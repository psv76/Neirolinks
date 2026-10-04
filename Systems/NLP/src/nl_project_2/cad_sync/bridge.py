"""Named-pipe client for the separate x64 STA AutoCAD bridge process."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any

from nl_project_2.cad_contract import (
    BlockDefinitionMetadata,
    CadObservation,
    CadObservationBatch,
    CadReadRequest,
)
from nl_project_2.runtime_resources import sta_bridge_command

from .models import WriteResult


class BridgeError(RuntimeError):
    pass


class BridgeTimeout(BridgeError):
    pass


@dataclass(frozen=True, slots=True)
class ActiveDocumentInfo:
    document_identity: str
    document_name: str
    read_only: bool
    saved: bool
    dbmod: int


class AutoCadBridgeClient:
    """Starts one short-lived bridge per command; the bridge never receives a DB path."""

    def __init__(self, bridge_script: Path | None = None, *, logger=None) -> None:
        self._bridge_script = bridge_script
        self._logger = logger
        self._cached_batch: CadObservationBatch | None = None
        self._cached_signatures: dict[str, str] | None = None
        self._cached_order: tuple[str, ...] | None = None

    def inspect_active_document(self, *, deadline_seconds: float = 15.0) -> ActiveDocumentInfo:
        payload = self._call({"operation": "document_identity"}, deadline_seconds)
        return ActiveDocumentInfo(
            document_identity=payload["document_identity"],
            document_name=payload["document_name"],
            read_only=bool(payload["read_only"]),
            saved=bool(payload["saved"]),
            dbmod=int(payload["dbmod"]),
        )

    def read_observations(self, request: CadReadRequest) -> CadObservationBatch:
        expected = request.expected_document_identity.strip()
        cache_matches = (
            self._cached_batch is not None
            and self._cached_signatures is not None
            and self._cached_order is not None
            and (
                not expected
                or self._cached_batch.document_identity.casefold() == expected.casefold()
            )
        )
        if cache_matches:
            try:
                fingerprint = self._fingerprint(request)
                if (
                    fingerprint["document_identity"].casefold()
                    == self._cached_batch.document_identity.casefold()
                ):
                    current_signatures = {
                        str(key): str(value) for key, value in fingerprint["signatures"].items()
                    }
                    current_order = tuple(str(value) for value in fingerprint["handles"])
                    if current_signatures == self._cached_signatures:
                        metadata = dict(fingerprint["source_metadata"])
                        metadata["incremental_mode"] = "CACHE_HIT"
                        return CadObservationBatch(
                            document_identity=fingerprint["document_identity"],
                            observations=self._cached_batch.observations,
                            source_metadata=metadata,
                        )

                    old_handles = set(self._cached_signatures)
                    current_handles = set(current_signatures)
                    changed_handles = {
                        handle
                        for handle in current_handles & old_handles
                        if current_signatures[handle] != self._cached_signatures[handle]
                    }
                    changed_handles.update(current_handles - old_handles)

                    replacements: dict[str, CadObservation] = {}
                    if changed_handles:
                        delta_payload = self._call(
                            {
                                "operation": "scan_handles",
                                "expected_document_identity": request.expected_document_identity,
                                "definition_names": list(request.definition_names),
                                "handles": sorted(changed_handles),
                            },
                            request.deadline_seconds,
                        )
                        delta_batch = _batch_from_payload(delta_payload)
                        replacements = {
                            observation.handle: observation
                            for observation in delta_batch.observations
                        }
                        if set(replacements) != changed_handles:
                            raise BridgeError(
                                "Incremental scan did not return every changed/new handle"
                            )

                    verify = self._fingerprint(request)
                    verify_signatures = {
                        str(key): str(value) for key, value in verify["signatures"].items()
                    }
                    verify_order = tuple(str(value) for value in verify["handles"])
                    if verify_signatures != current_signatures or verify_order != current_order:
                        raise BridgeError(
                            "AutoCAD changed while incremental observations were being read"
                        )

                    cached_by_handle = {
                        observation.handle: observation
                        for observation in self._cached_batch.observations
                    }
                    merged: list[CadObservation] = []
                    for handle in current_order:
                        if handle in replacements:
                            merged.append(replacements[handle])
                            continue
                        existing = cached_by_handle.get(handle)
                        if existing is None:
                            raise BridgeError(
                                f"Incremental cache is missing unchanged handle {handle}"
                            )
                        merged.append(existing)
                    metadata = dict(verify["source_metadata"])
                    metadata["incremental_mode"] = "DELTA"
                    metadata["incremental_changed_handles"] = len(changed_handles)
                    batch = CadObservationBatch(
                        document_identity=verify["document_identity"],
                        observations=tuple(merged),
                        source_metadata=metadata,
                    )
                    self._set_cache(
                        batch,
                        signatures=verify_signatures,
                        order=verify_order,
                    )
                    return batch
            except (BridgeError, BridgeTimeout, KeyError, TypeError, ValueError):
                self._clear_cache()

        pre_scan_fingerprint: dict[str, Any] | None = None
        try:
            pre_scan_fingerprint = self._fingerprint(request)
        except (BridgeError, BridgeTimeout, KeyError, TypeError, ValueError):
            self._clear_cache()

        payload = self._call(
            {
                "operation": "scan",
                "expected_document_identity": request.expected_document_identity,
                "definition_names": list(request.definition_names),
            },
            request.deadline_seconds,
        )
        batch = _batch_from_payload(payload)
        if pre_scan_fingerprint is None:
            self._clear_cache()
            return batch

        try:
            post_scan_fingerprint = self._fingerprint(request)
            pre_signatures = {
                str(key): str(value) for key, value in pre_scan_fingerprint["signatures"].items()
            }
            post_signatures = {
                str(key): str(value) for key, value in post_scan_fingerprint["signatures"].items()
            }
            pre_order = tuple(str(value) for value in pre_scan_fingerprint["handles"])
            post_order = tuple(str(value) for value in post_scan_fingerprint["handles"])
        except (BridgeError, BridgeTimeout, KeyError, TypeError, ValueError):
            self._clear_cache()
            return batch

        batch_handles = {item.handle for item in batch.observations}
        stable_full_read = (
            pre_scan_fingerprint["document_identity"].casefold()
            == batch.document_identity.casefold()
            == post_scan_fingerprint["document_identity"].casefold()
            and pre_signatures == post_signatures
            and pre_order == post_order
            and set(post_order) == batch_handles
            and len(post_order) == len(batch.observations)
        )
        if not stable_full_read:
            self._clear_cache()
            raise BridgeError("AutoCAD changed while full observations were being read")

        self._set_cache(batch, signatures=post_signatures, order=post_order)
        return batch

    def _fingerprint(self, request: CadReadRequest) -> dict[str, Any]:
        return self._call(
            {
                "operation": "fingerprint",
                "expected_document_identity": request.expected_document_identity,
                "timeout_seconds": min(15.0, request.deadline_seconds),
            },
            request.deadline_seconds,
        )

    def _set_cache(
        self,
        batch: CadObservationBatch,
        *,
        signatures: dict[str, str],
        order: tuple[str, ...],
    ) -> None:
        self._cached_batch = batch
        self._cached_signatures = dict(signatures)
        self._cached_order = tuple(order)

    def _clear_cache(self) -> None:
        self._cached_batch = None
        self._cached_signatures = None
        self._cached_order = None

    def write_attributes(
        self,
        *,
        document_identity: str,
        changes: list[dict[str, str]],
        deadline_seconds: float = 15.0,
    ) -> WriteResult:
        payload = self._call(
            {
                "operation": "write_attributes",
                "expected_document_identity": document_identity,
                "changes": changes,
            },
            deadline_seconds,
        )
        return WriteResult(
            document_identity=payload["document_identity"],
            readback=tuple(payload["readback"]),
            no_save_confirmed=bool(payload["no_save_confirmed"]),
            document_saved=bool(payload["document_saved"]),
            status=str(payload.get("status", "READ_BACK_OK")),
            failures=tuple(payload.get("failures", ())),
        )

    def _call(self, request: dict[str, Any], deadline_seconds: float) -> dict[str, Any]:
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        pipe = rf"\\.\pipe\nlp2-cad-{uuid.uuid4()}"
        process = subprocess.Popen(
            sta_bridge_command(pipe, self._bridge_script),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        connection = None
        operation = str(request.get("operation", "unknown"))
        started = time.monotonic()
        last_stage = "process_start"
        deadline = time.monotonic() + deadline_seconds
        self._record(
            level="INFO",
            operation=operation,
            result="started",
            started=started,
            summary={
                "bridge_pid": process.pid,
                "stage": last_stage,
                "target_identity_sha256": _identity_digest(
                    str(request.get("expected_document_identity", ""))
                ),
            },
        )
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    raise BridgeError(_bridge_failure(stdout, stderr, process.returncode))
                try:
                    connection = Client(pipe, family="AF_PIPE")
                    last_stage = "pipe_connected"
                    self._record(
                        level="INFO",
                        operation=operation,
                        result="progress",
                        started=started,
                        summary={"bridge_pid": process.pid, "stage": last_stage},
                    )
                    break
                except (FileNotFoundError, OSError):
                    time.sleep(0.05)
            if connection is None:
                raise BridgeTimeout("AutoCAD bridge did not open its named pipe in time")
            connection.send_bytes(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            last_stage = "command_sent"
            response = None
            while time.monotonic() < deadline:
                if not connection.poll(max(0.0, deadline - time.monotonic())):
                    break
                frame = json.loads(connection.recv_bytes().decode("utf-8"))
                if frame.get("type") == "progress":
                    last_stage = str(frame.get("stage", "bridge_progress"))
                    self._record(
                        level="INFO",
                        operation=operation,
                        result="progress",
                        started=started,
                        summary={"bridge_pid": process.pid, "stage": last_stage},
                    )
                    continue
                response = frame
                break
            if response is None:
                raise BridgeTimeout(
                    f"AutoCAD bridge command timed out at stage {last_stage}; "
                    f"bridge_pid={process.pid}"
                )
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            if not response.get("ok"):
                raise BridgeError(
                    f"{response.get('error_category', 'BRIDGE_ERROR')}: "
                    f"{response.get('message', 'unknown bridge error')}"
                )
            self._record(
                level="INFO",
                operation=operation,
                result="succeeded",
                started=started,
                summary={"bridge_pid": process.pid, "stage": "response_received"},
            )
            return response["result"]
        except subprocess.TimeoutExpired as exc:
            error = BridgeTimeout(
                f"AutoCAD bridge process did not finish at stage {last_stage}; "
                f"bridge_pid={process.pid}"
            )
            self._record(
                level="ERROR",
                operation=operation,
                result="failed",
                started=started,
                error=error,
                summary={"bridge_pid": process.pid, "stage": last_stage},
            )
            raise error from exc
        except Exception as exc:
            self._record(
                level="ERROR",
                operation=operation,
                result="failed",
                started=started,
                error=exc,
                summary={"bridge_pid": process.pid, "stage": last_stage},
            )
            raise
        finally:
            if connection is not None:
                connection.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
                self._record(
                    level="WARNING",
                    operation=operation,
                    result="terminated",
                    started=started,
                    summary={"bridge_pid": process.pid, "stage": last_stage},
                )

    def _record(self, *, level, operation, result, started, error=None, summary=None) -> None:
        if self._logger is None:
            return
        self._logger.record(
            level=level,
            component="autocad_bridge",
            operation=operation,
            result=result,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=error,
            summary=summary,
        )


def _batch_from_payload(payload: dict[str, Any]) -> CadObservationBatch:
    observations = tuple(
        CadObservation.from_mapping(
            effective_name=item["effective_name"],
            layer=item["layer"],
            raw_attributes=item["raw_attributes"],
            x=item["x"],
            y=item["y"],
            handle=item["handle"],
            definition=BlockDefinitionMetadata(
                attribute_definition_tags=(
                    tuple(item["definition_tags"])
                    if item.get("definition_tags") is not None
                    else None
                ),
                is_dynamic=item.get("is_dynamic"),
            ),
        )
        for item in payload["observations"]
    )
    return CadObservationBatch(
        document_identity=payload["document_identity"],
        observations=observations,
        source_metadata=payload["source_metadata"],
    )


def _bridge_failure(stdout: str, stderr: str, returncode: int | None) -> str:
    details = (stderr or stdout).strip()
    if details:
        return f"bridge exited with code {returncode}: {details[-1000:]}"
    return f"bridge exited with code {returncode}"


def _identity_digest(identity: str) -> str | None:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest() if identity else None
