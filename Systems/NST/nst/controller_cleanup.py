"""Controller-wide NST storage inspection and safe cleanup."""
from pathlib import Path

from .layout import CONFIG_DIR, LOG_DIR, STATE_DIR
from .retention import cleanup as cleanup_transaction_history
from .util import Error, Lock

KEEP_DIAGNOSTIC_BUNDLES = 5


def _size(path):
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


class ControllerCleanup:
    def __init__(self, engine):
        self.engine = engine

    def _diagnostic_bundles(self):
        folder = self.engine.target(STATE_DIR + "/diagnostics")
        if not folder.is_dir():
            return []
        result = []
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink() and path.name.startswith("nst-diagnostics-") and path.name.endswith(".tar.gz"):
                result.append(path)
        return sorted(result, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)

    def _known_state_names(self):
        names = {"backups", "deployment-backups", "bootstrap.json", "diagnostics", "platform.json", "pending.json", "self-update.json", "mutation.lock"}
        names.update(name + ".json" for name in self.engine.config.get("components", {}))
        return names

    def _unknown(self):
        unknown = []
        state = self.engine.target(STATE_DIR)
        if state.is_dir():
            known = self._known_state_names()
            for path in sorted(state.iterdir(), key=lambda p: p.name):
                if path.name in known or path.name.startswith("nst-package-"):
                    continue
                unknown.append({"path": str(path), "bytes": _size(path), "area": "state"})
        logs = self.engine.target(LOG_DIR)
        if logs.is_dir():
            for path in sorted(logs.iterdir(), key=lambda p: p.name):
                if path.is_symlink() or not (path.name.endswith(".json") or path.name.endswith(".firmware.log")):
                    unknown.append({"path": str(path), "bytes": _size(path), "area": "log"})
        return unknown

    def check(self):
        diagnostics = self._diagnostic_bundles()
        state = self.engine.target(STATE_DIR)
        logs = self.engine.target(LOG_DIR)
        backups = self.engine.target(STATE_DIR + "/backups")
        config = self.engine.target(CONFIG_DIR)
        temp = []
        if state.is_dir():
            temp = [p for p in state.glob("nst-package-*") if p.is_file() and not p.is_symlink()]
        journal = {"status": "unavailable"}
        fn = getattr(self.engine.system, "journal_disk_usage", None)
        if fn:
            try:
                journal = fn()
            except (Error, OSError, ValueError) as exc:
                journal = {"status": "unavailable", "error": str(exc)}
        pending = self.engine.pending()
        self_update = self.engine.target(STATE_DIR + "/self-update.json").exists()
        return {
            "command": "cleanup",
            "action": "check",
            "final_status": "ok",
            "pending_recovery": bool(pending),
            "self_update_pending": self_update,
            "categories": {
                "nst_temp": {"bytes": sum(_size(p) for p in temp), "items": len(temp)},
                "diagnostic_bundles": {
                    "bytes": sum(_size(p) for p in diagnostics),
                    "items": len(diagnostics),
                    "retention": KEEP_DIAGNOSTIC_BUNDLES,
                    "prunable": max(0, len(diagnostics) - KEEP_DIAGNOSTIC_BUNDLES),
                },
                "audit_transcripts": {"bytes": _size(logs)},
                "backups": {"bytes": _size(backups)},
                "protected_config_state": {"bytes": _size(config) + _size(state)},
                "journal": journal,
            },
            "unknown": self._unknown(),
        }

    def execute(self):
        self.engine.require_controller_mutation("cleanup")
        with Lock(self.engine.target(STATE_DIR + "/mutation.lock")):
            before = self.check()
            record = self.engine.record("cleanup")
            record["cleanup_before"] = before
            if before["pending_recovery"] or before["self_update_pending"]:
                record.update(final_status="ok", cleanup={
                    "status": "deferred",
                    "reason": "pending recovery" if before["pending_recovery"] else "self-update recovery",
                    "removed": [],
                })
                try:
                    self.engine.audit(record)
                except BaseException as exc:
                    record["audit_warning"] = str(exc) or type(exc).__name__
                return record

            removed = []
            warnings = []
            try:
                retention = cleanup_transaction_history(self.engine)
                removed.extend(retention.get("removed", []))
            except BaseException as exc:
                warnings.append("transaction retention: " + (str(exc) or type(exc).__name__))

            for path in self._diagnostic_bundles()[KEEP_DIAGNOSTIC_BUNDLES:]:
                try:
                    path.unlink()
                    removed.append("diagnostic:" + path.name)
                except OSError as exc:
                    warnings.append("diagnostic " + path.name + ": " + str(exc))

            state = self.engine.target(STATE_DIR)
            if state.is_dir():
                for path in state.glob("nst-package-*"):
                    if path.is_file() and not path.is_symlink():
                        try:
                            path.unlink()
                            removed.append("temp:" + path.name)
                        except OSError as exc:
                            warnings.append("temp " + path.name + ": " + str(exc))

            record.update(final_status="ok", cleanup={
                "status": "warning" if warnings else "ok",
                "removed": removed,
                "warnings": warnings,
                "unknown_preserved": self._unknown(),
                "diagnostic_retention": KEEP_DIAGNOSTIC_BUNDLES,
            })
            try:
                self.engine.audit(record)
            except BaseException as exc:
                record["audit_warning"] = str(exc) or type(exc).__name__
            return record
