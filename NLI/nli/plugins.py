"""Trusted component policies. Manifest data cannot weaken these checks."""
import json
import re
import time
from .util import digest, require

COMMON = {"/etc/wb-rules-modules/" + name + ".js" for name in
          ("HHM3Config", "HHM3Wire", "HHM3Runtime")}
BOILER = COMMON | {"/etc/wb-rules-modules/" + name + ".js" for name in
                   ("HHM3Circuit", "HHM3Mixing", "HHM3Outputs")} | {
    "/etc/wb-rules/500_HHM3_FSE.js", "/etc/wb-rules/620_thermostats.js",
    "/etc/wb-rules/600_Heat_diagnostics.js"}
GAZEBO = COMMON | {"/etc/wb-rules/624_combo_besedka.js"}


class Files:
    def validate(self, m, registration):
        allowed = registration.get("allowed_targets", [])
        require(all(f["target"] in allowed for f in m["files"]), "Target outside local component whitelist")
        require(all(f["target"].startswith("/etc/neiro/components/" + m["component"] + "/")
                    for f in m["files"]), "Generic component target outside its namespace")
        require(m["services"] == {"stop": [], "start": []}, "Generic files plugin cannot control services")
        require(m["preflight"] == ["identity", "drift"], "Invalid files policy")

    def preflight(self, engine, m, recovery=False):
        pass

    def verify(self, engine, m, since=None):
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
        managed = {f["target"] for f in m["files"]}
        approved = engine.config["components"]["hhm"].get("unmanaged_rules", {})
        # Conservative allowlist: unknown code may hide a computed second writer.
        # Includes modules as well as rules; does not claim to prove remote MQTT ACLs.
        for directory in ("/etc/wb-rules", "/etc/wb-rules-modules"):
            folder = engine.target(directory)
            require(folder.is_dir(), "Missing rules directory")
            for path in folder.rglob("*"):
                target = directory + "/" + path.relative_to(folder).as_posix()
                engine.target(target)  # reject symlink, including 507 (never read into backup)
                if path.suffix != ".js" or path.is_dir():
                    continue
                if target not in managed:
                    require(target in approved and digest(path.read_bytes()) == approved[target],
                            "Unknown/drifted possible writer: " + target)

    def preflight(self, engine, m, recovery=False):
        engine.system.rules_version()
        engine.system.active("wb-mqtt-serial")  # probe only, never stop this for HHM
        if not recovery:
            engine.system.active("wb-rules")
        if m["role"] == "boiler":
            for control in ("pressure_makeup/active", "A04/K1"):
                require(engine.system.control(control) == "0", "HHM blocked: " + control + " not confirmed OFF")
        self.inventory(engine, m)

    def verify(self, engine, m, since=None):
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


PLUGINS = {"hhm": HHM(), "files": Files()}
