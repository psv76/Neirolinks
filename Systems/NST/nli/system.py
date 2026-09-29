"""Real WB read probes and tightly bounded service operations."""
import os
import math
from pathlib import Path
import socket
import subprocess
import shutil
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

    def service_state(self, service):
        require(service in ("wb-rules", "wb-mqtt-serial"), "Unsafe service probe")
        try:
            value = self.run(["/usr/bin/systemctl", "is-active", service])
            return value or "unknown"
        except Error:
            return "inactive"

    def diagnostic_info(self):
        os_release = {}
        try:
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
                        os_release[key] = value.strip().strip('"')
        except OSError:
            pass
        uptime = None
        try:
            uptime = float(Path("/proc/uptime").read_text(encoding="ascii").split()[0])
        except (OSError, ValueError, IndexError):
            pass
        packages = {}
        for package in ("neiro-nst", "neiro-nli", "wb-rules", "wb-mqtt-db", "wb-mqtt-serial"):
            try:
                packages[package] = self.run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", package])
            except Error:
                packages[package] = None
        return {
            "os": os_release,
            "uptime_seconds": uptime,
            "packages": packages,
            "resources": self.resources(),
        }

    def resources(self):
        usage = shutil.disk_usage("/mnt/data" if Path("/mnt/data").exists() else "/")
        mem = {}
        try:
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    if key in ("MemTotal", "MemAvailable"):
                        mem[key] = int(value.strip().split()[0]) * 1024
        except (OSError, ValueError):
            pass
        return {
            "status": "ok",
            "disk": {"total": usage.total, "used": usage.used, "free": usage.free},
            "memory": {
                "total": mem.get("MemTotal"),
                "available": mem.get("MemAvailable"),
            },
        }

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

    def journal_disk_usage(self):
        return {"status": "ok", "summary": self.run(["/usr/bin/journalctl", "--disk-usage"], timeout=15)}

    def journal_unit(self, unit, since, until):
        require(unit in ("wb-rules", "wb-mqtt-db", "wb-mqtt-serial"), "Unsafe journal unit")
        require(isinstance(since, str) and since and isinstance(until, str) and until,
                "Explicit journal window required")
        return self.run(["/usr/bin/journalctl", "-u", unit, "--since", since, "--until", until,
                         "--no-pager", "-o", "short-iso"], timeout=45)

    def history(self, channels, since, until, limit):
        require(type(channels) is list and channels and all(isinstance(c, str) and "/" in c for c in channels),
                "Invalid MQTT history channels")
        require(type(limit) is int and 1 <= limit <= 100000, "Invalid MQTT history limit")
        args = ["/usr/bin/wb-mqtt-db-cli", "-b", "tcp://127.0.0.1:1883",
                "--from", since, "--to", until, "--limit", str(limit), "-a", "-d;"]
        args.extend(channels)
        return self.run(args, timeout=60)

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
