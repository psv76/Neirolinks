"""Delegates flashing exclusively to the installed official updater, interactively."""
import os
import hashlib
from pathlib import Path
import re
import signal
import subprocess
import sys
from .util import Error, Lock, digest, require
from .layout import STATE_DIR, LOG_DIR

UPDATER = "/usr/bin/wb-mcu-fw-updater"
SUPPORTED = {'1.16.0': '91d705e6de165970d5a87669b34c7ed9c282364f'}
BOOTLOADER_NOTICE = ("Штатный updater может обновить bootloader и firmware; временно нарушить связь "
                     "с модулями и приостановить serial clients. Требуется инженер на объекте. "
                     "NLI не добавляет --force/--allow-downgrade и сохраняет вопросы штатной утилиты.")


def parse_result(action, text, returncode):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    if action == "update":
        pattern = (r"(\d+) upgraded, (\d+) skipped upgrade, (\d+) bootloader updates available, "
                   r"(\d+) stuck in bootloader, (\d+) disconnected, (\d+) foreign and (\d+) too old")
        names = ["upgraded", "skipped", "bootloader_available", "stuck", "disconnected", "foreign", "too_old"]
    else:
        pattern = r"(\d+) recovered, (\d+) was already working, (\d+) not recovered and (\d+) not answered"
        names = ["recovered", "already_working", "not_recovered", "not_answered"]
    matches = list(re.finditer(pattern, clean))
    counts = dict(zip(names, map(int, matches[-1].groups()))) if matches else {}
    failure_keys = ("skipped", "bootloader_available", "stuck", "disconnected", "foreign", "too_old",
                    "not_recovered", "not_answered")
    failed = returncode != 0 or any(counts.get(k, 0) for k in failure_keys)
    failed = failed or bool(re.search(r"\bERROR\b|Traceback|not responding|Flashing.*failed|Not recovered:", clean, re.I))
    return dict(final_status="partial_failure" if failed else ("ok" if counts else "unverified"),
                returncode=returncode, counts=counts,
                device_report=[line for line in clean.splitlines() if re.search(r"/dev/|slave|address", line, re.I)])


class Firmware:
    def __init__(self, engine, runner=None):
        self.engine = engine
        self.live_runner = runner is None
        self.runner = runner or self.interactive

    def inspect(self):
        system = self.engine.system
        require(not system.firmware_busy(), "UPDATER_BUSY: existing updater must finish independently")
        path = self.engine.target(str(UPDATER))
        require(path.is_file(), "UPDATER_ABSENT: install official wb-mcu-fw-updater")
        # Do not import or execute updater for check/help: imports may create cache/database.
        version = system.run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", "wb-mcu-fw-updater"])
        source = path.read_bytes()
        require(version in SUPPORTED, 'UPDATER_UNSUPPORTED: ' + version + '; обновите NLI: nli self-update')
        # Debian dh_python may rewrite only the interpreter line.
        canonical = source.replace(b'#!/usr/bin/python3\n', b'#!/usr/bin/env python3\n', 1)
        blob = hashlib.sha1(b'blob ' + str(len(canonical)).encode() + b'\0' + canonical).hexdigest()
        require(blob == SUPPORTED[version], 'UPDATER_MODIFIED: executable differs from reviewed upstream')
        require(system.run(['/usr/bin/dpkg-query', '-S', UPDATER]) == 'wb-mcu-fw-updater: ' + UPDATER,
                'UPDATER_UNOFFICIAL: package ownership mismatch')
        require(system.run(['/usr/bin/dpkg', '--verify', 'wb-mcu-fw-updater']) == '', 'UPDATER_MODIFIED: package verification failed')
        return dict(version=version, executable_sha256=digest(source), compatibility='supported',
                    commands=[x for x in ("update-all", "recover-all") if x.encode() in source],
                    debug_supported=b"--debug" in source,
                    updates="unavailable", reason="No audited side-effect-free inventory API; no device probing performed",
                    bootloader_notice=BOOTLOADER_NOTICE)

    def confirm(self, action):
        require(sys.stdin.isatty(), "Interactive terminal required; unattended firmware mutation disabled")
        print(BOOTLOADER_NOTICE, flush=True)
        print("Для запуска штатной операции введите firmware-" + action + ": ", end="", flush=True)
        require(input().strip() == "firmware-" + action, "Operator cancelled firmware operation")

    def interactive(self, action, log_path):
        require(not self.engine.system.firmware_busy(), "UPDATER_BUSY")
        command = [str(UPDATER), "update-all" if action == "update" else "recover-all"]
        # Keep stdin attached for upstream prompts. Do not kill a flasher on timeout.
        # SIGINT goes to upstream too; keep NLI lock until child exits and report partial state.
        # A caught handler is reset to default on exec, unlike SIG_IGN; upstream
        # receives Ctrl-C while the parent keeps the lock and waits for its exit.
        old = signal.signal(signal.SIGINT, lambda *args: None)
        old_term = signal.signal(signal.SIGTERM, lambda *args: None)
        process = None
        try:
            command.append("--debug")  # official summaries are INFO, hidden by upstream default WARNING
            with log_path.open("xb") as stream:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           env={**os.environ, "LC_ALL": "C", "PYTHONUNBUFFERED": "1"})
                while True:
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
                returncode = process.wait()
            return log_path.read_text(encoding="utf-8", errors="replace"), returncode
        finally:
            if process is not None and process.poll() is None:
                # A transcript/stdout failure must not orphan a live flashing process
                # and release NLI's lock. Drain the pipe, then wait without killing it.
                while os.read(process.stdout.fileno(), 4096):
                    pass
                process.wait()
            signal.signal(signal.SIGINT, old)
            signal.signal(signal.SIGTERM, old_term)

    def execute(self, action):
        e = self.engine
        record = e.record("firmware " + action, "firmware")
        if action == "check":
            try:
                record.update(self.inspect(), final_status="unavailable")
            except (Error, OSError) as exc:
                record.update(final_status="failed", error=str(exc))
            return record
        with Lock(e.target(STATE_DIR + "/mutation.lock")):
            started = False
            try:
                require(e.config["hostname"] == e.system.hostname(), "Wrong controller hostname")
                previous = e.pending()
                require(not e.target(STATE_DIR + '/self-update.json').exists(), 'Interrupted package update: nli self-update')
                require(not previous or (action == "recover" and previous["component"] == "firmware"),
                        "Unresolved previous mutation; inspect status")
                if previous:
                    record["recovering_operation"] = previous["id"]
                info = self.inspect()
                record.update(info)
                require(("update-all" if action == "update" else "recover-all") in info["commands"], "Unsupported updater command")
                require(info['debug_supported'], 'Unsupported updater logging interface')
                if self.live_runner:
                    require(info["debug_supported"], "Unsupported updater logging interface")
                    self.confirm(action)
                log_path = e.target(LOG_DIR + "/" + record["id"] + ".firmware.log")
                record.update(preflight="ok", output_log=str(log_path))
                e.checkpoint(record)
                started = True
                text, code = self.runner(action, log_path)
                record.update(parse_result(action, text, code))
                record["install"] = record["final_status"]
                e.audit(record)
                # Completed process report remains inspectable; no automatic retry/recovery.
                if record['final_status'] == 'ok':
                    e.clear_pending()
                    e.cleanup(record)
                else:
                    e.checkpoint(record)
            except BaseException as exc:
                record.update(final_status="partial_failure" if started else "failed", error=str(exc))
                if started:
                    e.checkpoint(record)
                else:
                    e.audit(record)
            return record
