"""Real WB read probes and tightly bounded service operations."""
import os
import math
from pathlib import Path
import socket
import subprocess
import time
from .util import Error, require


class System:
    hostname = staticmethod(socket.gethostname)

    def run(self, argv, timeout=30):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False,
                               env={**os.environ, "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Error(str(exc)) from exc
        require(p.returncode == 0, "Command failed: " + " ".join(argv) + ": " + p.stderr.strip())
        return p.stdout.strip()

    def active(self, service):
        self.run(["/usr/bin/systemctl", "is-active", "--quiet", service])

    def service(self, action, service):
        require(action in ("start", "stop") and service in ("wb-rules", "wb-mqtt-serial"), "Unsafe service action")
        self.run(["/usr/bin/systemctl", action, service], timeout=45)
        if action == "start":
            deadline = time.monotonic() + 30
            while True:
                try:
                    self.active(service)
                    return
                except Error:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)

    def mqtt(self, topic, fresh=False, timeout=None):
        require(topic.startswith(("/devices/", "/neiro/")) and not topic.endswith("/on"), "Unsafe MQTT probe")
        budget = 18 if timeout is None else min(18, timeout)
        require(budget > 0, "MQTT probe deadline expired")
        wait = 15 if timeout is None else max(1, min(15, math.ceil(budget)))
        args = ["/usr/bin/mosquitto_sub", "-h", "127.0.0.1", "-t", topic, "-C", "1", "-W", str(wait)]
        if fresh:
            args.append("-R")
        return self.run(args, timeout=budget)

    def control(self, path, timeout=None):
        device, control = path.split("/", 1)
        return self.mqtt("/devices/" + device + "/controls/" + control, timeout=timeout)

    def journal(self, since=None):
        require(isinstance(since, str) and bool(since), "Explicit journal observation boundary required")
        return self.run(["/usr/bin/journalctl", "-u", "wb-rules", "--since", since,
                         "--no-pager", "-o", "cat"], timeout=30)

    def rules_version(self):
        version = self.run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", "wb-rules"])
        self.run(["/usr/bin/dpkg", "--compare-versions", version, "ge", "2.42.0"])
        return version

    def rule_started(self, marker, since=None):
        # 507 schedules its ordinary startup at +3 s. Wait only for observed log,
        # never execute a rule, publish MQTT or manipulate its runtime state.
        deadline = time.monotonic() + 15
        while True:
            if marker in self.journal(since):
                return
            require(time.monotonic() < deadline, "Missing rule startup marker: " + marker)
            time.sleep(0.5)

    def firmware_busy(self):
        require(Path("/proc").is_dir(), "Cannot inspect updater processes")
        found = []
        for path in Path("/proc").glob("[0-9]*/cmdline"):
            if path.parent.name == str(os.getpid()):
                continue
            try:
                args = path.read_bytes().split(b"\0")
            except FileNotFoundError:
                continue
            except PermissionError as exc:
                raise Error("Cannot establish updater exclusivity") from exc
            if any(Path(a.decode(errors="replace")).name in
                   ("wb-mcu-fw-updater", "wb-mcu-fw-flasher") for a in args[:3]):
                found.append(path.parent.name)
        return found
