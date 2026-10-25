"""Named-pipe client for the separate x64 STA AutoCAD bridge process."""

from __future__ import annotations

import hashlib
import json
import re
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
from nl_project_2.cad_contract.layer_names import parse_working_layer_name
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


@dataclass(frozen=True, slots=True)
class FreshCadReadWitness:
    """One stable forced full COM read; never a durable DWG-file attestation."""

    batch: CadObservationBatch
    document_identity: str
    fingerprint_sha256: str
    document_saved: bool
    dbmod: int
    scan_mode: str = "FORCED_FULL_SCAN"
    proves_durable_file_identity: bool = False


@dataclass(frozen=True, slots=True)
class LayerFilteredRead:
    """Diagnostic read only. The embedded batch remains blocked by C6."""

    batch: CadObservationBatch
    census: tuple[tuple[str, str], ...]
    present_excluded_handles: tuple[str, ...]
    absent_unknown_handles: tuple[str, ...]
    status: str = "REQUIRES_ATTENTION"
    next_action: str = "Obtain a full unfiltered read before preview/apply."


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

    def read_fresh_observations_with_witness(self, request: CadReadRequest) -> FreshCadReadWitness:
        """Bypass incremental cache and inspect COM state around an actual full scan.

        The scan and document metadata are read by the separate STA bridge.
        Fingerprint snapshots must bracket a real 'scan' operation and match
        its entire unfiltered read; this never authorizes publication by itself.
        """
        expected = request.expected_document_identity.strip()
        if not expected:
            raise BridgeError("D20_EXPLICIT_DOCUMENT_IDENTITY_REQUIRED")
        if request.deadline_seconds <= 0:
            raise BridgeError("D20_VALID_SCAN_DEADLINE_REQUIRED")

        self._clear_cache()
        before = self.inspect_active_document(deadline_seconds=request.deadline_seconds)
        if (
            before.document_identity.casefold() != expected.casefold()
            or not before.saved
            or before.dbmod != 0
        ):
            raise BridgeError("D20_DOCUMENT_NOT_SAVED_OR_WRONG_OWNER")
        first = self._fingerprint(request)
        if first["document_identity"].casefold() != expected.casefold():
            raise BridgeError("D20_INITIAL_FINGERPRINT_DOCUMENT_CHANGED")
        first_signatures = {str(key): str(value) for key, value in first["signatures"].items()}
        first_order = tuple(str(key) for key in first["handles"])
        if len(first_order) != len(set(first_order)) or set(first_order) != set(first_signatures):
            raise BridgeError("D20_FINGERPRINT_OWNER_SET_INVALID")

        payload = self._call(
            {
                "operation": "scan",
                "expected_document_identity": expected,
                "definition_names": list(request.definition_names),
            },
            request.deadline_seconds,
        )
        batch = _batch_from_payload(payload)

        final = self._fingerprint(request)
        after = self.inspect_active_document(deadline_seconds=request.deadline_seconds)
        final_signatures = {str(key): str(value) for key, value in final["signatures"].items()}
        final_order = tuple(str(key) for key in final["handles"])
        if (
            before != after
            or first_order != final_order
            or first_signatures != final_signatures
            or first["document_identity"].casefold() != expected.casefold()
            or final["document_identity"].casefold() != expected.casefold()
            or batch.document_identity.casefold() != expected.casefold()
        ):
            raise BridgeError("D20_DOCUMENT_OR_FINGERPRINT_CHANGED_DURING_READ")
        if len(batch.observations) != len(first_order) or {
            item.handle for item in batch.observations
        } != set(first_order):
            raise BridgeError("D20_FULL_SCAN_OWNER_SET_MISMATCH")

        # Parse the COM fingerprint independently and compare its source facts
        # with the actually returned scan; equal handles alone are not enough.
        try:
            fingerprint_batch = _batch_from_fingerprint(
                final, definition_names=set(request.definition_names)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BridgeError("D20_FINGERPRINT_NOT_INDEPENDENTLY_READABLE") from exc
        by_handle = {item.handle: item for item in fingerprint_batch.observations}
        for item in batch.observations:
            counterpart = by_handle[item.handle]
            if (
                item.effective_name != counterpart.effective_name
                or item.layer != counterpart.layer
                or float(item.x) != float(counterpart.x)
                or float(item.y) != float(counterpart.y)
                or {att.tag: att.value for att in item.raw_attributes}
                != {att.tag: att.value for att in counterpart.raw_attributes}
            ):
                raise BridgeError("D20_SCAN_DISAGREES_WITH_INDEPENDENT_FINGERPRINT")

        verified_metadata = dict(batch.source_metadata)
        verified_metadata["incremental_mode"] = "FORCED_FULL_SCAN"
        verified_metadata["d20_source_status"] = "BRIDGE_STABLE_IN_MEMORY_ONLY"
        batch = CadObservationBatch(
            document_identity=batch.document_identity,
            observations=batch.observations,
            source_metadata=verified_metadata,
        )
        digest_payload = json.dumps(
            {
                "contract": "NLP_D20_COM_BRIDGE_FULL_SCAN_V1",
                "document_identity": expected.casefold(),
                "order": first_order,
                "signatures": first_signatures,
                "document_saved": before.saved,
                "dbmod": before.dbmod,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return FreshCadReadWitness(
            batch=batch,
            document_identity=before.document_identity,
            fingerprint_sha256=hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
            document_saved=before.saved,
            dbmod=before.dbmod,
        )

    def read_layer_filtered_observations(
        self, request: CadReadRequest, *, tracked_handles: tuple[str, ...]
    ) -> LayerFilteredRead:
        """Explicit diagnostic API; never used by Update or the #148 cache.

        A complete handle/layer census brackets selected LISP/COM heavy reads.
        It proves presence at those samples, not durable deletion or a stable
        attribute revision. Absent tracked handles therefore stay unknown.
        """
        expected = request.expected_document_identity.strip()
        if not expected or request.deadline_seconds <= 0:
            raise BridgeError("FILTERED_READ_EXPLICIT_DOCUMENT_AND_DEADLINE_REQUIRED")
        if len(set(tracked_handles)) != len(tracked_handles) or any(
            not isinstance(h, str) or re.fullmatch(r"[0-9A-F]+", h) is None for h in tracked_handles
        ):
            raise BridgeError("FILTERED_READ_TRACKED_HANDLES_INVALID")
        read_id = uuid.uuid4().hex
        payload = self._call(
            {
                "operation": "scan_working_layers",
                "expected_document_identity": expected,
                "tracked_handles": list(tracked_handles),
                "read_id": read_id,
                "definition_names": list(request.definition_names),
                "timeout_seconds": min(15.0, request.deadline_seconds),
            },
            request.deadline_seconds,
        )
        try:
            if (
                payload["read_id"] != read_id
                or payload["document_identity"].casefold() != expected.casefold()
            ):
                raise ValueError("stale or foreign document response")
            before, after = payload["census_before"], payload["census_after"]
            if not isinstance(before, dict) or not isinstance(after, dict) or before != after:
                raise ValueError("census drift")
            if any(
                not isinstance(h, str)
                or re.fullmatch(r"[0-9A-F]+", h) is None
                or not isinstance(layer, str)
                for h, layer in before.items()
            ):
                raise ValueError("malformed census")
            selected = {
                h
                for h, layer in before.items()
                if parse_working_layer_name(layer) is not None or h in tracked_handles
            }
            returned = payload["selected_handles"]
            if len(returned) != len(set(returned)) or set(returned) != selected:
                raise ValueError("selected handle mismatch")
            if payload["tracked_handles"] != list(tracked_handles):
                raise ValueError("tracked handle mismatch")
            metadata = payload["source_metadata"]
            if (
                metadata.get("layer_filter_applied") is not True
                or metadata.get("scan_is_complete_for_reconciliation") is not False
                or type(metadata.get("skipped_block_references")) is not int
                or metadata["skipped_block_references"] != len(before) - len(selected)
            ):
                raise ValueError("missing non-authoritative flags")
            batch = (
                _batch_from_fingerprint(payload, definition_names=set(request.definition_names))
                if metadata["scan_mode"] == "FILTERED_FINGERPRINT"
                else _batch_from_payload(payload)
            )
            if (
                len(batch.observations) != len(selected)
                or {o.handle for o in batch.observations} != selected
            ):
                raise ValueError("heavy observation owner mismatch")
            if any(o.layer != before[o.handle] for o in batch.observations):
                raise ValueError("heavy observation layer drift")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise BridgeError(f"FILTERED_READ_INVALID: {exc}") from exc
        excluded = tuple(
            sorted(
                h
                for h in tracked_handles
                if h in before and parse_working_layer_name(before[h]) is None
            )
        )
        return LayerFilteredRead(
            batch,
            tuple(before.items()),
            excluded,
            tuple(sorted(set(tracked_handles) - before.keys())),
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

        batch: CadObservationBatch | None = None
        if pre_scan_fingerprint is not None:
            try:
                batch = _batch_from_fingerprint(
                    pre_scan_fingerprint,
                    definition_names=set(request.definition_names),
                )
            except (KeyError, TypeError, ValueError):
                batch = None

        if batch is None:
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


def _batch_from_fingerprint(
    payload: dict[str, Any], *, definition_names: set[str] | None = None
) -> CadObservationBatch:
    observations: list[CadObservation] = []
    order = tuple(str(value) for value in payload["handles"])
    signatures = {str(key): str(value) for key, value in payload["signatures"].items()}
    if set(order) != set(signatures):
        raise ValueError("Fingerprint handles/signatures mismatch")
    for handle in order:
        item = _parse_fingerprint_signature(signatures[handle])
        name = str(item[0])
        layer = str(item[1])
        point = item[2]
        dynamic = item[3]
        attrs = item[4]
        definition_tags = item[5]
        if not isinstance(point, list) or len(point) < 2:
            raise ValueError(f"Malformed fingerprint point for handle {handle}")
        if attrs is None:
            attrs = []
        if not isinstance(attrs, list):
            raise ValueError(f"Malformed fingerprint attributes for handle {handle}")
        if definition_tags is not None and not isinstance(definition_tags, list):
            raise ValueError(f"Malformed fingerprint definition for handle {handle}")
        raw_attributes: dict[str, str] = {}
        for pair in attrs:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Malformed fingerprint attribute pair for handle {handle}")
            raw_attributes[str(pair[0])] = str(pair[1])
        observations.append(
            CadObservation.from_mapping(
                effective_name=name,
                layer=layer,
                raw_attributes=raw_attributes,
                x=float(point[0]),
                y=float(point[1]),
                handle=handle,
                definition=BlockDefinitionMetadata(
                    attribute_definition_tags=(
                        tuple(str(value) for value in definition_tags)
                        if definition_tags is not None
                        and (definition_names is None or name in definition_names)
                        else None
                    ),
                    is_dynamic=dynamic if isinstance(dynamic, bool) else None,
                ),
            )
        )
    metadata = dict(payload["source_metadata"])
    metadata["incremental_mode"] = "FINGERPRINT_COLD"
    return CadObservationBatch(
        document_identity=payload["document_identity"],
        observations=tuple(observations),
        source_metadata=metadata,
    )


def _parse_fingerprint_signature(text: str) -> list[Any]:
    index = 0
    length = len(text)

    def skip_ws() -> None:
        nonlocal index
        while index < length and text[index].isspace():
            index += 1

    def parse_string() -> str:
        nonlocal index
        index += 1
        out: list[str] = []
        while index < length:
            char = text[index]
            index += 1
            if char == '"':
                return "".join(out)
            if char == "\\" and index < length:
                escaped = text[index]
                index += 1
                out.append(escaped)
            else:
                out.append(char)
        raise ValueError("Unterminated fingerprint string")

    def parse_atom() -> Any:
        nonlocal index
        start = index
        while index < length and not text[index].isspace() and text[index] not in "()":
            index += 1
        token = text[start:index]
        lowered = token.casefold()
        if lowered == ":vlax-true":
            return True
        if lowered == ":vlax-false":
            return False
        if lowered == "nil":
            return None
        try:
            return float(token) if any(mark in token for mark in ".eE") else int(token)
        except ValueError:
            return token

    def parse_value() -> Any:
        nonlocal index
        skip_ws()
        if index >= length:
            raise ValueError("Unexpected end of fingerprint signature")
        char = text[index]
        if char == '"':
            return parse_string()
        if char == "(":
            index += 1
            values: list[Any] = []
            while True:
                skip_ws()
                if index >= length:
                    raise ValueError("Unterminated fingerprint list")
                if text[index] == ")":
                    index += 1
                    return values
                values.append(parse_value())
        if char == ")":
            raise ValueError("Unexpected closing parenthesis in fingerprint signature")
        return parse_atom()

    value = parse_value()
    skip_ws()
    if index != length or not isinstance(value, list) or len(value) != 6:
        raise ValueError("Malformed fingerprint signature")
    return value


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
