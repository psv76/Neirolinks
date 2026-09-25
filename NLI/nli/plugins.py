"""Trusted component policies. Manifest data cannot weaken these checks."""
import re
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
        pass  # legacy manifest controls are metadata, never install gates


class HHM(Files):
    device_prefixes = ('HHM3', 'hhm3', 'NL_simple_thermostat_', 'NL_combo_thermostat_', 'heat_diagnostics')
    def validate(self, m, registration):
        require(m["component"] == "hhm" and m["object"] == "05_31_Ivolga_13", "Wrong HHM object")
        require(m["role"] in ("boiler", "gazebo"), "Wrong HHM role")
        targets = {f["target"] for f in m["files"]}
        require(targets == (BOILER if m["role"] == "boiler" else GAZEBO), "Incomplete/wrong-role HHM payload")
        require(m["services"] == {"stop": ["wb-rules"], "start": ["wb-rules"]}, "HHM only controls wb-rules")
        require(m["preflight"] == ["identity", "drift", "hhm"], "HHM preflight cannot be omitted")

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
        # Installation only. No application controls, frames or health contracts.
        self.inventory(engine, m)


class PressureMakeup(Files):
    device_prefixes = ('pressure_makeup', '507_Pressure_makeup')
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
        engine.rules_inventory(m)


PLUGINS = {"hhm": HHM(), "pressure_makeup": PressureMakeup(), "files": Files()}
