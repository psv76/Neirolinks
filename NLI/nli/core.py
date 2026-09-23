"""Release transactions with durable intent before every externally visible action."""
from datetime import datetime, timezone
import http.client
from pathlib import Path
import stat
import urllib.request
import uuid
from . import __version__
from .manifest import validate, match, SHA, NAME
from .plugins import PLUGINS
from .system import System
from .util import Error, Lock, atomic, beneath, decode, digest, read_json, require, sync_dir, write_json

MAX_ARTIFACT = 8 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Error("Release redirect rejected")


class Engine:
    def __init__(self, config, root="/", system=None):
        self.config = config
        self.root = Path(root).absolute()
        require(system is not None or self.root == Path("/"), "Alternate root requires injected sandbox backend")
        self.system = system or System()
        for field in ("object", "role", "hostname", "components"):
            require(field in config, "Missing config: " + field)
        require(type(config["components"]) is dict, "Invalid component registry")
        self.state_dir = self.target("/var/lib/neiro/nli")
        self.log_dir = self.target("/var/log/neiro/nli")
        self.pending_path = self.target("/var/lib/neiro/nli/pending.json")

    def target(self, path):
        require(isinstance(path, str) and path.startswith("/"), "Expected absolute path")
        return beneath(self.root, path[1:])

    def registration(self, component):
        match(component, NAME, "component")
        require(component in self.config["components"], "Unknown component: " + component)
        r = self.config["components"][component]
        require(r.get("plugin") in PLUGINS, "Unknown component plugin")
        require(component != "hhm" or r["plugin"] == "hhm", "HHM policy is mandatory")
        return r

    def validate(self, m, component):
        validate(m)
        require(m["component"] == component, "Component mismatch")
        require(m["object"] == self.config["object"] and m["role"] == self.config["role"], "Object/role mismatch")
        require(self.config["hostname"] == self.system.hostname(), "Wrong controller hostname")
        r = self.registration(component)
        PLUGINS[r["plugin"]].validate(m, r)
        for f in m["files"]:
            self.target(f["target"])
        return m

    def pinned(self, reference, component):
        require(type(reference) is dict and set(reference) == {"path", "sha256"}, "Expected pinned manifest path/hash")
        match(reference["sha256"], SHA, "manifest hash")
        data = self.target(reference["path"]).read_bytes()
        require(digest(data) == reference["sha256"], "Manifest checksum mismatch")
        return self.validate(decode(data), component)

    def state_path(self, component):
        self.registration(component)
        return self.target("/var/lib/neiro/nli/" + component + ".json")

    def state(self, component):
        p = self.state_path(component)
        return read_json(p) if p.exists() else None

    def current(self, component):
        state = self.state(component)
        if state:
            return self.validate(state["manifest"], component)
        r = self.registration(component)
        require("baseline" in r, "No installed release or reviewed baseline")
        return self.pinned(r["baseline"], component)

    def pending(self):
        return read_json(self.pending_path) if self.pending_path.exists() else None

    def record(self, command, component=None):
        return dict(id=uuid.uuid4().hex, time=now(), hostname=self.system.hostname(),
                    object=self.config["object"], role=self.config["role"], nli=__version__,
                    command=command, component=component, from_version=None, to_version=None,
                    release=None, preflight="not_run", backup=None, services=[],
                    install="not_run", verify="not_run", rollback="not_run", final_status="running")

    def audit(self, record):
        # One durable file per operation, updated after each action. No unbounded log append.
        write_json(self.target("/var/log/neiro/nli/" + record["id"] + ".json"), record)

    def checkpoint(self, record):
        write_json(self.pending_path, record)
        self.audit(record)

    def clear_pending(self):
        self.pending_path.unlink(missing_ok=True)
        sync_dir(self.state_dir)

    def files_match(self, m):
        for f in m["files"]:
            p = self.target(f["target"])
            require(p.is_file() and digest(p.read_bytes()) == f["sha256"], "Unknown file drift: " + f["target"])

    def preflight(self, current, target, recovery=False):
        self.validate(current, current["component"])
        self.validate(target, target["component"])
        if not recovery:
            self.files_match(current)
        current_targets = {f["target"] for f in current["files"]}
        require(current_targets == {f["target"] for f in target["files"]},
                "v0.1 requires stable managed file set; review component migration separately")
        PLUGINS[self.registration(target["component"])["plugin"]].preflight(self, target, recovery)

    def payload(self, m):
        registration = self.registration(m["component"])
        result = {}
        total = 0
        for f in m["files"]:
            if "payload_dir" in registration:
                p = beneath(self.target(registration["payload_dir"]), f["source"])
                require(p.stat().st_size <= MAX_ARTIFACT, "Oversize artifact")
                data = p.read_bytes()
            else:
                url = "https://raw.githubusercontent.com/{}/{}/{}".format(
                    m["release"]["repository"], m["release"]["commit"], f["source"])
                try:
                    with urllib.request.build_opener(NoRedirect).open(url, timeout=20) as response:
                        data = response.read(MAX_ARTIFACT + 1)
                        length = response.headers.get("Content-Length")
                        require(length is None or int(length) == len(data), "Interrupted artifact download")
                except (OSError, ValueError, http.client.HTTPException) as exc:
                    raise Error("Release download failed: " + str(exc)) from exc
                require(len(data) <= MAX_ARTIFACT, "Oversize artifact")
            require(digest(data) == f["sha256"], "Payload checksum mismatch: " + f["source"])
            total += len(data)
            require(total <= 64 * 1024 * 1024, "Release payload exceeds 64 MiB")
            result[f["target"]] = data
        return result

    def verify(self, m, since=None):
        self.files_match(m)
        for service in m["services"]["start"]:
            self.system.active(service)
        PLUGINS[self.registration(m["component"])["plugin"]].verify(self, m, since)

    def backup(self, current, target, record):
        folder = self.target("/var/lib/neiro/nli/backups/" + record["id"])
        items = []
        for i, f in enumerate(current["files"]):
            p = self.target(f["target"])
            data = p.read_bytes()
            require(digest(data) == f["sha256"], "Drift during backup")
            meta = p.stat()
            require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, "Non-regular/hardlinked target")
            name = str(i) + ".bin"
            atomic(beneath(folder, name), data)
            items.append(dict(target=f["target"], blob=name, sha256=digest(data),
                              mode=stat.S_IMODE(meta.st_mode), uid=meta.st_uid, gid=meta.st_gid))
        metadata = dict(manifest=current, target_manifest=target, files=items,
                        previous_state=self.state(current["component"]))
        write_json(beneath(folder, "metadata.json"), metadata)
        return {"id": record["id"], "metadata_sha256": digest(beneath(folder, "metadata.json").read_bytes())}

    def load_backup(self, reference, component):
        match(reference["id"], r"[0-9a-f]{32}", "backup id")
        folder = self.target("/var/lib/neiro/nli/backups/" + reference["id"])
        data = beneath(folder, "metadata.json").read_bytes()
        require(digest(data) == reference["metadata_sha256"], "Corrupted backup metadata")
        meta = decode(data)
        self.validate(meta["manifest"], component)
        self.validate(meta["target_manifest"], component)
        expected = {f["target"]: f["sha256"] for f in meta["manifest"]["files"]}
        require(len(meta["files"]) == len(expected) and {f["target"] for f in meta["files"]} == expected.keys(),
                "Incomplete backup")
        payload = {}
        for f in meta["files"]:
            data = beneath(folder, f["blob"]).read_bytes()
            require(digest(data) == f["sha256"] == expected[f["target"]], "Corrupted backup payload")
            payload[f["target"]] = data
        return meta, payload

    def services(self, m, action, record):
        for service in m["services"][action]:
            step = dict(action=action, service=service, result="intent", time=now())
            record["services"].append(step)
            self.checkpoint(record)
            try:
                self.system.service(action, service)
                step["result"] = "ok"
            except BaseException:
                step["result"] = "failed_or_interrupted"
                raise
            finally:
                self.checkpoint(record)

    def install(self, m, payload, metadata=None):
        saved = {f["target"]: f for f in metadata["files"]} if metadata else {}
        for f in m["files"]:
            p = self.target(f["target"])
            data = payload[f["target"]]
            require(digest(data) == f["sha256"], "Staged payload changed")
            meta = saved.get(f["target"])
            existing = p.stat() if meta is None else None
            atomic(p, data, meta["mode"] if meta else 0o644,
                   (meta["uid"], meta["gid"]) if meta else (existing.st_uid, existing.st_gid))

    def restore(self, reference, component, record):
        meta, payload = self.load_backup(reference, component)
        old = meta["manifest"]
        # Recovery still checks makeup/identity/ownership, but permits stopped wb-rules.
        self.preflight(old, old, recovery=True)
        record["rollback"] = "running"
        self.services(old, "stop", record)
        self.install(old, payload, meta)
        since = now()
        self.services(old, "start", record)
        self.verify(old, since)
        write_json(self.state_path(component), meta["previous_state"] or {
            "manifest": old, "previous_backup": None, "last_result": "baseline_restored"})
        record["rollback"] = "ok"

    def read_operation(self, command, component=None):
        record = self.record(command, component)
        try:
            pending = self.pending()
            if command == "status":
                record["components"] = {c: self.state(c) for c in self.config["components"]}
                history = []
                if self.log_dir.is_dir():
                    for path in self.log_dir.glob("*.json"):
                        item = read_json(beneath(self.log_dir, path.name))
                        history.append(item)
                record["last_operations"] = {}
                for item in sorted(history, key=lambda x: x["time"]):
                    record["last_operations"][item["component"]] = item
                record["pending"] = pending
                record["final_status"] = "recovery_required" if pending else "ok"
                return record
            require(not pending, "Interrupted mutation: use status and rollback " + str((pending or {}).get("component")))
            current = self.current(component)
            record["from_version"] = current["version"]
            if command == "check":
                target = self.pinned(self.registration(component)["target"], component)
                record.update(to_version=target["version"], release=target["release"])
                self.preflight(current, target)
                record["preflight"] = "ok"
                self.payload(target)  # read into memory; no cache/temp/log/lock writes
            else:
                self.verify(current)
                record["verify"] = "ok"
            record["final_status"] = "ok"
        except (Error, OSError, ValueError, KeyError, TypeError) as exc:
            record.update(final_status="failed", error=str(exc))
        return record

    def mutate(self, command, component):
        with Lock(self.target("/var/lib/neiro/nli/mutation.lock")):
            record = self.record(command, component)
            mutation = False
            original_pending = self.pending()
            try:
                self.registration(component)
                require(not original_pending or (command == "rollback" and original_pending["component"] == component),
                        "Recovery required before new mutation")
                current = self.current(component)
                if command == "update":
                    target = self.pinned(self.registration(component)["target"], component)
                    record.update(from_version=current["version"], to_version=target["version"], release=target["release"])
                    record["preflight"] = "running"
                    self.preflight(current, target)
                    record["preflight"] = "ok"
                    record["backup"] = self.backup(current, target, record)
                    self.audit(record)
                    payload = self.payload(target)
                    # Recheck changing interlocks and file drift after network/backup delay.
                    self.preflight(current, target)
                    self.checkpoint(record)
                    mutation = True  # includes stop failure / Ctrl-C in service action
                    self.services(target, "stop", record)
                    record["install"] = "running"
                    self.install(target, payload)
                    record["install"] = "ok"
                    since = now()
                    self.services(target, "start", record)
                    record["verify"] = "running"
                    self.verify(target, since)
                    record["verify"] = "ok"
                    write_json(self.state_path(component), {"manifest": target,
                               "previous_backup": record["backup"], "last_result": "update_ok"})
                else:
                    reference = original_pending["backup"] if original_pending else (self.state(component) or {}).get("previous_backup")
                    require(reference is not None, "No previous release")
                    meta, payload = self.load_backup(reference, component)
                    target = meta["manifest"]
                    record.update(from_version=current["version"], to_version=target["version"],
                                  release=target["release"], backup=reference)
                    record["preflight"] = "running"
                    self.preflight(current, target, recovery=bool(original_pending))
                    record["preflight"] = "ok"
                    self.checkpoint(record)
                    mutation = True
                    self.restore(reference, component, record)
                    record["verify"] = "ok"
                record["final_status"] = "ok"
                state = self.state(component)
                state["last_result"] = command + "_ok"
                write_json(self.state_path(component), state)
                self.audit(record)
                self.clear_pending()
                return record
            except BaseException as exc:
                for stage in ("preflight", "install", "verify"):
                    if record[stage] == "running":
                        record[stage] = "failed"
                record.update(error=str(exc) or type(exc).__name__, final_status="failed")
                if mutation:
                    if command == "update":
                        try:
                            self.restore(record["backup"], component, record)
                            record["final_status"] = "rolled_back"
                            self.audit(record)
                            self.clear_pending()
                        except BaseException as recovery_error:
                            record.update(rollback="failed", rollback_error=str(recovery_error), final_status="partial_failure")
                            self.checkpoint(record)
                    else:
                        record.update(rollback="failed", final_status="partial_failure")
                        self.checkpoint(record)
                self.audit(record)
                return record
