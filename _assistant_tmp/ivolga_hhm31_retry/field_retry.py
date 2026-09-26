#!/usr/bin/env python3
"""Temporary field helper for 05_31 Ivolga HHM 3.1 controlled retry.

Stdlib-only orchestration around existing WB tools. Read-only by default.
Mutation is limited to explicit NLI target staging and, only with --execute-update
plus an interactive phrase, `nli --json update hhm`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

OBJECT = "05_31_Ivolga_13"
PR_HEAD = "5efce9783886a991d9d1b9008860f9309b1d5559"
RUNTIME_COMMIT = "20af0c29ed37130a5d4ff051ff1fb5984a5f8193"
VERSION = "3.1"
NLI_VERSION = "0.1.9"
REPO = "psv76/Neirolinks"
RAW = f"https://raw.githubusercontent.com/{REPO}/{PR_HEAD}"
EVIDENCE_ROOT = Path("/tmp/hhm31-field-retry")
NLI_CONFIG = Path("/mnt/data/etc/neiro/nli/config.json")
NLI_CONFIG_BACKUP = Path("/mnt/data/etc/neiro/nli/config.json.pre-hhm31-retry")
RELEASE_DIR = Path("/mnt/data/etc/neiro/nli/releases")

MANIFESTS = {
    "gazebo": {
        "repo_path": "NLI/releases/hhm-gazebo-3.1.json",
        "sha256": "c3de99685ba6995ed2b51fcd74d1bc20c3c416e293691c9b42689cc857547261",
    },
    "boiler": {
        "repo_path": "NLI/releases/hhm-boiler-3.1.json",
        "sha256": "b8c45743c4d290949e42f0b459804b1e545087a788383fb0cb816edc0379d444",
    },
}

GAZEBO_FLOOR = "921.10_TEMP_NONE/External Sensor 1"
GAZEBO_AIR = "921.09_MSW_TH/Temperature"

HOUSE_FLOORS = [
    "903.09_TEMP_NONE/External Sensor 1",
    "902.11_M1W2_TEMP_NONE/External Sensor 1",
    "902.09_M1W2_TEMP_NONE/External Sensor 1",
    "902.06_M1W2_TEMP_NONE/External Sensor 1",
    "902.04_M1W2_LEAK_TEMP/External Sensor 2",
    "902.13_M1W2_LEAK_TEMP/External Sensor 2",
    "902.02_M1W2_TEMP_NONE/External Sensor 1",
    "903.02_M1W2_LEAK_TEMP/External Sensor 2",
    "903.06_M1W2_LEAK_TEMP/External Sensor 2",
]

BOILER_DIAG = [
    "wb-m1w2_170/External Sensor 1",
    "wb-m1w2_170/External Sensor 2",
    "wb-m1w2_141/External Sensor 1",
    "wb-m1w2_141/External Sensor 2",
    "wb-m1w2_167/External Sensor 1",
    "wb-m1w2_167/External Sensor 2",
    "wb-m1w2_121/External Sensor 1",
    "wb-m1w2_173/External Sensor 1",
    "wb-m1w2_173/External Sensor 2",
    "wb-m1w2_166/External Sensor 1",
]

BOILER_MANAGER = [p for p in BOILER_DIAG if p != "wb-m1w2_170/External Sensor 2"]
BOILER_ALL = HOUSE_FLOORS + BOILER_DIAG

EXPECTED_OWNER_PATHS = {
    "gazebo": {"624_combo_besedka": [GAZEBO_FLOOR]},
    "boiler": {
        "620": HOUSE_FLOORS,
        "500_HHM3": BOILER_MANAGER,
        "600": BOILER_DIAG,
    },
}

ROLE_CONTROLS = {
    "gazebo": [
        "NL_combo_thermostat_504/floor_valid",
        "NL_combo_thermostat_504/reason",
        "NL_combo_thermostat_504/runtime_status",
        "NL_combo_thermostat_504/sensor_health_contract",
        "NL_combo_thermostat_504/floor_temperature",
    ],
    "boiler": [
        "HHM3_FSE/runtime_status",
        "HHM3_FSE/operational_status",
        "HHM3_FSE/sensor_health_contract",
        "HHM3_FSE/in_service",
        "HHM3_FSE/source_status",
    ],
}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(argv: List[str], timeout: Optional[int] = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=check)


def require_cmd(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required command not found: {name}")


def control_topic(path: str) -> str:
    device, control = path.split("/", 1)
    return f"/devices/{device}/controls/{control}"


def parse_scalar(value: Optional[str]) -> Any:
    if value is None:
        return None
    s = value.strip()
    if s == "":
        return ""
    lo = s.lower()
    if lo == "true":
        return True
    if lo == "false":
        return False
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        return s


def is_ok(v: Any) -> bool:
    return v is True or v == 1 or v == "1"


def numeric(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def snapshot_topics(topics: Iterable[str], seconds: float = 2.0) -> Dict[str, str]:
    topics = list(dict.fromkeys(topics))
    if not topics:
        return {}
    require_cmd("mosquitto_sub")
    argv = ["mosquitto_sub", "-h", "127.0.0.1", "-p", "1883", "-v"]
    for topic in topics:
        argv += ["-t", topic]
    proc = subprocess.Popen(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, _ = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    values: Dict[str, str] = {}
    for line in out.splitlines():
        if " " in line:
            topic, payload = line.split(" ", 1)
        else:
            topic, payload = line, ""
        values[topic] = payload
    return values


def snapshot_controls(paths: Iterable[str], include_errors: bool = True) -> Dict[str, Dict[str, Any]]:
    paths = list(dict.fromkeys(paths))
    topics = []
    for path in paths:
        t = control_topic(path)
        topics.append(t)
        if include_errors:
            topics.append(t + "/meta/error")
    raw = snapshot_topics(topics)
    result: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        t = control_topic(path)
        result[path] = {
            "value": parse_scalar(raw.get(t)),
            "error": parse_scalar(raw.get(t + "/meta/error")) if include_errors else None,
            "value_seen": t in raw,
            "error_seen": (t + "/meta/error") in raw,
        }
    return result


def mqtt_rpc(topic: str, payload: Dict[str, Any], timeout: int = 12) -> Tuple[Dict[str, Any], float]:
    require_cmd("mosquitto_pub")
    require_cmd("mosquitto_sub")
    reply = topic + "/reply"
    sub = subprocess.Popen(
        ["mosquitto_sub", "-h", "127.0.0.1", "-p", "1883", "-t", reply, "-C", "1"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.12)
    started = time.monotonic()
    pub = run(["mosquitto_pub", "-h", "127.0.0.1", "-p", "1883", "-t", topic,
               "-m", json.dumps(payload, separators=(",", ":"))], timeout=3)
    if pub.returncode != 0:
        sub.kill()
        raise RuntimeError("mosquitto_pub failed: " + pub.stderr.strip())
    try:
        out, err = sub.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        sub.kill()
        sub.communicate()
        raise RuntimeError(f"MQTT RPC timeout: {topic}")
    elapsed_ms = (time.monotonic() - started) * 1000.0
    if sub.returncode != 0:
        raise RuntimeError("mosquitto_sub failed: " + err.strip())
    try:
        return json.loads(out.strip()), elapsed_ms
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid RPC JSON on {reply}: {out!r}") from exc


def db_rpc(method: str, params: Dict[str, Any], timeout: int = 12) -> Dict[str, Any]:
    client = f"hhm31-field-{os.getpid()}-{int(time.time()*1000)%1000000}"
    req_id = int(time.time() * 1000) % 2147483647
    topic = f"/rpc/v1/db_logger/history/{method}/{client}"
    response, _ = mqtt_rpc(topic, {"id": req_id, "params": params}, timeout=timeout)
    if response.get("id") != req_id:
        raise RuntimeError(f"db history mismatched RPC id: {response}")
    if response.get("error") not in (None, {}):
        raise RuntimeError(f"db history RPC error: {response.get('error')}")
    return response.get("result") or {}


def db_channels() -> Dict[str, Any]:
    return (db_rpc("get_channels", {}).get("channels") or {})


def split_channel(path: str) -> List[str]:
    device, control = path.split("/", 1)
    return [device, control]


def db_values(paths: Iterable[str], start: int, end: int, max_records: int = 5000) -> List[Dict[str, Any]]:
    paths = list(dict.fromkeys(paths))
    if not paths:
        return []
    params = {
        "ver": 0,
        "channels": [split_channel(x) for x in paths],
        "timestamp": {"gt": int(start), "lt": int(end)},
        "max_records": int(max_records),
        "request_timeout": 9,
        "with_milliseconds": True,
    }
    return (db_rpc("get_values", params, timeout=12).get("values") or [])


def read_db_config_summary() -> Dict[str, Any]:
    p = Path("/etc/wb-mqtt-db.conf")
    if not p.exists():
        return {"present": False}
    data = p.read_bytes()
    return {"present": True, "path": str(p), "size": len(data), "sha256": sha256(data),
            "text_preview": data.decode("utf-8", "replace")[:12000]}


def record_path(rec: Dict[str, Any]) -> Optional[str]:
    d = rec.get("device")
    c = rec.get("control")
    return f"{d}/{c}" if d is not None and c is not None else None


def record_value(rec: Dict[str, Any]) -> Any:
    return rec.get("value", rec.get("v"))


def history_role(role: str, hours: int = 24, save: bool = True) -> Dict[str, Any]:
    report: Dict[str, Any] = {"time": now_iso(), "role": role, "hours": hours, "db_config": read_db_config_summary()}
    try:
        inventory = db_channels()
        report["db_available"] = True
        report["channel_count"] = len(inventory)
    except Exception as exc:
        report.update(db_available=False, error=str(exc), recommended_stability_s=600 if role == "gazebo" else 180)
        return report

    now = int(time.time())
    start = now - hours * 3600
    if role == "gazebo":
        desired = [
            GAZEBO_FLOOR, GAZEBO_FLOOR + " OK", GAZEBO_AIR,
            "NL_combo_thermostat_504/floor_valid",
            "NL_combo_thermostat_504/reason",
            "NL_combo_thermostat_504/runtime_status",
            "NL_combo_thermostat_504/floor_temperature",
        ]
        present = [p for p in desired if p in inventory]
        report["expected_channels"] = desired
        report["present_channels"] = present
        report["coverage"] = len(present) / len(desired)
        recent = db_values(present, start, now, 4000) if present else []
        report["recent_records"] = recent
        # Broad incident window: controller clock was previously suspect, so use 48 h UTC.
        inc_start = int(dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc).timestamp())
        inc_end = int(dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc).timestamp())
        incident_paths = [p for p in [GAZEBO_FLOOR, GAZEBO_FLOOR + " OK",
                                      "NL_combo_thermostat_504/floor_valid",
                                      "NL_combo_thermostat_504/reason"] if p in inventory]
        incident = db_values(incident_paths, inc_start, inc_end, 12000) if incident_paths else []
        report["incident_records"] = incident
        invalid_ts = []
        for rec in incident:
            if record_path(rec) == "NL_combo_thermostat_504/reason" and str(record_value(rec)) == "FLOOR_SENSOR_INVALID":
                try:
                    invalid_ts.append(float(rec.get("timestamp", rec.get("t"))))
                except (TypeError, ValueError):
                    pass
        invalid_ts = sorted(set(invalid_ts))
        intervals = [round(invalid_ts[i] - invalid_ts[i-1], 3) for i in range(1, len(invalid_ts))]
        report["historical_floor_invalid_timestamps"] = invalid_ts
        report["historical_floor_invalid_intervals_s"] = intervals
        report["recommended_stability_s"] = 600
    else:
        expected = []
        for p in BOILER_ALL:
            expected += [p, p + " OK"]
        present = [p for p in expected if p in inventory]
        report["expected_channels"] = expected
        report["present_channels"] = present
        coverage = len(present) / len(expected)
        report["coverage"] = coverage
        ok_paths = [p + " OK" for p in BOILER_ALL if p + " OK" in inventory]
        representative = [p for p in [HOUSE_FLOORS[0], "wb-m1w2_170/External Sensor 1", "wb-m1w2_167/External Sensor 1"] if p in inventory]
        recent = db_values(ok_paths + representative, start, now, 8000) if (ok_paths or representative) else []
        report["recent_records"] = recent
        historical_bad_ok = False
        bad_ok_records = []
        ok_set = set(ok_paths)
        for rec in recent:
            if record_path(rec) in ok_set:
                vals = [rec.get("min"), rec.get("max"), record_value(rec)]
                parsed = [numeric(v) for v in vals]
                if any(v is not None and v < 0.5 for v in parsed):
                    historical_bad_ok = True
                    bad_ok_records.append(rec)
        report["historical_bad_ok"] = historical_bad_ok
        report["historical_bad_ok_records"] = bad_ok_records
        report["recommended_stability_s"] = 120 if coverage >= 0.8 and not historical_bad_ok else 180
    return report


def package_version(name: str) -> Optional[str]:
    cp = run(["dpkg-query", "-W", "-f=${Version}", name], timeout=4)
    return cp.stdout.strip() if cp.returncode == 0 else None


def service_state(name: str) -> Dict[str, Any]:
    cp = run(["systemctl", "show", name, "-p", "ActiveState", "-p", "SubState",
              "-p", "ActiveEnterTimestamp"], timeout=5)
    result: Dict[str, Any] = {"returncode": cp.returncode}
    for line in cp.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def nli_call(args: List[str], timeout: int = 120) -> Dict[str, Any]:
    cp = run(["nli", "--json"] + args, timeout=timeout)
    result: Dict[str, Any] = {"returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    try:
        result["json"] = json.loads(cp.stdout)
    except json.JSONDecodeError:
        result["json"] = None
    return result


def nli_version() -> Optional[str]:
    cp = run(["nli", "--json", "--version"], timeout=5)
    try:
        return str(json.loads(cp.stdout).get("version"))
    except Exception:
        cp2 = run(["nli", "--version"], timeout=5)
        m = re.search(r"(\d+\.\d+\.\d+)", cp2.stdout + cp2.stderr)
        return m.group(1) if m else None


def port_load_probe(sensor_path: str) -> Dict[str, Any]:
    m = re.search(r"/External Sensor ([12])$", sensor_path)
    if not m:
        return {"ok": False, "error": "unsupported sensor path"}
    input_no = int(m.group(1))
    device = sensor_path.split("/", 1)[0]
    health = sensor_path + " OK"
    snap = snapshot_controls([sensor_path, health])
    local_temp = numeric(snap[sensor_path]["value"])
    local_ok = snap[health]["value"]
    if local_temp is None or not is_ok(local_ok):
        return {"ok": False, "error": "local controls not healthy", "snapshot": snap}
    for p in (sensor_path, health):
        err = snap[p].get("error")
        if err not in (None, "", 0, False):
            return {"ok": False, "error": f"local control error on {p}: {err}", "snapshot": snap}

    client = f"hhm31-preflight-{os.getpid()}-{int(time.time()*1000)%1000000}"
    topic = f"/rpc/v1/wb-mqtt-serial/port/Load/{client}"
    req_id = int(time.time() * 1000) % 1000000000
    p1 = {"id": req_id, "params": {"device_id": device, "function": 4,
          "address": 7 + input_no - 1, "count": 1, "format": "HEX", "total_timeout": 10000}}
    try:
        r1, ms1 = mqtt_rpc(topic, p1, timeout=12)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stage": "temperature", "snapshot": snap}
    if r1.get("id") != req_id or r1.get("error") is not None or not isinstance(r1.get("result"), dict):
        return {"ok": False, "error": "temperature RPC returned error", "reply": r1, "snapshot": snap}
    hx = r1["result"].get("response")
    if not isinstance(hx, str) or not re.fullmatch(r"[0-9A-Fa-f]{4}", hx):
        return {"ok": False, "error": "bad temperature response", "reply": r1, "snapshot": snap}
    raw = int(hx, 16)
    if raw == 0x7FFF:
        return {"ok": False, "error": "temperature sentinel 0x7fff", "reply": r1, "snapshot": snap}
    signed = raw - 65536 if raw >= 32768 else raw
    bus_temp = signed * 0.0625
    rounded = float(f"{round(bus_temp / 0.05) * 0.05:.2f}")
    if local_temp not in (bus_temp, rounded):
        return {"ok": False, "error": "bus/local temperature mismatch", "bus_temp": bus_temp,
                "local_temp": local_temp, "reply": r1, "snapshot": snap}

    req_id2 = req_id + 1
    p2 = {"id": req_id2, "params": {"device_id": device, "function": 2,
          "address": 16 + input_no - 1, "count": 1, "format": "HEX", "total_timeout": 10000}}
    try:
        r2, ms2 = mqtt_rpc(topic, p2, timeout=12)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stage": "health", "temperature_reply": r1,
                "snapshot": snap}
    if r2.get("id") != req_id2 or r2.get("error") is not None or not isinstance(r2.get("result"), dict):
        return {"ok": False, "error": "health RPC returned error", "reply": r2, "snapshot": snap}
    if r2["result"].get("response") != "01":
        return {"ok": False, "error": "health register is not OK", "reply": r2, "snapshot": snap}
    return {"ok": True, "sensor": sensor_path, "local_temp": local_temp, "bus_temp": bus_temp,
            "local_ok": local_ok, "temperature_rtt_ms": round(ms1, 1), "health_rtt_ms": round(ms2, 1),
            "snapshot": snap}


def sensor_bounds(path: str) -> Tuple[float, float]:
    if path in HOUSE_FLOORS or path == GAZEBO_FLOOR:
        return -20.0, 70.0
    return -40.0, 120.0


def current_sensor_health(role: str) -> Dict[str, Any]:
    sensors = [GAZEBO_FLOOR] if role == "gazebo" else BOILER_ALL
    paths = []
    for p in sensors:
        paths += [p, p + " OK"]
    snap = snapshot_controls(paths)
    failures = []
    for p in sensors:
        lo, hi = sensor_bounds(p)
        tv = numeric(snap[p]["value"])
        hv = snap[p + " OK"]["value"]
        terr = snap[p].get("error")
        herr = snap[p + " OK"].get("error")
        if tv is None or not (lo <= tv <= hi):
            failures.append(f"{p}: invalid temperature {snap[p]['value']!r}")
        if not is_ok(hv):
            failures.append(f"{p} OK: {hv!r}")
        if terr not in (None, "", 0, False):
            failures.append(f"{p}: error={terr!r}")
        if herr not in (None, "", 0, False):
            failures.append(f"{p} OK: error={herr!r}")
    return {"ok": not failures, "failures": failures, "snapshot": snap}


def evidence_dir(role: str, label: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    p = EVIDENCE_ROOT / f"{stamp}-{role}-{label}"
    p.mkdir(parents=True, exist_ok=False)
    return p


def preflight_role(role: str, hours: int = 24, save: bool = True) -> Dict[str, Any]:
    report: Dict[str, Any] = {"time": now_iso(), "role": role, "object": OBJECT, "checks": {}}
    checks = report["checks"]
    checks["hostname"] = run(["hostname"], timeout=3).stdout.strip()
    checks["packages"] = {"wb-rules": package_version("wb-rules"),
                          "wb-mqtt-serial": package_version("wb-mqtt-serial")}
    checks["services"] = {n: service_state(n) for n in ("wb-rules", "wb-mqtt-serial", "wb-mqtt-db")}
    checks["nli_version"] = nli_version()
    checks["nli_status"] = nli_call(["status"], timeout=20)
    checks["nli_verify_hhm"] = nli_call(["verify", "hhm"], timeout=30)
    if role == "boiler":
        checks["nli_verify_pressure_makeup"] = nli_call(["verify", "pressure_makeup"], timeout=30)
    checks["sensor_health"] = current_sensor_health(role)
    if role == "gazebo":
        air = snapshot_controls([GAZEBO_AIR], include_errors=True)[GAZEBO_AIR]
        checks["air_sensor"] = air
    representative = GAZEBO_FLOOR if role == "gazebo" else "wb-m1w2_170/External Sensor 1"
    checks["port_load_probe"] = port_load_probe(representative)
    checks["history"] = history_role(role, hours=hours, save=False)

    failures = []
    if checks["nli_version"] != NLI_VERSION:
        failures.append(f"NLI version is {checks['nli_version']}, expected {NLI_VERSION}")
    for svc in ("wb-rules", "wb-mqtt-serial"):
        if checks["services"][svc].get("ActiveState") != "active":
            failures.append(f"{svc} is not active")
    if checks["nli_status"]["returncode"] != 0:
        failures.append("nli status failed")
    if checks["nli_verify_hhm"]["returncode"] != 0:
        failures.append("nli verify hhm failed")
    if role == "boiler" and checks["nli_verify_pressure_makeup"]["returncode"] != 0:
        failures.append("nli verify pressure_makeup failed")
    if not checks["sensor_health"]["ok"]:
        failures.extend(checks["sensor_health"]["failures"])
    if not checks["port_load_probe"].get("ok"):
        failures.append("port/Load representative proof failed: " + str(checks["port_load_probe"].get("error")))
    report["failures"] = failures
    report["ok"] = not failures
    if save:
        p = evidence_dir(role, "preflight")
        json_dump(p / "preflight.json", report)
        report["evidence_dir"] = str(p)
    return report


def fetch_manifest(role: str) -> Tuple[bytes, Dict[str, Any]]:
    info = MANIFESTS[role]
    url = f"{RAW}/{info['repo_path']}"
    req = urllib.request.Request(url, headers={"User-Agent": "hhm31-field-retry/1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(2 * 1024 * 1024)
    got = sha256(data)
    if got != info["sha256"]:
        raise RuntimeError(f"manifest SHA mismatch: {got} != {info['sha256']}")
    manifest = json.loads(data)
    if manifest.get("component") != "hhm" or manifest.get("version") != VERSION or manifest.get("role") != role:
        raise RuntimeError("manifest identity mismatch")
    if manifest.get("object") != OBJECT or (manifest.get("release") or {}).get("commit") != RUNTIME_COMMIT:
        raise RuntimeError("manifest object/runtime mismatch")
    return data, manifest


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def stage_role(role: str) -> Dict[str, Any]:
    if os.geteuid() != 0:
        raise RuntimeError("stage must run as root")
    if not NLI_CONFIG.is_file():
        raise RuntimeError(f"NLI config not found: {NLI_CONFIG}")
    data, manifest = fetch_manifest(role)
    cfg_bytes = NLI_CONFIG.read_bytes()
    cfg = json.loads(cfg_bytes)
    if cfg.get("object") != OBJECT or cfg.get("role") != role:
        raise RuntimeError(f"NLI config identity mismatch: object={cfg.get('object')} role={cfg.get('role')}")
    if "hhm" not in (cfg.get("components") or {}):
        raise RuntimeError("NLI hhm component not registered")
    if not NLI_CONFIG_BACKUP.exists():
        atomic_write(NLI_CONFIG_BACKUP, cfg_bytes, 0o600)
    retry_manifest = RELEASE_DIR / f"hhm-{role}-3.1-retry-{PR_HEAD[:12]}.json"
    atomic_write(retry_manifest, data, 0o644)
    cfg["release_source"] = "pinned"
    cfg["components"]["hhm"]["target"] = {"path": str(retry_manifest), "sha256": MANIFESTS[role]["sha256"]}
    atomic_write(NLI_CONFIG, (json.dumps(cfg, ensure_ascii=False, indent=2) + "\n").encode(), 0o600)
    check = nli_call(["check", "hhm"], timeout=120)
    return {"ok": check["returncode"] == 0, "manifest": str(retry_manifest),
            "manifest_sha256": MANIFESTS[role]["sha256"], "nli_check": check,
            "backup": str(NLI_CONFIG_BACKUP), "runtime_commit": manifest["release"]["commit"]}


def unstage(execute: bool) -> Dict[str, Any]:
    if not execute:
        raise RuntimeError("unstage requires --execute")
    if os.geteuid() != 0:
        raise RuntimeError("unstage must run as root")
    if not NLI_CONFIG_BACKUP.is_file():
        raise RuntimeError("staging backup not found; refusing to guess original config")
    backup = NLI_CONFIG_BACKUP.read_bytes()
    cfg = json.loads(backup)
    if cfg.get("object") != OBJECT:
        raise RuntimeError("backup config object mismatch")
    atomic_write(NLI_CONFIG, backup, 0o600)
    removed = []
    for p in RELEASE_DIR.glob(f"hhm-*-3.1-retry-{PR_HEAD[:12]}.json"):
        p.unlink()
        removed.append(str(p))
    NLI_CONFIG_BACKUP.unlink()
    return {"ok": True, "restored": str(NLI_CONFIG), "removed": removed}


class TopicMonitor:
    def __init__(self, topics: Iterable[str], log_path: Path):
        self.topics = list(dict.fromkeys(topics))
        self.log_path = log_path
        self.proc: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.events: List[Tuple[float, str, str]] = []
        self._stop = threading.Event()

    def start(self) -> None:
        argv = ["mosquitto_sub", "-h", "127.0.0.1", "-p", "1883", "-v"]
        for t in self.topics:
            argv += ["-t", t]
        self.proc = subprocess.Popen(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     bufsize=1)
        def reader() -> None:
            assert self.proc and self.proc.stdout
            with self.log_path.open("a", encoding="utf-8") as f:
                for line in self.proc.stdout:
                    ts = time.time()
                    raw = line.rstrip("\n")
                    if " " in raw:
                        topic, payload = raw.split(" ", 1)
                    else:
                        topic, payload = raw, ""
                    self.events.append((ts, topic, payload))
                    f.write(f"{ts:.3f}\t{topic}\t{payload}\n")
                    f.flush()
                    if self._stop.is_set():
                        break
        self.thread = threading.Thread(target=reader, daemon=True)
        self.thread.start()
        time.sleep(0.2)

    def stop(self) -> None:
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.thread:
            self.thread.join(timeout=2)


def journal_since(epoch: float) -> str:
    when = dt.datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    cp = run(["journalctl", "-u", "wb-rules", "--since", when, "--no-pager", "-o", "short-iso"], timeout=30)
    return cp.stdout


def parse_m1w2_diagnostics(text: str) -> List[Dict[str, Any]]:
    out = []
    rx = re.compile(r"\[отопление\]\[([^\]]+)\]\[M1W2 ([^\]]+)\];\s+(\{.*\})")
    for line in text.splitlines():
        m = rx.search(line)
        if not m:
            continue
        try:
            diag = json.loads(m.group(3))
        except json.JSONDecodeError:
            continue
        out.append({"owner": m.group(1), "path": m.group(2), "diag": diag, "line": line})
    return out


def expected_pair_set(role: str) -> set:
    return {(owner, path) for owner, paths in EXPECTED_OWNER_PATHS[role].items() for path in paths}


def latest_pair_state(diags: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    latest = {}
    for item in diags:
        latest[(item["owner"], item["path"])] = item
    return latest


def role_monitor_topics(role: str) -> List[str]:
    paths = ROLE_CONTROLS[role][:]
    if role == "gazebo":
        paths += [GAZEBO_FLOOR, GAZEBO_FLOOR + " OK"]
    else:
        paths += [p for x in BOILER_ALL for p in (x, x + " OK")]
    return [control_topic(p) for p in paths]


def smoke_role(role: str, since_epoch: float, stability_s: Optional[int] = None,
               monitor: Optional[TopicMonitor] = None, evidence: Optional[Path] = None) -> Dict[str, Any]:
    evidence = evidence or evidence_dir(role, "smoke")
    own_monitor = False
    if monitor is None:
        monitor = TopicMonitor(role_monitor_topics(role), evidence / "mqtt-events.tsv")
        monitor.start()
        own_monitor = True
    report: Dict[str, Any] = {"role": role, "started": now_iso(), "since_epoch": since_epoch}
    try:
        verify = nli_call(["verify", "hhm"], timeout=40)
        report["nli_verify_hhm"] = verify
        if role == "boiler":
            report["nli_verify_pressure_makeup"] = nli_call(["verify", "pressure_makeup"], timeout=40)
        if verify["returncode"] != 0:
            report.update(ok=False, failure="nli verify hhm failed")
            return report

        if role == "gazebo":
            deadline = time.time() + 45
            qualified_at = None
            while time.time() < deadline:
                snap = snapshot_controls(ROLE_CONTROLS[role], include_errors=False)
                if is_ok(snap["NL_combo_thermostat_504/floor_valid"]["value"]):
                    qualified_at = time.time()
                    break
                time.sleep(2)
            report["qualified_at"] = qualified_at
            if qualified_at is None:
                report.update(ok=False, failure="gazebo floor did not qualify within 45 s")
                return report
            duration = int(stability_s or 600)
            invalid_samples = []
            end = time.time() + duration
            while time.time() < end:
                snap = snapshot_controls([
                    "NL_combo_thermostat_504/floor_valid",
                    "NL_combo_thermostat_504/reason",
                ], include_errors=False)
                fv = snap["NL_combo_thermostat_504/floor_valid"]["value"]
                rs = snap["NL_combo_thermostat_504/reason"]["value"]
                if not is_ok(fv) or rs == "FLOOR_SENSOR_INVALID":
                    invalid_samples.append({"time": now_iso(), "floor_valid": fv, "reason": rs})
                time.sleep(5)
            journal = journal_since(since_epoch)
            (evidence / "wb-rules-journal.txt").write_text(journal, encoding="utf-8")
            diags = parse_m1w2_diagnostics(journal)
            proof_valid = [x for x in diags if x["owner"] == "624_combo_besedka" and
                           x["path"] == GAZEBO_FLOOR and x["diag"].get("phase") == "RUNTIME" and
                           x["diag"].get("reason") == "VALID"]
            false_journal = [line for line in journal.splitlines() if "FLOOR_SENSOR_INVALID" in line]
            proof_warn = [line for line in journal.splitlines() if "POST_START_PROOF=" in line]
            final = snapshot_controls(ROLE_CONTROLS[role], include_errors=False)
            temp_topic = control_topic(GAZEBO_FLOOR)
            numeric_events = [e for e in monitor.events if e[0] >= since_epoch and e[1] == temp_topic]
            report.update(
                stability_s=duration,
                invalid_samples=invalid_samples,
                floor_invalid_journal=false_journal,
                post_start_proof_warnings=proof_warn,
                proof_valid_diagnostics=proof_valid,
                numeric_publications_after_update=len(numeric_events),
                final_controls=final,
            )
            contract = final["NL_combo_thermostat_504/sensor_health_contract"]["value"]
            final_valid = final["NL_combo_thermostat_504/floor_valid"]["value"]
            reason = final["NL_combo_thermostat_504/reason"]["value"]
            runtime = str(final["NL_combo_thermostat_504/runtime_status"]["value"] or "")
            report["ok"] = (not invalid_samples and not false_journal and is_ok(final_valid) and
                            reason != "FLOOR_SENSOR_INVALID" and contract == "m1w2-health-v1" and
                            "RUNTIME_UNSUPPORTED" not in runtime)
            if not report["ok"]:
                report["failure"] = "gazebo functional smoke failed"
        else:
            hist = history_role("boiler", hours=24, save=False)
            duration = int(stability_s or hist.get("recommended_stability_s", 180))
            expected = expected_pair_set("boiler")
            qualify_deadline = time.time() + 120
            all_valid_at = None
            last_latest = {}
            while time.time() < qualify_deadline:
                journal = journal_since(since_epoch)
                diags = parse_m1w2_diagnostics(journal)
                last_latest = latest_pair_state(diags)
                valid = {k for k, v in last_latest.items() if v["diag"].get("phase") == "RUNTIME" and
                         v["diag"].get("reason") == "VALID"}
                if expected.issubset(valid):
                    all_valid_at = time.time()
                    break
                time.sleep(5)
            report["all_valid_at"] = all_valid_at
            report["expected_pairs"] = sorted([list(x) for x in expected])
            if all_valid_at is None:
                missing = sorted([list(x) for x in expected if x not in {k for k, v in last_latest.items()
                                  if v["diag"].get("phase") == "RUNTIME" and v["diag"].get("reason") == "VALID"}])
                report.update(ok=False, failure="not all boiler consumer/sensor pairs qualified within 120 s",
                              missing_pairs=missing)
                return report
            time.sleep(duration)
            journal = journal_since(since_epoch)
            (evidence / "wb-rules-journal.txt").write_text(journal, encoding="utf-8")
            diags = parse_m1w2_diagnostics(journal)
            latest = latest_pair_state(diags)
            bad_latest = []
            for pair in expected:
                item = latest.get(pair)
                if not item or item["diag"].get("phase") != "RUNTIME" or item["diag"].get("reason") != "VALID":
                    bad_latest.append({"owner": pair[0], "path": pair[1], "state": item})
            proof_warn = [line for line in journal.splitlines() if "POST_START_PROOF=" in line]
            final = snapshot_controls(ROLE_CONTROLS[role], include_errors=False)
            contract = final["HHM3_FSE/sensor_health_contract"]["value"]
            runtime = str(final["HHM3_FSE/runtime_status"]["value"] or "")
            services = {n: service_state(n) for n in ("wb-rules", "wb-mqtt-serial")}
            pressure_verify = report.get("nli_verify_pressure_makeup", {})
            report.update(stability_s=duration, history_summary={k: hist.get(k) for k in
                          ("coverage", "historical_bad_ok", "recommended_stability_s")},
                          bad_latest_pairs=bad_latest, post_start_proof_warnings=proof_warn,
                          final_controls=final, services=services)
            report["ok"] = (not bad_latest and contract == "m1w2-health-v1" and
                            "RUNTIME_UNSUPPORTED" not in runtime and
                            all(x.get("ActiveState") == "active" for x in services.values()) and
                            pressure_verify.get("returncode", 1) == 0)
            if not report["ok"]:
                report["failure"] = "boiler functional smoke failed"
        return report
    finally:
        if own_monitor:
            monitor.stop()
        report["finished"] = now_iso()
        report["evidence_dir"] = str(evidence)
        json_dump(evidence / "smoke.json", report)


def print_summary(report: Dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print()
    print("RESULT:", "PASS" if report.get("ok") else "FAIL")
    if not report.get("ok") and report.get("failure"):
        print("FAILURE:", report["failure"])


def retry_role(role: str, execute_update: bool, hours: int = 24) -> int:
    if not execute_update:
        raise RuntimeError("retry mutation requires --execute-update")
    if os.geteuid() != 0:
        raise RuntimeError("retry must run as root")
    root = evidence_dir(role, "retry")
    pre = preflight_role(role, hours=hours, save=False)
    json_dump(root / "preflight.json", pre)
    print("PRECHECK:", "PASS" if pre.get("ok") else "FAIL")
    if not pre.get("ok"):
        print_summary(pre)
        return 2
    staged = stage_role(role)
    json_dump(root / "stage.json", staged)
    if not staged.get("ok"):
        print_summary({"ok": False, "failure": "NLI staged check failed", "stage": staged})
        return 3
    phrase = f"UPDATE {role.upper()}"
    print(f"About to run nli update hhm on {role}. Type exactly: {phrase}")
    if input("> ").strip() != phrase:
        print("Cancelled; target remains staged. No HHM update executed.")
        return 4

    monitor = TopicMonitor(role_monitor_topics(role), root / "mqtt-events.tsv")
    monitor.start()
    update_epoch = time.time()
    try:
        update = nli_call(["update", "hhm"], timeout=240)
        json_dump(root / "nli-update.json", update)
        print(update.get("stdout", ""), end="")
        if update["returncode"] != 0:
            print(update.get("stderr", ""), file=sys.stderr)
            print("NLI update failed. Do not start a second update automatically; inspect status/pending.")
            return 5
        stability = (pre.get("checks", {}).get("history", {}) or {}).get("recommended_stability_s")
        smoke = smoke_role(role, update_epoch, stability_s=stability, monitor=monitor, evidence=root)
    finally:
        monitor.stop()
    print_summary(smoke)
    if not smoke.get("ok"):
        print("Recommended next command after reviewing evidence:")
        print("  nli --json rollback hhm")
        print("No automatic rollback was executed.")
        return 6
    return 0


def selftest() -> Dict[str, Any]:
    tests = []
    def t(name: str, cond: bool) -> None:
        tests.append({"name": name, "ok": bool(cond)})
        if not cond:
            raise AssertionError(name)
    t("control topic", control_topic("dev/External Sensor 1") == "/devices/dev/controls/External Sensor 1")
    t("numeric int", numeric("23.5") == 23.5)
    t("numeric rejects bool", numeric(True) is None)
    t("ok values", all(is_ok(x) for x in (True, 1, "1")))
    t("bad ok", not is_ok(0))
    t("boiler inventory", len(BOILER_ALL) == 19 and len(set(BOILER_ALL)) == 19)
    t("manager inventory", len(BOILER_MANAGER) == 9)
    t("house floors", len(HOUSE_FLOORS) == 9)
    t("expected boiler pair count", len(expected_pair_set("boiler")) == 28)
    t("manifest constants", len(MANIFESTS["boiler"]["sha256"]) == 64 and len(MANIFESTS["gazebo"]["sha256"]) == 64)
    return {"ok": True, "tests": tests}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    h = sub.add_parser("history", help="read-only wb-mqtt-db evidence collection")
    h.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    h.add_argument("--hours", type=int, default=24)
    pf = sub.add_parser("preflight", help="read-only current state + representative port/Load probe")
    pf.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    pf.add_argument("--hours", type=int, default=24)
    st = sub.add_parser("stage", help="stage exact PR #73 manifest in NLI pinned config; no HHM update")
    st.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    us = sub.add_parser("unstage", help="restore pre-retry NLI config from the helper backup")
    us.add_argument("--execute", action="store_true")
    sm = sub.add_parser("smoke", help="passive post-update functional smoke")
    sm.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    sm.add_argument("--since-epoch", type=float, default=None)
    sm.add_argument("--stability-seconds", type=int, default=None)
    rt = sub.add_parser("retry", help="preflight + stage + explicit NLI update + passive smoke")
    rt.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    rt.add_argument("--hours", type=int, default=24)
    rt.add_argument("--execute-update", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "selftest":
            print_summary(selftest())
            return 0
        if args.command == "history":
            report = history_role(args.role, hours=args.hours)
            p = evidence_dir(args.role, "history")
            json_dump(p / "history.json", report)
            report["evidence_dir"] = str(p)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report.get("db_available") else 1
        if args.command == "preflight":
            report = preflight_role(args.role, hours=args.hours, save=True)
            print_summary(report)
            return 0 if report.get("ok") else 2
        if args.command == "stage":
            report = stage_role(args.role)
            print_summary(report)
            return 0 if report.get("ok") else 3
        if args.command == "unstage":
            report = unstage(args.execute)
            print_summary(report)
            return 0
        if args.command == "smoke":
            since = args.since_epoch or (time.time() - 60)
            report = smoke_role(args.role, since, args.stability_seconds)
            print_summary(report)
            return 0 if report.get("ok") else 6
        if args.command == "retry":
            return retry_role(args.role, args.execute_update, args.hours)
    except KeyboardInterrupt:
        print("Interrupted by operator. No automatic rollback executed.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
