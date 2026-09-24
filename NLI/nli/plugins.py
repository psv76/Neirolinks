"""Trusted component policies. Manifest data cannot weaken these checks."""
import json
import re
import time
from .manifest import MAKEUP_TARGET
from .util import require

COMMON = {"/etc/wb-rules-modules/" + name + ".js" for name in
          ("HHM3Config", "HHM3Wire", "HHM3Runtime")}
BOILER = COMMON | {"/etc/wb-rules-modules/" + name + ".js" for name in
                   ("HHM3Circuit", "HHM3Mixing", "HHM3Outputs")} | {
    "/etc/wb-rules/500_HHM3_FSE.js", "/etc/wb-rules/620_thermostats.js",
    "/etc/wb-rules/600_Heat_diagnostics.js"}
GAZEBO = COMMON | {"/etc/wb-rules/624_combo_besedka.js"}


class Files:
    outputs = frozenset()

    def validate(self, m, registration):
        allowed = registration.get("allowed_targets", [])
        require(all(f["target"] in allowed for f in m["files"]), "Target outside local component whitelist")
        require(all(f["target"].startswith("/etc/neiro/components/" + m["component"] + "/")
                    for f in m["files"]), "Generic component target outside its namespace")
        require(m["services"] == {"stop": [], "start": []}, "Generic files plugin cannot control services")
        require(m["preflight"] == ["identity", "drift"], "Invalid files policy")

    def preflight(self, engine, m, recovery=False):
        pass

    def verify(self, engine, m, since=None, post_restart=False):
        for c in m["verify"]["controls"]:
            value = engine.system.control(c["path"])
            require(value != "" and ("equals" not in c or value == c["equals"]), "Control mismatch: " + c["path"])


class HHM(Files):
    def validate(self, m, registration):
        require(m["component"] == "hhm" and m["object"] == "05_31_Ivolga_13", "Wrong HHM object")
        require(m["role"] in ("boiler", "gazebo"), "Wrong HHM role")
        targets = {f["target"] for f in m["files"]}
        require(targets == (BOILER if m["role"] == "boiler" else GAZEBO), "Incomplete/wrong-role HHM payload")
        require(m["services"] == {"stop": ["wb-rules"], "start": ["wb-rules"]}, "HHM only controls wb-rules")
        require(m["preflight"] == ["identity", "drift", "hhm"], "HHM preflight cannot be omitted")
        version = m["verify"]["runtime_version"]
        require(re.fullmatch(r"3\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version), "Unknown HHM runtime version")
        require(m["version"] == version or m["version"].startswith(version + "+"), "Release/runtime version mismatch")
        health = m["verify"]["health_contract"]
        if not version.startswith("3.0."):
            require(health == "m1w2-health-v1", "HHM >= 3.1 requires sensor health contract")
            require(any(c["path"].endswith("/sensor_health_contract") and c.get("equals") == health
                        for c in m["verify"]["controls"]), "Missing health contract runtime attestation")
        else:
            require(health == "legacy-3.0", "Cannot claim HHM 3.1 health for 3.0")

    def inventory(self, engine, m):
        engine.rules_inventory(m)

    def preflight(self, engine, m, recovery=False):
        engine.system.rules_version()
        engine.system.active("wb-mqtt-serial")  # probe only, never stop this for HHM
        if not recovery:
            engine.system.active("wb-rules")
        if m["role"] == "boiler":
            for control in ("pressure_makeup/active", "A04/K1"):
                require(engine.system.control(control) == "0", "HHM blocked: " + control + " not confirmed OFF")
        self.inventory(engine, m)

    def verify(self, engine, m, since=None, post_restart=False):
        engine.system.active("wb-rules")
        self.inventory(engine, m)
        text = engine.target("/etc/wb-rules-modules/HHM3Config.js").read_text(encoding="utf-8")
        require(re.search(r"version\s*:\s*['\"]" + re.escape(m["verify"]["runtime_version"]) + r"['\"]", text),
                "HHM runtime version mismatch")
        topic = "/neiro/ivolga/hhm3/house/frame" if m["role"] == "boiler" else "/neiro/ivolga/504/v2/frame"
        frame = json.loads(engine.system.mqtt(topic, fresh=True))
        expected_source = "ivolga-hhm3-house" if m["role"] == "boiler" else "ivolga-besedka-504"
        require(type(frame) is dict and type(frame.get("sent_ms")) in (int, float)
                and -2000 <= time.time() * 1000 - frame["sent_ms"] < 30000,
                "Missing fresh HHM frame")
        require(frame.get("source") == expected_source and frame.get("v") == (3 if m["role"] == "boiler" else 2)
                and type(frame.get("seq")) is int and frame["seq"] > 0, "Wrong HHM runtime frame")
        required = (["HHM3_FSE/runtime_status", "HHM3_FSE/circuit_502", "heat_diagnostics/request_504"]
                    if m["role"] == "boiler" else ["NL_combo_thermostat_504/runtime_status", "NL_combo_thermostat_504/state"])
        for control in required:
            value = engine.system.control(control)
            require(value and not any(x in value for x in ("RUNTIME_UNSUPPORTED", "STARTUP", "Ожидание MQTT", "Запуск")),
                    "HHM runtime not loaded: " + control)
        super().verify(engine, m, since)
        journal = engine.system.journal(since)
        require(not re.search(r"SyntaxError|ReferenceError|TypeError|exception|ERROR|write ignored", journal, re.I),
                "wb-rules journal reports errors; inspect journal")


class PressureMakeup(Files):
    # Fixed trusted policy, never a manifest-supplied physical-output claim.
    outputs = frozenset({"A04/K1"})

    def validate(self, m, registration):
        require(m["component"] == "pressure_makeup" and m["object"] == "05_31_Ivolga_13"
                and m["role"] == "boiler", "Wrong pressure_makeup identity/role")
        require({f["target"] for f in m["files"]} == {MAKEUP_TARGET}, "pressure_makeup owns only 507")
        require(m["services"] == {"stop": ["wb-rules"], "start": ["wb-rules"]},
                "pressure_makeup only controls wb-rules")
        require(m["preflight"] == ["identity", "drift", "pressure_makeup"], "Missing pressure_makeup preflight")
        require(re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", m["version"]), "Invalid pressure_makeup release version")
        require(m["verify"]["runtime_version"] == m["version"] and m["verify"]["health_contract"] == "none",
                "Invalid pressure_makeup version contract")
        # Legacy version is attested by exact file hash, not a nonexistent runtime VD.
        require(m["verify"]["controls"] == [], "pressure_makeup verify policy is fixed")

    def preflight(self, engine, m, recovery=False):
        engine.system.rules_version()
        engine.system.active("wb-mqtt-serial")
        if not recovery:
            engine.system.active("wb-rules")
        for control in ("pressure_makeup/active", "A04/K1"):
            require(engine.system.control(control) == "0", "pressure_makeup blocked: " + control + " not confirmed OFF")
        engine.rules_inventory(m)

    def verify(self, engine, m, since=None, post_restart=False):
        engine.system.active("wb-rules")
        engine.rules_inventory(m)
        if post_restart:
            engine.system.rule_started("[507_Pressure_makeup] Запуск скрипта", since)
        # Reset counters/alarms and subsequent normal evaluate (including ON) are
        # accepted. Do not restore these runtime values or assert post-restart OFF.
        for cell in ("active", "valve_open", "enabled", "auto_mode", "sensor_alarm",
                     "low_pressure_alarm", "makeup_failed_alarm", "watchdog_alarm"):
            require(engine.system.control("pressure_makeup/" + cell) in ("0", "1"),
                    "Missing/invalid pressure_makeup control: " + cell)
        count = engine.system.control("pressure_makeup/pulse_count")
        require(re.fullmatch(r"[0-9]+", count) is not None, "Invalid pressure_makeup pulse_count")
        require(bool(engine.system.control("pressure_makeup/last_event")), "Missing pressure_makeup last_event")
        require(not re.search(r"SyntaxError|ReferenceError|TypeError|exception|ERROR|write ignored",
                              engine.system.journal(since), re.I), "wb-rules journal reports errors; inspect journal")


PLUGINS = {"hhm": HHM(), "pressure_makeup": PressureMakeup(), "files": Files()}
