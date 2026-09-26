#!/usr/bin/env python3
"""Temporary field helper for 05_31 Ivolga HHM 3.1 controlled retry.

Stdlib-only orchestration around existing WB tools. Read-only by default.
Operational policy from 26.09.2026: NLI is the standard installer/updater on every
managed WB. Boiler already has NLI 0.1.9; gazebo is migrated to NLI before the
HHM 3.1 update. Manual replacement of managed HHM files is not a normal path.
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
NLI_RELEASE_TAG = "nli-approved-0.1.9"
NLI_BOOTSTRAP_SHA256 = "fb46edd0071dbe7c1c410f65dce97af66d1e96a23465a9da6895d189fc0e634c"
NLI_PACKAGE_SHA256 = "5042800dc01507742904b039d6d6539038255067aeec5b88603508bba5e718d5"
NLI_BOOTSTRAP_URL = f"https://github.com/{REPO}/releases/download/{NLI_RELEASE_TAG}/install-nli.py"
RAW = f"https://raw.githubusercontent.com/{REPO}/{PR_HEAD}"
EVIDENCE_ROOT = Path("/mnt/data/var/log/neiro/hhm31-field-retry")
ETC_ROOT = Path("/mnt/data/etc")
WB_RULES_DIR = ETC_ROOT / "wb-rules"
WB_MODULES_DIR = ETC_ROOT / "wb-rules-modules"
WB_MQTT_DB_CONFIG = ETC_ROOT / "wb-mqtt-db.conf"
WB_MQTT_SERIAL_CONFIG = ETC_ROOT / "wb-mqtt-serial.conf"
NLI_CONFIG = ETC_ROOT / "neiro/nli/config.json"
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
GAZEBO_FRAME_TOPIC = "/neiro/ivolga/504/v2/frame"
GAZEBO_LIVE_BASELINE_COMMIT = "837b2c6da31275cdb8964373f73b070fbbd31d6a"
GAZEBO_LIVE_BASELINE_VERSION = "3.0.0-FSE+837b2c6da312"
GAZEBO_LIVE_BASELINE_FILES = {
    "/etc/wb-rules-modules/HHM3Config.js": "99f7d993c2060015dd2e90f91d755597f0393d049c7904f31baf398b1bed5faf",
    "/etc/wb-rules-modules/HHM3Runtime.js": "9c6a71d2db52f37177ab8cd8a899c8ec2ade8987367eeecf80f731973df776d3",
    "/etc/wb-rules-modules/HHM3Wire.js": "b35baa255c4948f8ec926943efeee1ac5a29b594d508112478e8be4ea1360ada",
    "/etc/wb-rules/624_combo_besedka.js": "fd17a68d6b707df00ec752d7d650182c75361647ad099de26591d0acdf636c4a",
}

ROLE_RUNTIME_FILES = {
    "gazebo": [
        WB_RULES_DIR / "624_combo_besedka.js",
        WB_MODULES_DIR / "HHM3Config.js",
        WB_MODULES_DIR / "HHM3Wire.js",
        WB_MODULES_DIR / "HHM3Runtime.js",
    ],
    "boiler": [
        WB_RULES_DIR / "500_HHM3_FSE.js",
        WB_RULES_DIR / "600_Heat_diagnostics.js",
        WB_RULES_DIR / "620_thermostats.js",
        WB_MODULES_DIR / "HHM3Circuit.js",
        WB_MODULES_DIR / "HHM3Config.js",
        WB_MODULES_DIR / "HHM3Mixing.js",
        WB_MODULES_DIR / "HHM3Outputs.js",
        WB_MODULES_DIR / "HHM3Runtime.js",
        WB_MODULES_DIR / "HHM3Wire.js",
    ],
}

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


def round_template_005(value: float) -> float:
    """Match HHM/WB template rounding: sign * Math.round(abs(value) / 0.05) * 0.05."""
    sign = -1.0 if value < 0 else 1.0
    rounded = sign * math.floor(abs(value) / 0.05 + 0.5) * 0.05
    return float(f"{rounded:.2f}")


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
    p = WB_MQTT_DB_CONFIG
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


def bootstrap_nli(execute: bool) -> Dict[str, Any]:
    if not execute:
        raise RuntimeError("NLI bootstrap changes rootfs package state; pass --execute-install")
    if os.geteuid() != 0:
        raise RuntimeError("NLI bootstrap must run as root")
    before = {n: service_state(n) for n in ("wb-rules", "wb-mqtt-serial")}
    current = nli_version()
    if current == NLI_VERSION:
        return {"ok": True, "already_installed": True, "version": current,
                "package_sha256": NLI_PACKAGE_SHA256, "services_before": before,
                "services_after": {n: service_state(n) for n in before}}
    if current is not None:
        raise RuntimeError(f"NLI {current} already installed; use reviewed self-update path instead of bootstrap")
    req = urllib.request.Request(NLI_BOOTSTRAP_URL, headers={"User-Agent": "hhm31-field-retry/1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(2 * 1024 * 1024)
    actual = sha256(data)
    if actual != NLI_BOOTSTRAP_SHA256:
        raise RuntimeError(f"NLI bootstrap SHA mismatch: {actual}")
    fd, tmp = tempfile.mkstemp(prefix="install-nli-", suffix=".py", dir="/tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        check = run(["python3", tmp, "--check"], timeout=90)
        expected_check = (
            check.returncode == 0 and
            ("Последний approved NLI: " + NLI_VERSION) in check.stdout and
            ("SHA256: " + NLI_PACKAGE_SHA256) in check.stdout
        )
        if not expected_check:
            raise RuntimeError("approved NLI catalog changed or bootstrap check failed: " +
                               (check.stdout + check.stderr).strip())
        cp = run(["python3", tmp], timeout=180)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    after_version = nli_version()
    after = {n: service_state(n) for n in before}
    unchanged = all(
        before[n].get("ActiveEnterTimestamp") == after[n].get("ActiveEnterTimestamp")
        for n in before
    )
    ok = cp.returncode == 0 and after_version == NLI_VERSION and unchanged
    return {
        "ok": ok,
        "already_installed": False,
        "version": after_version,
        "bootstrap_sha256": actual,
        "package_sha256": NLI_PACKAGE_SHA256,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
        "services_before": before,
        "services_after": after,
        "service_start_timestamps_unchanged": unchanged,
    }


def logical_rule_path(path: Path) -> str:
    rel = path.relative_to(ETC_ROOT).as_posix()
    return "/etc/" + rel


def adoption_inventory(role: str) -> Dict[str, Any]:
    managed_expected = set()
    if role == "gazebo":
        managed_expected = set(GAZEBO_LIVE_BASELINE_FILES)
    else:
        managed_expected = {
            logical_rule_path(p) for p in ROLE_RUNTIME_FILES["boiler"]
        }
    entries = []
    for directory in (WB_RULES_DIR, WB_MODULES_DIR):
        if not directory.is_dir():
            continue
        for p in sorted(directory.rglob("*.js")):
            if not p.is_file():
                continue
            logical = logical_rule_path(p)
            data = p.read_bytes()
            entries.append({
                "logical_path": logical,
                "persistent_path": str(p),
                "sha256": sha256(data),
                "size": len(data),
                "managed_candidate": logical in managed_expected,
            })
    managed = [x for x in entries if x["managed_candidate"]]
    unmanaged = [x for x in entries if not x["managed_candidate"]]
    baseline_match = None
    baseline_mismatches: List[Dict[str, Any]] = []
    if role == "gazebo":
        got = {x["logical_path"]: x["sha256"] for x in managed}
        baseline_mismatches = [
            {"path": path, "expected": expected, "actual": got.get(path)}
            for path, expected in GAZEBO_LIVE_BASELINE_FILES.items()
            if got.get(path) != expected
        ]
        baseline_match = not baseline_mismatches
    return {
        "ok": bool(entries) and (baseline_match is not False),
        "time": now_iso(),
        "role": role,
        "hostname": run(["hostname"], timeout=3).stdout.strip(),
        "canonical_etc_root": str(ETC_ROOT),
        "nli_version": nli_version(),
        "nli_config_exists": NLI_CONFIG.is_file(),
        "managed_candidate_count": len(managed),
        "unmanaged_count": len(unmanaged),
        "managed_candidates": managed,
        "unmanaged_rules": unmanaged,
        "gazebo_live_baseline_commit": GAZEBO_LIVE_BASELINE_COMMIT if role == "gazebo" else None,
        "gazebo_live_baseline_match": baseline_match,
        "gazebo_live_baseline_mismatches": baseline_mismatches,
    }


def service_state(name: str) -> Dict[str, Any]:
    cp = run(["systemctl", "show", name, "-p", "ActiveState", "-p", "SubState",
              "-p", "ActiveEnterTimestamp"], timeout=5)
    result: Dict[str, Any] = {"returncode": cp.returncode}
    for line in cp.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


def file_inventory(role: str) -> Dict[str, Any]:
    files = []
    missing = []
    for p in ROLE_RUNTIME_FILES[role]:
        item: Dict[str, Any] = {"path": str(p), "exists": p.is_file()}
        if p.is_file():
            data = p.read_bytes()
            item.update(size=len(data), sha256=sha256(data))
        else:
            missing.append(str(p))
        files.append(item)
    configs = {}
    for name, p in (("wb-mqtt-db", WB_MQTT_DB_CONFIG), ("wb-mqtt-serial", WB_MQTT_SERIAL_CONFIG)):
        configs[name] = {"path": str(p), "exists": p.is_file()}
        if p.is_file():
            data = p.read_bytes()
            configs[name].update(size=len(data), sha256=sha256(data))
    return {"ok": not missing, "files": files, "missing": missing, "configs": configs,
            "canonical_etc_root": str(ETC_ROOT)}


def gazebo_frame_probe(seconds: float = 7.0) -> Dict[str, Any]:
    raw = snapshot_topics([GAZEBO_FRAME_TOPIC], seconds=seconds)
    payload = raw.get(GAZEBO_FRAME_TOPIC)
    if payload is None:
        return {"ok": False, "topic": GAZEBO_FRAME_TOPIC, "error": "no live frame observed"}
    try:
        frame = json.loads(payload)
    except json.JSONDecodeError:
        return {"ok": False, "topic": GAZEBO_FRAME_TOPIC, "error": "frame is not JSON", "payload": payload}
    now_ms = int(time.time() * 1000)
    sent_ms = numeric(frame.get("sent_ms"))
    ttl_ms = numeric(frame.get("ttl_ms"))
    age_ms = None if sent_ms is None else now_ms - sent_ms
    fresh = (age_ms is not None and ttl_ms is not None and age_ms >= -2000 and age_ms <= ttl_ms)
    ok = (frame.get("source") == "ivolga-besedka-504" and
          isinstance(frame.get("session_id"), (int, float)) and
          isinstance(frame.get("seq"), (int, float)) and
          frame.get("ttl_ms") == 30000 and fresh)
    return {"ok": bool(ok), "topic": GAZEBO_FRAME_TOPIC, "frame": frame,
            "age_ms": age_ms, "fresh": fresh}


def nli_call(args: List[str], timeout: int = 120) -> Dict[str, Any]:
    if shutil.which("nli") is None:
        return {"available": False, "returncode": 127, "stdout": "", "stderr": "nli command not found", "json": None}
    cp = run(["nli", "--json"] + args, timeout=timeout)
    result: Dict[str, Any] = {"available": True, "returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    try:
        result["json"] = json.loads(cp.stdout)
    except json.JSONDecodeError:
        result["json"] = None
    return result


def nli_version() -> Optional[str]:
    if shutil.which("nli") is None:
        return None
    cp = run(["nli", "--json", "--version"], timeout=5)
    try:
        return str(json.loads(cp.stdout).get("version"))
    except Exception:
        cp2 = run(["nli", "--version"], timeout=5)
        m = re.search(r"(\d+\.\d+\.\d+)", cp2.stdout + cp2.stderr)
        return m.group(1) if m else None


def port_load_probe(sensor_path: str, reference_temp: Optional[float] = None) -> Dict[str, Any]:
    """Prove serial-read capability without requiring a fresh MQTT publication.

    An unchanged healthy M1W2 may be silent on MQTT; that is the cold-start
    condition under test. If a current MQTT value is observed, it is used as an
    extra consistency check. A caller may also pass a fresh application-frame
    temperature as the local reference.
    """
    m = re.search(r"/External Sensor ([12])$", sensor_path)
    if not m:
        return {"ok": False, "error": "unsupported sensor path"}
    input_no = int(m.group(1))
    device = sensor_path.split("/", 1)[0]
    health = sensor_path + " OK"
    snap = snapshot_controls([sensor_path, health])
    local_temp = numeric(snap[sensor_path]["value"])
    local_ok = snap[health]["value"]
    for p in (sensor_path, health):
        err = snap[p].get("error")
        if err not in (None, "", 0, False):
            return {"ok": False, "error": f"local control error on {p}: {err}", "snapshot": snap}
    if snap[health].get("value_seen") and not is_ok(local_ok):
        return {"ok": False, "error": "observed local OK is not healthy", "snapshot": snap}

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
    rounded = round_template_005(bus_temp)
    if local_temp is not None and local_temp not in (bus_temp, rounded):
        return {"ok": False, "error": "bus/current-MQTT temperature mismatch", "bus_temp": bus_temp,
                "local_temp": local_temp, "reply": r1, "snapshot": snap}
    if reference_temp is not None:
        ref = numeric(reference_temp)
        if ref is None or ref not in (bus_temp, rounded):
            return {"ok": False, "error": "bus/reference temperature mismatch", "bus_temp": bus_temp,
                    "reference_temp": reference_temp, "reply": r1, "snapshot": snap}

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
            "local_ok": local_ok, "reference_temp": reference_temp,
            "mqtt_value_seen": snap[sensor_path].get("value_seen"),
            "mqtt_ok_seen": snap[health].get("value_seen"),
            "temperature_rtt_ms": round(ms1, 1), "health_rtt_ms": round(ms2, 1),
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


def preflight_role(role: str, hours: int = 24, save: bool = True,
                   include_history: bool = True, require_nli: bool = False) -> Dict[str, Any]:
    report: Dict[str, Any] = {"time": now_iso(), "role": role, "object": OBJECT, "checks": {}}
    checks = report["checks"]
    checks["hostname"] = run(["hostname"], timeout=3).stdout.strip()
    checks["packages"] = {"wb-rules": package_version("wb-rules"),
                          "wb-mqtt-serial": package_version("wb-mqtt-serial")}
    checks["services"] = {n: service_state(n) for n in ("wb-rules", "wb-mqtt-serial", "wb-mqtt-db")}
    checks["runtime_inventory"] = file_inventory(role)

    nli_required = role == "boiler" or require_nli
    checks["nli_expected"] = nli_required
    checks["nli_present"] = shutil.which("nli") is not None
    if nli_required:
        checks["nli_version"] = nli_version()
        checks["nli_status"] = nli_call(["status"], timeout=20)
        checks["nli_verify_hhm"] = nli_call(["verify", "hhm"], timeout=30)
        if role == "boiler":
            checks["nli_verify_pressure_makeup"] = nli_call(["verify", "pressure_makeup"], timeout=30)
    else:
        checks["nli_note"] = "NLI not required for this pre-adoption hardware preflight"

    if role == "gazebo":
        checks["air_sensor"] = snapshot_controls([GAZEBO_AIR], include_errors=True)[GAZEBO_AIR]
        checks["frame_probe"] = gazebo_frame_probe()
        frame = (checks["frame_probe"].get("frame") or {}) if checks["frame_probe"].get("ok") else {}
        floor_ref = numeric(frame.get("floor"))
        checks["port_load_probe"] = port_load_probe(GAZEBO_FLOOR, reference_temp=floor_ref)
        air_now = numeric(checks["air_sensor"].get("value"))
        air_ok = air_now is not None and -20 <= air_now <= 60 and checks["air_sensor"].get("error") in (None, "", 0, False)
        port_ok = checks["port_load_probe"].get("ok") is True
        frame_reason = frame.get("reason")
        frame_valid = frame.get("valid") is True
        reproduced_old_false_invalid = (
            checks["frame_probe"].get("ok") is True and
            frame_valid is False and
            frame_reason == "FLOOR_SENSOR_INVALID" and
            floor_ref is None and
            air_ok and port_ok
        )
        checks["sensor_health"] = {
            "ok": bool(port_ok and air_ok),
            "source": "port_load_plus_air",
            "air_ok": air_ok,
            "frame_valid": frame_valid,
            "frame_reason": frame_reason,
            "frame_floor": floor_ref,
            "old_runtime_false_invalid_reproduced": reproduced_old_false_invalid,
            "mqtt_snapshot": snapshot_controls([GAZEBO_FLOOR, GAZEBO_FLOOR + " OK"]),
            "note": "pre-deploy hardware gate is port/Load + healthy air; old 624 false FLOOR_SENSOR_INVALID is evidence, not a hardware failure",
        }
    else:
        checks["sensor_health"] = current_sensor_health(role)
        checks["port_load_probe"] = port_load_probe("wb-m1w2_170/External Sensor 1")
    checks["history"] = history_role(role, hours=hours, save=False) if include_history else {
        "skipped": True,
        "reason": "already collected separately",
        "recommended_stability_s": 600 if role == "gazebo" else 180,
    }

    failures = []
    for svc in ("wb-rules", "wb-mqtt-serial"):
        if checks["services"][svc].get("ActiveState") != "active":
            failures.append(f"{svc} is not active")
    if not checks["runtime_inventory"]["ok"]:
        failures.extend("missing runtime file: " + p for p in checks["runtime_inventory"]["missing"])

    if nli_required:
        if checks["nli_version"] != NLI_VERSION:
            failures.append(f"NLI version is {checks['nli_version']}, expected {NLI_VERSION}")
        if checks["nli_status"]["returncode"] != 0:
            failures.append("nli status failed")
        elif isinstance(checks["nli_status"].get("json"), dict) and checks["nli_status"]["json"].get("pending") is not None:
            failures.append("NLI has a pending mutation; recovery required before retry")
        if checks["nli_verify_hhm"]["returncode"] != 0:
            failures.append("nli verify hhm failed")
        if role == "boiler" and checks["nli_verify_pressure_makeup"]["returncode"] != 0:
            failures.append("nli verify pressure_makeup failed")
    if role == "gazebo":
        if not checks["frame_probe"].get("ok"):
            failures.append("gazebo live frame probe failed: " + str(checks["frame_probe"].get("error")))
        if not (checks.get("air_sensor") or {}).get("value_seen"):
            failures.append("gazebo air sensor not observed")
        elif not checks["sensor_health"].get("air_ok"):
            failures.append("gazebo air sensor is not healthy/in-range")

    if not checks["sensor_health"]["ok"]:
        if role == "gazebo":
            failures.append("gazebo floor hardware proof failed")
        else:
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


def retry_manifest_path(role: str) -> Path:
    return RELEASE_DIR / f"hhm-{role}-3.1-retry-{PR_HEAD[:12]}.json"


def staged_target_matches(cfg: Dict[str, Any], role: str) -> bool:
    try:
        target = cfg["components"]["hhm"]["target"]
    except (KeyError, TypeError):
        return False
    return (cfg.get("object") == OBJECT and cfg.get("role") == role and
            cfg.get("release_source") == "pinned" and
            target.get("path") == str(retry_manifest_path(role)) and
            target.get("sha256") == MANIFESTS[role]["sha256"])


def nli_pending() -> Tuple[bool, Dict[str, Any]]:
    status = nli_call(["status"], timeout=20)
    if status["returncode"] != 0 or not isinstance(status.get("json"), dict):
        raise RuntimeError("cannot verify NLI pending state before config restore")
    return status["json"].get("pending") is not None, status


def restore_staging(role: str, require_staged_current: bool = True, check_pending: bool = True) -> Dict[str, Any]:
    if not NLI_CONFIG_BACKUP.is_file():
        raise RuntimeError("staging backup not found; refusing to guess original config")
    backup = NLI_CONFIG_BACKUP.read_bytes()
    backup_cfg = json.loads(backup)
    if backup_cfg.get("object") != OBJECT or backup_cfg.get("role") != role:
        raise RuntimeError("backup config identity mismatch")
    status: Dict[str, Any] = {}
    if check_pending:
        pending, status = nli_pending()
        if pending:
            raise RuntimeError("NLI has a pending mutation; refusing to change target config")
    current_cfg = json.loads(NLI_CONFIG.read_bytes()) if NLI_CONFIG.is_file() else {}
    if require_staged_current and not staged_target_matches(current_cfg, role):
        raise RuntimeError("current NLI config no longer matches helper staging; refusing to overwrite it")
    retry_manifest = retry_manifest_path(role)
    if retry_manifest.exists():
        manifest_bytes = retry_manifest.read_bytes()
        if sha256(manifest_bytes) != MANIFESTS[role]["sha256"]:
            raise RuntimeError("retry manifest drift detected; refusing cleanup")
    atomic_write(NLI_CONFIG, backup, 0o600)
    removed = []
    if retry_manifest.exists():
        retry_manifest.unlink()
        removed.append(str(retry_manifest))
    NLI_CONFIG_BACKUP.unlink()
    return {"ok": True, "restored": str(NLI_CONFIG), "removed": removed, "nli_status": status}


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
    pending, _ = nli_pending()
    if pending:
        raise RuntimeError("NLI has a pending mutation; refusing to stage a new target")
    retry_manifest = retry_manifest_path(role)

    if NLI_CONFIG_BACKUP.exists():
        if not staged_target_matches(cfg, role):
            raise RuntimeError("staging backup already exists but current config is not this exact staged target; resolve it before retry")
        if not retry_manifest.is_file() or sha256(retry_manifest.read_bytes()) != MANIFESTS[role]["sha256"]:
            raise RuntimeError("existing staged manifest is missing or has drift")
        check = nli_call(["check", "hhm"], timeout=120)
        return {"ok": check["returncode"] == 0, "already_staged": True,
                "manifest": str(retry_manifest), "manifest_sha256": MANIFESTS[role]["sha256"],
                "nli_check": check, "backup": str(NLI_CONFIG_BACKUP),
                "runtime_commit": manifest["release"]["commit"]}

    created = False
    try:
        atomic_write(NLI_CONFIG_BACKUP, cfg_bytes, 0o600)
        created = True
        atomic_write(retry_manifest, data, 0o644)
        cfg["release_source"] = "pinned"
        cfg["components"]["hhm"]["target"] = {"path": str(retry_manifest), "sha256": MANIFESTS[role]["sha256"]}
        atomic_write(NLI_CONFIG, (json.dumps(cfg, ensure_ascii=False, indent=2) + "\n").encode(), 0o600)
        check = nli_call(["check", "hhm"], timeout=120)
        if check["returncode"] != 0:
            restored = restore_staging(role, check_pending=False)
            return {"ok": False, "manifest": str(retry_manifest),
                    "manifest_sha256": MANIFESTS[role]["sha256"], "nli_check": check,
                    "restored_after_failed_check": restored, "runtime_commit": manifest["release"]["commit"]}
        return {"ok": True, "manifest": str(retry_manifest),
                "manifest_sha256": MANIFESTS[role]["sha256"], "nli_check": check,
                "backup": str(NLI_CONFIG_BACKUP), "runtime_commit": manifest["release"]["commit"]}
    except BaseException:
        if created and NLI_CONFIG_BACKUP.exists():
            try:
                restore_staging(role, require_staged_current=False, check_pending=False)
            except Exception as cleanup_exc:
                print(f"WARNING: staging cleanup failed: {cleanup_exc}", file=sys.stderr)
        raise


def unstage(execute: bool) -> Dict[str, Any]:
    if not execute:
        raise RuntimeError("unstage requires --execute")
    if os.geteuid() != 0:
        raise RuntimeError("unstage must run as root")
    if not NLI_CONFIG_BACKUP.is_file():
        raise RuntimeError("staging backup not found; refusing to guess original config")
    backup_cfg = json.loads(NLI_CONFIG_BACKUP.read_bytes())
    role = backup_cfg.get("role")
    if role not in MANIFESTS:
        raise RuntimeError("backup role is not a supported retry role")
    return restore_staging(role)


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
        return [control_topic(p) for p in paths] + [GAZEBO_FRAME_TOPIC]
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
        if role == "boiler":
            verify = nli_call(["verify", "hhm"], timeout=40)
            report["nli_verify_hhm"] = verify
            report["nli_verify_pressure_makeup"] = nli_call(["verify", "pressure_makeup"], timeout=40)
            if verify["returncode"] != 0:
                report.update(ok=False, failure="nli verify hhm failed")
                return report
        else:
            report["nli_expected"] = False
            report["nli_note"] = "gazebo smoke is runtime-only; live baseline has no NLI"

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
            hist = history_role("boiler", hours=24, save=False) if stability_s is None else {
                "skipped": True,
                "reason": "stability interval supplied by caller",
                "recommended_stability_s": stability_s,
            }
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


def print_history_summary(report: Dict[str, Any]) -> None:
    summary: Dict[str, Any] = {
        "role": report.get("role"),
        "db_available": report.get("db_available"),
        "channel_count": report.get("channel_count"),
        "coverage": report.get("coverage"),
        "recommended_stability_s": report.get("recommended_stability_s"),
        "evidence_dir": report.get("evidence_dir"),
    }
    if report.get("role") == "gazebo":
        ts = report.get("historical_floor_invalid_timestamps") or []
        iv = report.get("historical_floor_invalid_intervals_s") or []
        summary["historical_floor_invalid_count"] = len(ts)
        summary["historical_interval_min_s"] = min(iv) if iv else None
        summary["historical_interval_max_s"] = max(iv) if iv else None
    else:
        bad = report.get("historical_bad_ok_records") or []
        summary["historical_bad_ok"] = report.get("historical_bad_ok")
        summary["historical_bad_ok_count"] = len(bad)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print("RESULT:", "PASS" if report.get("db_available") else "FAIL")
    if report.get("evidence_dir"):
        print("FULL_REPORT:", str(Path(report["evidence_dir"]) / "history.json"))


def print_preflight_summary(report: Dict[str, Any]) -> None:
    checks = report.get("checks") or {}
    services = checks.get("services") or {}
    inv = checks.get("runtime_inventory") or {}
    probe = checks.get("port_load_probe") or {}
    summary: Dict[str, Any] = {
        "role": report.get("role"),
        "hostname": checks.get("hostname"),
        "packages": checks.get("packages"),
        "services": {k: v.get("ActiveState") for k, v in services.items()},
        "canonical_etc_root": inv.get("canonical_etc_root"),
        "runtime_files_ok": inv.get("ok"),
        "runtime_files_missing": inv.get("missing"),
        "sensor_health_ok": (checks.get("sensor_health") or {}).get("ok"),
        "sensor_health_source": (checks.get("sensor_health") or {}).get("source"),
        "port_load_ok": probe.get("ok"),
        "port_load_temperature_rtt_ms": probe.get("temperature_rtt_ms"),
        "port_load_health_rtt_ms": probe.get("health_rtt_ms"),
        "nli_expected": checks.get("nli_expected"),
        "failures": report.get("failures") or [],
        "evidence_dir": report.get("evidence_dir"),
    }
    if report.get("role") == "gazebo":
        summary["nli_present_informational"] = checks.get("nli_present")
        summary["frame_probe_ok"] = (checks.get("frame_probe") or {}).get("ok")
        summary["frame_age_ms"] = (checks.get("frame_probe") or {}).get("age_ms")
        summary["frame_valid"] = (checks.get("sensor_health") or {}).get("frame_valid")
        summary["frame_reason"] = (checks.get("sensor_health") or {}).get("frame_reason")
        summary["old_runtime_false_invalid_reproduced"] = (checks.get("sensor_health") or {}).get("old_runtime_false_invalid_reproduced")
        mqtt_snap = (checks.get("sensor_health") or {}).get("mqtt_snapshot") or {}
        summary["mqtt_floor_value_seen"] = mqtt_snap.get(GAZEBO_FLOOR, {}).get("value_seen")
        summary["mqtt_floor_ok_seen"] = mqtt_snap.get(GAZEBO_FLOOR + " OK", {}).get("value_seen")
    else:
        summary["nli_version"] = checks.get("nli_version")
        hist = checks.get("history") or {}
        summary["recommended_stability_s"] = hist.get("recommended_stability_s")
        summary["history_skipped"] = hist.get("skipped", False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print("RESULT:", "PASS" if report.get("ok") else "FAIL")
    if report.get("evidence_dir"):
        print("FULL_REPORT:", str(Path(report["evidence_dir"]) / "preflight.json"))


def retry_role(role: str, execute_update: bool, hours: int = 24,
               include_history: bool = True, stability_override: Optional[int] = None) -> int:
    if not execute_update:
        raise RuntimeError("retry mutation requires --execute-update")
    if os.geteuid() != 0:
        raise RuntimeError("retry must run as root")
    root = evidence_dir(role, "retry")
    pre = preflight_role(role, hours=hours, save=False, include_history=include_history, require_nli=True)
    json_dump(root / "preflight.json", pre)
    print("PRECHECK:", "PASS" if pre.get("ok") else "FAIL")
    if not pre.get("ok"):
        print_preflight_summary(pre)
        return 2

    staged_ok = False
    update_started = False
    monitor: Optional[TopicMonitor] = None
    try:
        staged = stage_role(role)
        json_dump(root / "stage.json", staged)
        if not staged.get("ok"):
            print_summary({"ok": False, "failure": "NLI staged check failed; original target restored", "stage": staged})
            return 3
        staged_ok = True
        phrase = f"UPDATE {role.upper()}"
        print(f"About to run nli update hhm on {role}. Type exactly: {phrase}")
        if input("> ").strip() != phrase:
            restored = unstage(True)
            json_dump(root / "cancel-unstage.json", restored)
            print("Cancelled; original NLI target restored. No HHM update executed.")
            staged_ok = False
            return 4

        monitor = TopicMonitor(role_monitor_topics(role), root / "mqtt-events.tsv")
        monitor.start()
        update_epoch = time.time()
        update_started = True
        update = nli_call(["update", "hhm"], timeout=240)
        json_dump(root / "nli-update.json", update)
        print(update.get("stdout", ""), end="")
        if update["returncode"] != 0:
            print(update.get("stderr", ""), file=sys.stderr)
            print("NLI update failed. Do not start a second update automatically; inspect status/pending.")
            return 5
        stability = stability_override
        if stability is None:
            stability = (pre.get("checks", {}).get("history", {}) or {}).get("recommended_stability_s")
        if stability is None:
            stability = 600 if role == "gazebo" else 180
        smoke = smoke_role(role, update_epoch, stability_s=int(stability), monitor=monitor, evidence=root)
    except BaseException:
        if staged_ok and not update_started:
            try:
                restored = unstage(True)
                json_dump(root / "preupdate-exception-unstage.json", restored)
                print("Pre-update interruption: original NLI target restored.", file=sys.stderr)
            except Exception as cleanup_exc:
                print(f"WARNING: pre-update target restore failed: {cleanup_exc}", file=sys.stderr)
        raise
    finally:
        if monitor is not None:
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
    t("template rounding positive half", round_template_005(0.125) == 0.15)
    t("template rounding negative half", round_template_005(-0.125) == -0.15)
    t("boiler inventory", len(BOILER_ALL) == 19 and len(set(BOILER_ALL)) == 19)
    t("manager inventory", len(BOILER_MANAGER) == 9)
    t("house floors", len(HOUSE_FLOORS) == 9)
    t("expected boiler pair count", len(expected_pair_set("boiler")) == 28)
    t("manifest constants", len(MANIFESTS["boiler"]["sha256"]) == 64 and len(MANIFESTS["gazebo"]["sha256"]) == 64)
    t("canonical etc", str(ETC_ROOT) == "/mnt/data/etc")
    t("gazebo old baseline identity", GAZEBO_LIVE_BASELINE_COMMIT.startswith("837b2c6"))
    t("nli bootstrap pin", len(NLI_BOOTSTRAP_SHA256) == 64 and NLI_RELEASE_TAG == "nli-approved-0.1.9")
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
    pf.add_argument("--skip-history", action="store_true", help="do not query wb-mqtt-db again")
    pf.add_argument("--require-nli", action="store_true", help="require configured NLI 0.1.9 and verify hhm")
    bn = sub.add_parser("bootstrap-nli", help="install approved NLI 0.1.9 package; does not create object config or restart WB services")
    bn.add_argument("--execute-install", action="store_true")
    ai = sub.add_parser("adoption-inventory", help="read-only inventory for first NLI adoption")
    ai.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    st = sub.add_parser("stage", help="stage exact PR #73 manifest in existing configured NLI; no HHM update")
    st.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    st.add_argument("--execute", action="store_true")
    us = sub.add_parser("unstage", help="restore pre-retry NLI config from the helper backup")
    us.add_argument("--execute", action="store_true")
    sm = sub.add_parser("smoke", help="passive post-update functional smoke")
    sm.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    sm.add_argument("--since-epoch", type=float, default=None)
    sm.add_argument("--stability-seconds", type=int, default=None)
    rt = sub.add_parser("retry", help="preflight + stage + explicit existing-NLI update + passive smoke")
    rt.add_argument("--role", choices=["gazebo", "boiler"], required=True)
    rt.add_argument("--hours", type=int, default=24)
    rt.add_argument("--skip-history", action="store_true", help="reuse already-reviewed history; current checks still run")
    rt.add_argument("--stability-seconds", type=int, choices=[120, 180], default=None,
                    help="boiler post-update soak; use only from reviewed preflight/history")
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
            print_history_summary(report)
            return 0 if report.get("db_available") else 1
        if args.command == "preflight":
            report = preflight_role(args.role, hours=args.hours, save=True,
                                    include_history=not args.skip_history, require_nli=args.require_nli)
            print_preflight_summary(report)
            return 0 if report.get("ok") else 2
        if args.command == "bootstrap-nli":
            report = bootstrap_nli(args.execute_install)
            print_summary(report)
            return 0 if report.get("ok") else 2
        if args.command == "adoption-inventory":
            report = adoption_inventory(args.role)
            p = evidence_dir(args.role, "adoption-inventory")
            report["evidence_dir"] = str(p)
            json_dump(p / "adoption-inventory.json", report)
            compact = {
                "role": report["role"],
                "hostname": report["hostname"],
                "nli_version": report["nli_version"],
                "nli_config_exists": report["nli_config_exists"],
                "managed_candidate_count": report["managed_candidate_count"],
                "unmanaged_count": report["unmanaged_count"],
                "gazebo_live_baseline_match": report["gazebo_live_baseline_match"],
                "ok": report["ok"],
                "full_report": str(p / "adoption-inventory.json"),
            }
            print(json.dumps(compact, ensure_ascii=False, indent=2))
            print()
            print("RESULT:", "PASS" if report.get("ok") else "FAIL")
            return 0 if report.get("ok") else 2
        if args.command == "stage":
            if not args.execute:
                raise RuntimeError("stage changes persistent NLI target config; pass --execute")
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
            return retry_role(args.role, args.execute_update, args.hours,
                              include_history=not args.skip_history,
                              stability_override=args.stability_seconds)
    except KeyboardInterrupt:
        print("Interrupted by operator. No automatic rollback executed.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
