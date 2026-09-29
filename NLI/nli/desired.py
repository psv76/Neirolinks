"""NST desired-state status/check/sync orchestration.

Read-only status never requires network. Check resolves a stable approved platform
release but never downloads component payload. Sync delegates each component
change to the accepted NLI/NST transaction engine.
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from . import __version__
from .controller import ControllerRegistry
from .core import Engine
from .deployment import validate_deployment
from .layout import CONFIG_DIR
from .manifest import validate as validate_component
from .platform import load_platform_state, save_platform_state
from .releases import API, MAX_METADATA, RAW, REPO, TransportError, version
from .util import Error, atomic, decode, digest, require


def now():
    return datetime.now(timezone.utc).isoformat()


class PlatformReleases:
    """Stable GitHub Release is the approval act for registry + deployments."""

    PREFIX = "nst-approved-platform-"
    REGISTRY_ASSET = "nst-controller-registry.json"

    def __init__(self, releases):
        self.releases = releases

    def latest(self, serial):
        candidates = []
        for page in range(1, 11):
            rows = decode(self.releases.fetch(API + "/releases?per_page=100&page=" + str(page)))
            require(type(rows) is list, "Invalid GitHub releases response")
            for release in rows:
                if (release.get("draft") is not False or release.get("prerelease") is not False
                        or not release.get("published_at")
                        or not str(release.get("tag_name", "")).startswith(self.PREFIX)):
                    continue
                assets = release.get("assets")
                require(type(assets) is list, "Invalid platform release assets")
                registry_assets = [a for a in assets if a.get("name") == self.REGISTRY_ASSET]
                deployment_name = "nst-deployment-" + serial + ".json"
                deployment_assets = [a for a in assets if a.get("name") == deployment_name]
                require(len(registry_assets) == 1, "Approved platform release requires one controller registry")
                if not deployment_assets:
                    continue
                require(len(deployment_assets) == 1, "Duplicate controller deployment asset")
                registry_raw = self.releases.asset(registry_assets[0], MAX_METADATA)
                deployment_raw = self.releases.asset(deployment_assets[0], MAX_METADATA)
                registry = ControllerRegistry(decode(registry_raw))
                deployment = validate_deployment(decode(deployment_raw))
                resolved = registry.resolve({"serial": serial, "serial_source": "approved-check", "fingerprint": None})
                assignment = resolved.get("assignment")
                require(assignment is not None, "Approved registry does not contain controller " + serial)
                require((assignment["object"], assignment["node"], assignment["role"], assignment["state"]) ==
                        (deployment["object"], deployment["node"], deployment["role"], deployment["state"]),
                        "Approved registry/deployment assignment mismatch")
                require(deployment["controller_serial"] == serial, "Deployment serial mismatch")
                candidates.append({
                    "published_at": release["published_at"],
                    "tag": release["tag_name"],
                    "registry": registry.data,
                    "registry_sha256": digest(registry_raw),
                    "deployment": deployment,
                    "deployment_sha256": digest(deployment_raw),
                })
            if len(rows) < 100:
                break
        require(candidates, "No approved platform deployment for controller " + serial)
        candidates.sort(key=lambda x: (x["published_at"], x["tag"]), reverse=True)
        latest = candidates[0]
        require(all((c["registry_sha256"], c["deployment_sha256"]) ==
                    (latest["registry_sha256"], latest["deployment_sha256"])
                    for c in candidates if c["published_at"] == latest["published_at"]),
                "Conflicting latest approved platform releases")
        return latest

    def component_manifest(self, deployment_component):
        ref = deployment_component["manifest"]
        raw = self.releases.fetch(RAW + ref["commit"] + "/" + ref["path"])
        require(digest(raw) == ref["sha256"], "Desired component manifest checksum mismatch")
        manifest = validate_component(decode(raw))
        require((manifest["component"], manifest["version"], manifest["release"]) ==
                (deployment_component["component"], deployment_component["version"], deployment_component["release"]),
                "Desired component manifest identity mismatch")
        require(manifest["files"] == deployment_component["files"], "Desired component file set mismatch")
        require(manifest["services"] == deployment_component["services"], "Desired component service set mismatch")
        return raw, manifest


class DesiredState:
    def __init__(self, engine, platform_source=None):
        self.engine = engine
        self.source = platform_source or PlatformReleases(engine.releases)

    def _serial(self):
        controller = self.engine.controller or {}
        identity = controller.get("identity") or {}
        serial = identity.get("serial")
        require(serial, controller.get("reason") or "CONTROLLER_IDENTITY_UNAVAILABLE")
        return serial

    def _resources(self):
        fn = getattr(self.engine.system, "resources", None)
        if not fn:
            return {"status": "unavailable"}
        try:
            return fn()
        except (Error, OSError, ValueError):
            return {"status": "unavailable"}

    def _service_states(self, deployment=None):
        services = set()
        if deployment:
            services.update(deployment.get("services", {}).get("start", []))
        for component in self.engine.config.get("components", {}).values():
            # component registrations intentionally do not own arbitrary services;
            # wb-rules is the common engineering runtime for current plugins.
            if component.get("plugin") in ("hhm", "pressure_makeup"):
                services.add("wb-rules")
        fn = getattr(self.engine.system, "service_state", None)
        result = {}
        for service in sorted(services):
            if not fn:
                result[service] = "unavailable"
                continue
            try:
                result[service] = fn(service)
            except (Error, OSError, ValueError):
                result[service] = "unavailable"
        return result

    def _file_state(self, deployment):
        files = []
        for item in deployment.get("object_files", []):
            files.append(("object", item))
        for component in deployment.get("components", []):
            for item in component["files"]:
                files.append((component["component"], item))
        result = []
        for owner, item in files:
            path = self.engine.target(item["target"])
            actual = digest(path.read_bytes()) if path.is_file() else None
            result.append({
                "owner": owner,
                "target": item["target"],
                "expected_sha256": item["sha256"],
                "actual_sha256": actual,
                "status": "exact" if actual == item["sha256"] else ("missing" if actual is None else "drift"),
            })
        return result

    def _plan(self, deployment):
        files = self._file_state(deployment)
        component_plan = []
        for desired in deployment["components"]:
            name = desired["component"]
            installed = None
            error = None
            try:
                installed = self.engine.current(name)["version"]
            except (Error, OSError, KeyError, TypeError) as exc:
                error = str(exc)
            changed_files = [f["target"] for f in files
                             if f["owner"] == name and f["status"] != "exact"]
            action = "none" if installed == desired["version"] and not changed_files else "sync"
            component_plan.append({
                "component": name,
                "installed": installed,
                "desired": desired["version"],
                "action": action,
                "changed_files": changed_files,
                "error": error,
            })
        object_changes = [f["target"] for f in files if f["owner"] == "object" and f["status"] != "exact"]
        exact = (not object_changes and all(x["action"] == "none" for x in component_plan))
        return {
            "status": "exact" if exact else "changes_required",
            "components": component_plan,
            "object_files": object_changes,
            "services": [] if exact else deployment["services"]["stop"],
            "files": files,
        }

    def status(self):
        before = self.engine.read_operation("status")
        platform = before.get("platform") or load_platform_state(self.engine)
        deployment_meta = platform.get("deployment")
        deployment = deployment_meta.get("manifest") if isinstance(deployment_meta, dict) else None
        local_plan = None
        if isinstance(deployment, dict):
            try:
                validate_deployment(deployment)
                local_plan = self._plan(deployment)
            except (Error, OSError, ValueError, KeyError, TypeError) as exc:
                local_plan = {"status": "invalid_local_deployment", "error": str(exc)}
        before["command"] = "status"
        before["resources"] = self._resources()
        before["services"] = self._service_states(deployment)
        before["deployment_state"] = local_plan
        return before

    def _approved(self):
        serial = self._serial()
        approved = self.source.latest(serial)
        deployment = validate_deployment(approved["deployment"])
        require(version(__version__) >= version(deployment["minimum_nst"]),
                "Требуется NST " + deployment["minimum_nst"] + ": nst self-update")
        controller = self.engine.controller or {}
        assignment = controller.get("assignment")
        require(assignment is not None, controller.get("reason") or "CONTROLLER_NOT_REGISTERED")
        require((assignment["object"], assignment["node"], assignment["role"], assignment["state"]) ==
                (deployment["object"], deployment["node"], deployment["role"], "active"),
                "CONTROLLER_DEPLOYMENT_MISMATCH")
        return approved

    def check(self):
        record = self.engine.record("check")
        snapshot = None
        try:
            controller = self.engine.controller or {}
            require(controller.get("state") == "active" and controller.get("mutation_allowed") is True,
                    controller.get("reason") or "CONTROLLER_NOT_ACTIVE")
            approved = self._approved()
            plan = self._plan(approved["deployment"])
            record.update(
                final_status="ok",
                approved_platform={
                    "tag": approved["tag"],
                    "published_at": approved["published_at"],
                    "registry_sha256": approved["registry_sha256"],
                    "deployment_sha256": approved["deployment_sha256"],
                },
                desired_deployment=approved["deployment"],
                plan=plan,
                mutation_required=plan["status"] != "exact",
            )
        except TransportError as exc:
            record.update(final_status="unavailable", error=str(exc))
        except (Error, OSError, ValueError, KeyError, TypeError) as exc:
            record.update(final_status="failed", error=str(exc))
        return record

    def _install_component(self, desired, approved):
        raw, manifest = self.source.component_manifest(desired)
        pin_path = CONFIG_DIR + "/releases/nst-desired-" + self._serial() + "-" + desired["component"] + ".json"
        atomic(self.engine.target(pin_path), raw)
        config = copy.deepcopy(self.engine.config)
        config["release_source"] = "pinned"
        registration = config["components"].get(desired["component"])
        require(registration is not None, "Desired component is not registered locally: " + desired["component"])
        registration["target"] = {"path": pin_path, "sha256": digest(raw)}
        registration.pop("payload_dir", None)
        registration["remote_payload"] = True
        child = Engine(config, self.engine.root, self.engine.system, self.engine.releases, self.engine.controller)
        result = child.mutate("update", desired["component"])
        require(result["final_status"] == "ok", "Component sync failed: " + desired["component"] + ": "
                + str(result.get("error") or result["final_status"]))
        require(child.current(desired["component"])["version"] == manifest["version"],
                "Installed component version does not match desired deployment")
        return result

    def sync(self):
        record = self.engine.record("sync")
        # Lifecycle/identity refusal is intentionally before any persistent
        # mutation or audit, matching the controller guard contract.
        try:
            self.engine.require_controller_mutation("sync")
        except (Error, OSError, ValueError, KeyError, TypeError) as exc:
            record.update(final_status="failed", error=str(exc))
            return record
        try:
            require(not self.engine.pending(), "Recovery required before desired-state sync")
            approved = self._approved()
            deployment = approved["deployment"]
            plan = self._plan(deployment)
            record["approved_platform"] = {
                "tag": approved["tag"],
                "published_at": approved["published_at"],
                "registry_sha256": approved["registry_sha256"],
                "deployment_sha256": approved["deployment_sha256"],
            }
            record["plan"] = plan
            require(not plan["object_files"],
                    "Object payload changes require reviewed object-file transaction support")
            operations = []
            desired_by_name = {c["component"]: c for c in deployment["components"]}
            for item in plan["components"]:
                if item["action"] == "sync":
                    operations.append(self._install_component(desired_by_name[item["component"]], approved))
            final_plan = self._plan(deployment)
            require(final_plan["status"] == "exact", "Desired deployment is not exact after sync")
            platform = load_platform_state(self.engine)
            platform["controller"] = {
                "serial": self._serial(),
                "object": deployment["object"],
                "node": deployment["node"],
                "role": deployment["role"],
            }
            platform["registry"] = {
                "tag": approved["tag"],
                "sha256": approved["registry_sha256"],
                "published_at": approved["published_at"],
            }
            platform["deployment"] = {
                "tag": approved["tag"],
                "sha256": approved["deployment_sha256"],
                "published_at": approved["published_at"],
                "manifest": deployment,
            }
            platform["desired_state"] = {"status": "exact", "checked_at": now()}
            save_platform_state(self.engine, platform)
            record.update(operations=operations, deployment_state=final_plan, final_status="ok")
            self.engine.audit(record)
        except TransportError as exc:
            record.update(final_status="unavailable", error=str(exc))
        except BaseException as exc:
            record.update(final_status="failed", error=str(exc) or type(exc).__name__)
            try:
                self.engine.audit(record)
            except BaseException:
                pass
        return record
