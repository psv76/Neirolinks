"""Read-only first-visit inventory for registered or unknown Wiren Board controllers.

No controller approval, GitHub access, MQTT writes, service restarts or
engineering-rule mutations. Evidence remains local until an engineer exports it.
"""
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import tarfile
import tempfile
import uuid

from .controller import read_hardware_identity
from .diagnostics import DIAGNOSTICS_DIR, Diagnostics
from .layout import target
from .system import System
from .util import Error, digest, require

CONFIGS = ("/etc/wb-mqtt-serial.conf", "/etc/wb-webui.conf")
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_METADATA_BYTES = 3 * 1024 * 1024
TOPIC_DEVICE = re.compile(r"^/devices/([^/]+)/meta$")
TOPIC_CONTROL = re.compile(r"^/devices/([^/]+)/controls/(.+)/meta$")


def _json(data, label, warnings):
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("top-level object expected")
        return value
    except (ValueError, UnicodeError, TypeError) as exc:
        warnings.append(label + ": invalid JSON (" + str(exc) + ")")
        return None


def serial_devices(config):
    """Configured Modbus devices; a config entry does NOT imply an online device."""
    devices = []
    for port in config.get("ports", []):
        if not isinstance(port, dict):
            continue
        port_path = str(port.get("path") or "")
        for device in port.get("devices", []):
            if not isinstance(device, dict):
                continue
            key = device.get("id")
            if not isinstance(key, str) or not key:
                continue
            devices.append({
                "device_id": key,
                "device_type": str(device.get("device_type") or ""),
                "configured_name": str(device.get("name") or ""),
                "slave_id": str(device.get("slave_id") or ""),
                "port": port_path,
                "configured_enabled": device.get("enabled", port.get("enabled", True)),
                "origin": "wb-mqtt-serial.conf",
            })
    return sorted(devices, key=lambda v: (v["port"], v["device_id"]))


def widget_channels(config):
    """Explicit cell labels; dashboards are context, NOT proof of field wiring."""
    dashboard_names = {}
    for dash in config.get("dashboards", []):
        if not isinstance(dash, dict):
            continue
        groups = dash.get("widgets", [])
        def visit(value):
            if isinstance(value, str):
                dashboard_names.setdefault(value, set()).add(str(dash.get("name") or ""))
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(groups)
    items = []
    for widget in config.get("widgets", []):
        if not isinstance(widget, dict):
            continue
        widget_id = widget.get("id")
        for cell in widget.get("cells", []) if isinstance(widget.get("cells"), list) else []:
            if not isinstance(cell, dict):
                continue
            path = cell.get("id")
            if not isinstance(path, str) or "/" not in path or path.startswith("/"):
                continue
            device, control = path.split("/", 1)
            if not device or not control:
                continue
            label = str(cell.get("name") or "").strip()
            items.append({
                "path": path,
                "device_id": device,
                "control": control,
                "ui_label": label,
                "widget": str(widget.get("name") or ""),
                "widget_id": str(widget_id or ""),
                "dashboards": sorted(dashboard_names.get(widget_id, [])),
                "label_present": bool(label),
                "evidence": "wb-webui.conf",
            })
    return sorted(items, key=lambda x: (x["device_id"], x["control"], x["widget_id"]))


def mqtt_topics(text, warnings):
    """Retained MQTT *metadata only*, never values, commands or credentials."""
    if len(text.encode("utf-8")) > MAX_METADATA_BYTES:
        warnings.append("MQTT metadata exceeds size cap; ignored")
        return {}, {}
    devices, controls = {}, {}
    for line in text.splitlines():
        if "\t" not in line:
            continue
        topic, payload = line.split("\t", 1)
        match_device, match_control = TOPIC_DEVICE.fullmatch(topic), TOPIC_CONTROL.fullmatch(topic)
        if not (match_device or match_control):
            continue
        try:
            raw = json.loads(payload)
        except (ValueError, UnicodeError):
            continue
        if not isinstance(raw, dict):
            continue
        safe = {k: raw[k] for k in ("title", "driver", "type", "units") if isinstance(raw.get(k), str)}
        if match_device:
            devices[match_device.group(1)] = safe
        else:
            device, control = match_control.groups()
            controls[device + "/" + control] = safe
        if len(devices) + len(controls) > 10000:
            warnings.append("MQTT metadata item limit exceeded; partial snapshot")
            break
    return devices, controls


def build_map(serial, widgets, mqtt_devices, mqtt_controls):
    labels = {}
    for item in widgets:
        if item["label_present"]:
            labels.setdefault(item["path"], []).append(item)
    serial_by_id = {d["device_id"]: d for d in serial}
    device_ids = sorted(set(serial_by_id)
                        | set(mqtt_devices)
                        | {x["device_id"] for x in widgets}
                        | {path.split("/", 1)[0] for path in mqtt_controls})
    devices = []
    for key in device_ids:
        listed = [x for x in widgets if x["device_id"] == key]
        devices.append({
            "device_id": key,
            "configured_modbus": key in serial_by_id,
            "mqtt_device_meta_seen": key in mqtt_devices,
            "widget_control_count": len(listed),
            "named_widget_controls": sum(bool(x["label_present"]) for x in listed),
            "configured": serial_by_id.get(key),
            "mqtt": mqtt_devices.get(key),
            "without_widget_labels": not any(x["label_present"] for x in listed),
            "status_note": "appearance in config or MQTT does not verify wiring",
        })
    unlabelled = [
        {"path": path, "device_id": path.split("/", 1)[0],
         "mqtt_title": meta.get("title", ""), "reason": "no explicit wb-webui cell label"}
        for path, meta in sorted(mqtt_controls.items()) if path not in labels
    ]
    return {
        "schema": 1,
        "scope": "preliminary; widget text is an unverified installation hint",
        "configured_modbus_devices": serial,
        "webui_channels": widgets,
        "mqtt_devices": devices,
        "mqtt_control_metadata_count": len(mqtt_controls),
        "mqtt_channels_without_explicit_widget_label": unlabelled,
        "devices_without_explicit_widget_labels": [x for x in devices if x["without_widget_labels"]],
    }


class Onboarding:
    def __init__(self, engine=None):
        self.root = getattr(engine, "root", "/")
        self.system = getattr(engine, "system", None) or System()

    def target(self, logical):
        return target(self.root, logical)

    @staticmethod
    def _write(root, name, data):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def _packages(self, warnings):
        try:
            result = self.system.run(["/usr/bin/dpkg-query", "-W", "-f=${binary:Package}\\t${Version}\\n"], timeout=12)
        except (Error, OSError, ValueError) as exc:
            warnings.append("packages: " + str(exc))
            return []
        out = []
        for line in result.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and parts[0].startswith(("wb-", "sprut", "nst", "neiro", "mosquitto", "node-red", "tailscale")):
                out.append({"package": parts[0], "version": parts[1]})
        return sorted(out, key=lambda x: x["package"])

    def collect(self, mode):
        require(mode in ("inventory", "channels"), "Unsupported onboarding mode")
        # Do not require a registered/active controller or a completed NST sync.
        identity = read_hardware_identity(self.root)
        require(identity.get("serial"), "WB serial unavailable; no registration draft may be inferred")
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        destination = self.target(DIAGNOSTICS_DIR + "/nst-onboarding-" + stamp + ".tar.gz")
        destination.parent.mkdir(parents=True, exist_ok=True)
        warnings = []
        with tempfile.TemporaryDirectory(prefix="nst-onboarding-") as temp:
            root = Path(temp)
            collector = Diagnostics(self)
            inventory = []
            copy = CONFIGS if mode == "channels" else CONFIGS[:1]
            parsed = {}
            for path in copy:
                source = collector._config_source(path)
                if source.is_file() and source.stat().st_size > MAX_CONFIG_BYTES:
                    warnings.append(path + ": exceeds size cap; omitted")
                    inventory.append({"path": path, "status": "oversized"})
                    continue
                collector._copy_file(root, path, "config", inventory)
                evidence = root / "config" / path.lstrip("/")
                if evidence.is_file():
                    value = _json(evidence.read_bytes(), path, warnings)
                    if value is None:
                        # Fail closed: heuristics cannot guarantee redaction of malformed configs.
                        evidence.unlink()
                        inventory[-1]["status"] = "invalid_json_omitted"
                    else:
                        parsed[path] = value
                else:
                    warnings.append(path + ": unavailable")
            serial = serial_devices(parsed.get(CONFIGS[0]) or {})
            self._write(root, "hardware.json", {
                "identity": identity, "hostname": self.system.hostname(),
                "installed_packages": self._packages(warnings),
                "configured_modbus_count": len(serial),
                "configured_modbus_devices": serial,
            })
            self._write(root, "config-inventory.json", inventory)
            if mode == "channels":
                widgets = widget_channels(parsed.get(CONFIGS[1]) or {})
                md, mc = {}, {}
                try:
                    md, mc = mqtt_topics(self.system.mqtt_metadata(), warnings)
                except (Error, OSError, ValueError, AttributeError) as exc:
                    warnings.append("MQTT metadata unavailable: " + str(exc))
                mapping = build_map(serial, widgets, md, mc)
                self._write(root, "channel-map.json", mapping)
                columns = ("path", "device_id", "control", "ui_label", "widget", "widget_id", "dashboards")
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                for row in widgets:
                    writer.writerow({**row, "dashboards": "; ".join(row["dashboards"])})
                (root / "widget-channels.csv").write_text(buf.getvalue(), encoding="utf-8-sig")
            self._write(root, "meta.json", {
                "schema": 1, "mode": mode, "created_at": now.isoformat(),
                "identity": identity, "registered": "not_checked",
                "warnings": warnings,
                "notice": "Preliminary inventory only: names from WB widgets are not physical verification.",
            })
            collector._checksums(root)
            with tarfile.open(destination, mode="w:gz") as archive:
                for file in sorted(root.rglob("*")):
                    if file.is_file():
                        archive.add(file, arcname=file.relative_to(root).as_posix(), recursive=False)
        return {"command": "onboarding", "action": mode, "serial": identity["serial"],
                "bundle": str(destination), "sha256": digest(destination.read_bytes()),
                "warnings": warnings, "final_status": "ok"}
