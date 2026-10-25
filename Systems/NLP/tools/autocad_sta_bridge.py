"""Out-of-process AutoCAD COM adapter. Never imports application persistence code."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from functools import cache
from multiprocessing.connection import Listener
from pathlib import Path
from typing import Any

import pythoncom
import win32com.client

PROTOCOL_VERSION = "1.1"
ADAPTER_VERSION = "1.1"
AUTOCAD_PROG_IDS = (
    "AutoCAD.Application.24.3",
    "AutoCAD.Application.24.2",
    "AutoCAD.Application.24.1",
    "AutoCAD.Application.24",
    "AutoCAD.Application",
)
_FINGERPRINT_DONE = "__NLP_DONE__"


def _active_application():
    last_error: Exception | None = None
    for prog_id in AUTOCAD_PROG_IDS:
        try:
            return win32com.client.GetActiveObject(prog_id)
        except Exception as exc:  # COM errors differ between AutoCAD releases.
            last_error = exc
    raise RuntimeError("AutoCAD is unavailable") from last_error


def _document_identity(document) -> str:
    full_name = str(document.FullName or "").strip()
    return full_name or str(document.Name)


def _require_document(application, expected: str):
    try:
        document = application.ActiveDocument
    except Exception as exc:
        raise RuntimeError("AutoCAD has no open document") from exc
    if document is None:
        raise RuntimeError("AutoCAD has no open document")
    identity = _document_identity(document)
    if expected and identity.casefold() != expected.casefold():
        raise RuntimeError(f"active DWG identity mismatch: expected {expected!r}, got {identity!r}")
    return document, identity


def _definition_metadata(document, name: str, *, strict: bool = False) -> list[str] | None:
    try:
        definition = document.Blocks.Item(name)
    except Exception:
        if strict:
            raise
        return None
    tags: list[str] = []
    for entity in definition:
        try:
            if str(entity.ObjectName) == "AcDbAttributeDefinition":
                tags.append(str(entity.TagString))
        except (AttributeError, pythoncom.com_error):
            if strict:
                raise
            continue
    return tags


def _effective_name(entity) -> str:
    try:
        return str(entity.EffectiveName)
    except Exception:
        return str(entity.Name)


def _attributes(entity) -> dict[str, str]:
    if not bool(entity.HasAttributes):
        return {}
    return {str(item.TagString): str(item.TextString) for item in entity.GetAttributes()}


def _send_progress(connection, stage: str) -> None:
    connection.send_bytes(
        json.dumps({"type": "progress", "stage": stage}, ensure_ascii=False).encode("utf-8")
    )


def _document_info(document, identity: str) -> dict[str, Any]:
    return {
        "document_identity": identity,
        "document_name": str(document.Name),
        "read_only": bool(document.ReadOnly),
        "saved": bool(document.Saved),
        "dbmod": int(document.GetVariable("DBMOD")),
    }


def _source_metadata(document) -> dict[str, Any]:
    return {
        "adapter_version": ADAPTER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "document_name": str(document.Name),
        "full_name": str(document.FullName or ""),
        "read_only": bool(document.ReadOnly),
        "saved": bool(document.Saved),
        "dbmod": int(document.GetVariable("DBMOD")),
    }


def _observation_payload(
    document,
    entity,
    definition_names: set[str] | None,
    definition_cache: dict[str, list[str] | None],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    if str(entity.ObjectName) != "AcDbBlockReference":
        raise RuntimeError(f"Handle {entity.Handle} is not a block reference")
    name = _effective_name(entity)
    if definition_names is None or name in definition_names:
        if name not in definition_cache:
            definition_cache[name] = (
                _definition_metadata(document, name, strict=True)
                if strict
                else _definition_metadata(document, name)
            )
        definition_tags = definition_cache[name]
    else:
        definition_tags = None
    try:
        dynamic = bool(entity.IsDynamicBlock)
    except Exception:
        if strict:
            raise
        dynamic = None
    point = entity.InsertionPoint
    return {
        "effective_name": name,
        "layer": str(entity.Layer),
        "raw_attributes": _attributes(entity),
        "x": point[0],
        "y": point[1],
        "handle": str(entity.Handle),
        "definition_tags": definition_tags,
        "is_dynamic": dynamic,
    }


@cache
def _working_layer_parser() -> Callable[[object], int | None]:
    # Import only the pure C1 file: importing cad_contract executes its __init__
    # and pulls application persistence dependencies into the standalone bridge.
    path = Path(__file__).resolve().parents[1] / "src/nl_project_2/cad_contract/layer_names.py"
    spec = importlib.util.spec_from_file_location("_nlp_sta_layer_names", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load working-layer parser from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_working_layer_name


def is_working_layer_for_scan(layer: object) -> bool:
    """Use C1 without application imports; load lazily only for explicit opt-in."""
    return _working_layer_parser()(layer) is not None


def _scan(
    document,
    identity: str,
    definition_names: set[str] | None = None,
    progress=None,
    *,
    include_layer: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Scan once; optional filtering is internal and never deletion-authoritative.

    The protocol does not enable include_layer. Consumers must gain a separate
    reconciliation safety gate before using filtered results for synchronization.
    Layer access and predicate errors propagate rather than returning a subset.
    """
    observations: list[dict[str, Any]] = []
    skipped_block_references = 0
    definition_cache: dict[str, list[str] | None] = {}
    if progress:
        progress("scan_modelspace_started")
    for index, entity in enumerate(document.ModelSpace, start=1):
        if progress and index % 250 == 0:
            progress(f"scan_modelspace_progress_{index}")
        if str(entity.ObjectName) != "AcDbBlockReference":
            continue
        if include_layer is not None and not include_layer(entity.Layer):
            skipped_block_references += 1
            continue
        observations.append(
            _observation_payload(document, entity, definition_names, definition_cache)
        )
    if progress:
        progress("scan_modelspace_completed")
    metadata = _source_metadata(document)
    if include_layer is not None:
        metadata.update(
            layer_filter_applied=True,
            skipped_block_references=skipped_block_references,
            scan_is_complete_for_reconciliation=False,
        )
    return {
        "document_identity": identity,
        "observations": observations,
        "source_metadata": metadata,
    }


def _scan_handles(
    document,
    identity: str,
    handles: list[str],
    definition_names: set[str] | None = None,
    progress=None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    definition_cache: dict[str, list[str] | None] = {}
    if progress:
        progress("scan_handles_started")
    for handle in handles:
        try:
            entity = document.HandleToObject(str(handle))
        except Exception as exc:
            raise RuntimeError(f"Handle {handle} is unavailable during incremental scan") from exc
        observations.append(
            _observation_payload(
                document, entity, definition_names, definition_cache, strict=strict
            )
        )
    if progress:
        progress("scan_handles_completed")
    return {
        "document_identity": identity,
        "observations": observations,
        "source_metadata": _source_metadata(document),
    }


def _fingerprint_lisp(
    output_path: Path, *, handles: tuple[str, ...] | None = None, expected_identity: str = ""
) -> str:
    path = _lisp_string(output_path.as_posix())[1:-1]
    selection = '(setq ss (ssget "_X" (list (cons 0 "INSERT") (cons 410 "Model"))))'
    guard = ""
    definition_check = ""
    if handles is not None:
        _checked_handles(handles)
        definition_check = '(if (vl-catch-all-error-p b) (error "Selected definition read failed"))'
        quoted = " ".join(_lisp_string(handle) for handle in handles)
        selection = f"""(setq ss (ssadd))
(foreach h '({quoted})
  (setq en (handent h))
  (if (or (not en) (/= (cdr (assoc 0 (entget en))) "INSERT")
          (/= (cdr (assoc 410 (entget en))) "Model"))
    (error "Selected INSERT no longer exists in model space"))
  (ssadd en ss))"""
        if not expected_identity:
            raise RuntimeError("Explicit document identity required for selected fingerprint")
        guard = f"""(if (/= (strcase (vla-get-FullName d))
                          (strcase {_lisp_string(expected_identity)}))
                    (error "Selected fingerprint document changed"))"""
    return f"""(progn
(vl-load-com)
(setq nlp3-dc nil)
(defun nlp3-def (bs n / hit b r x)
  (setq hit (assoc n nlp3-dc))
  (if hit
    (cdr hit)
    (progn
      (setq r nil)
      (setq b (vl-catch-all-apply 'vla-item (list bs n)))
      {definition_check}
      (if (not (vl-catch-all-error-p b))
        (vlax-for x b
          (if (= (vla-get-ObjectName x) "AcDbAttributeDefinition")
            (setq r (cons (vla-get-TagString x) r)))))
      (setq r (reverse r))
      (setq nlp3-dc (cons (cons n r) nlp3-dc))
      r)))
(defun nlp3-attrs (o / r a)
  (setq r nil)
  (if (= :vlax-true (vla-get-HasAttributes o))
    (foreach a (vlax-invoke o 'GetAttributes)
      (setq r (cons (list (vla-get-TagString a) (vla-get-TextString a)) r))))
  (reverse r))
(setq d (vla-get-ActiveDocument (vlax-get-acad-object)))
(setq bs (vla-get-Blocks d))
{guard}
{selection}
(setq f (open "{path}" "w" "utf8"))
(if ss
  (progn
    (setq i 0)
    (repeat (sslength ss)
      (setq o (vlax-ename->vla-object (ssname ss i)))
      (setq n (if (vlax-property-available-p o 'EffectiveName)
                (vla-get-EffectiveName o)
                (vla-get-Name o)))
      (setq p (vlax-safearray->list
                (vlax-variant-value (vla-get-InsertionPoint o))))
      (setq dy (if (vlax-property-available-p o 'IsDynamicBlock)
                 (vla-get-IsDynamicBlock o)
                 :vlax-false))
      (write-line
        (strcat
          (vla-get-Handle o)
          "\\t"
          (vl-prin1-to-string
            (list n (vla-get-Layer o) p dy (nlp3-attrs o) (nlp3-def bs n))))
        f)
      (setq i (1+ i)))))
(write-line "{_FINGERPRINT_DONE}" f)
(close f)
(princ))
""".replace("\n", " ")


def _fingerprints(
    document,
    identity: str,
    *,
    timeout_seconds: float = 15.0,
    handles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    fd, raw_path = tempfile.mkstemp(prefix="nlp3-cad-fingerprint-", suffix=".txt")
    os.close(fd)
    Path(raw_path).unlink(missing_ok=True)
    try:
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        document.SendCommand(
            _fingerprint_lisp(Path(raw_path), handles=handles, expected_identity=identity) + "\n"
        )
        deadline = time.monotonic() + timeout_seconds
        text = ""
        while time.monotonic() < deadline:
            pythoncom.PumpWaitingMessages()
            path = Path(raw_path)
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    text = ""
                if text.splitlines()[-1:] == [_FINGERPRINT_DONE]:
                    break
            time.sleep(0.02)
        else:
            raise RuntimeError("AutoCAD fingerprint command timed out")
        order: list[str] = []
        signatures: dict[str, str] = {}
        for line in text.splitlines():
            if line == _FINGERPRINT_DONE:
                continue
            handle, separator, signature = line.partition("\t")
            if not separator or not handle:
                raise RuntimeError("Malformed AutoCAD fingerprint row")
            order.append(handle)
            signatures[handle] = signature
        if len(order) != len(signatures):
            raise RuntimeError("Duplicate AutoCAD handles in fingerprint snapshot")
        return {
            "document_identity": identity,
            "handles": order,
            "signatures": signatures,
            "source_metadata": _source_metadata(document),
        }
    finally:
        Path(raw_path).unlink(missing_ok=True)


def _lisp_string(value: str) -> str:
    """AutoLISP string literal; never interpolate document/path/handle as code."""
    if any(ord(char) < 32 for char in value):
        raise ValueError("Control characters are not supported in LISP paths")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _checked_handles(handles) -> tuple[str, ...]:
    values = tuple(handles)
    if any(not isinstance(h, str) or re.fullmatch(r"[0-9A-F]+", h) is None for h in values):
        raise RuntimeError("Invalid canonical INSERT handle")
    if len(set(values)) != len(values):
        raise RuntimeError("Duplicate INSERT handles")
    return values


def _insert_census(document, identity: str) -> dict[str, str]:
    """Complete lightweight census; reads no names, points, attributes or definitions."""
    if _document_identity(document).casefold() != identity.casefold():
        raise RuntimeError("Census document identity changed")
    census: dict[str, str] = {}
    for entity in document.ModelSpace:
        if str(entity.ObjectName) != "AcDbBlockReference":
            continue
        handle = str(entity.Handle)
        _checked_handles((handle,))
        if handle in census:
            raise RuntimeError("Duplicate census handle")
        layer = entity.Layer
        if not isinstance(layer, str):
            raise RuntimeError("Invalid census layer")
        census[handle] = layer
    if _document_identity(document).casefold() != identity.casefold():
        raise RuntimeError("Census document identity changed")
    return census


def _scan_working_layers(
    document, identity, tracked_handles, definition_names=None, *, timeout_seconds=15.0
):
    """Explicit diagnostic operation, never a reconciliation snapshot.

    One shared COM handle/layer census selects heavy work for BOTH LISP and COM.
    Surviving tracked handles are always read, including excluded/legacy layers.
    No deletion proof is inferred from a lookup failure or absent heavy payload.
    """
    if not identity or not str(document.FullName or ""):
        raise RuntimeError("Saved-path document identity required for census read")
    tracked = _checked_handles(tracked_handles)
    before = _insert_census(document, identity)
    selected = tuple(
        h for h, layer in before.items() if is_working_layer_for_scan(layer) or h in tracked
    )
    try:
        payload = _fingerprints(
            document, identity, timeout_seconds=timeout_seconds, handles=selected
        )
        if tuple(payload["handles"]) != selected or set(payload["signatures"]) != set(selected):
            raise RuntimeError("Selected fingerprint owner set mismatch")
        mode = "FILTERED_FINGERPRINT"
    except Exception:
        # Discard the entire failed LISP result; never merge it into COM fallback.
        payload = _scan_handles(document, identity, list(selected), definition_names, strict=True)
        mode = "FILTERED_COM_FALLBACK"
    after = _insert_census(document, identity)
    if before != after:
        raise RuntimeError("INSERT census changed during filtered read; repeat full read")
    metadata = dict(payload["source_metadata"])
    metadata.update(
        layer_filter_applied=True,
        scan_is_complete_for_reconciliation=False,
        skipped_block_references=len(before) - len(selected),
        scan_mode=mode,
    )
    return {
        **payload,
        "source_metadata": metadata,
        "census_before": before,
        "census_after": after,
        "selected_handles": list(selected),
        "tracked_handles": list(tracked),
        "status": "REQUIRES_ATTENTION",
        "next_action": "Use full unfiltered read for preview/apply; absence is not proven.",
    }


def _find_attribute(document, handle: str, tag: str):
    entity = document.HandleToObject(handle)
    if str(entity.ObjectName) != "AcDbBlockReference":
        raise RuntimeError(f"Handle {handle} is not a block reference")
    matches = [item for item in entity.GetAttributes() if str(item.TagString) == tag]
    if len(matches) != 1:
        raise RuntimeError(f"Handle {handle} has {len(matches)} attributes named {tag}")
    return entity, matches[0]


def _write_attributes(document, identity: str, changes: list[dict[str, str]]) -> dict[str, Any]:
    targets = []
    identities: set[tuple[str, str]] = set()
    for change in changes:
        handle = str(change["handle"])
        tag = str(change["tag"])
        key = (handle, tag)
        if key in identities:
            raise RuntimeError(f"duplicate write target {handle}/{tag}")
        identities.add(key)
        entity, attribute = _find_attribute(document, handle, tag)
        if _effective_name(entity) != change["expected_block_name"]:
            raise RuntimeError(f"block-name precondition failed for {handle}")
        if str(entity.Layer) != change["expected_layer"]:
            raise RuntimeError(f"layer precondition failed for {handle}")
        if str(attribute.TextString) != change["old_value"]:
            raise RuntimeError(f"old-value precondition failed for {handle}/{tag}")
        targets.append((attribute, change))
    written = []
    failures = []
    document.StartUndoMark()
    try:
        for attribute, change in targets:
            try:
                attribute.TextString = change["new_value"]
                written.append((attribute, change))
            except Exception as exc:
                failures.append(
                    {
                        "handle": change["handle"],
                        "tag": change["tag"],
                        "reason": "WRITE_FAILED",
                        "error_category": type(exc).__name__,
                    }
                )
                break
        readback = []
        for _attribute, change in written:
            try:
                _entity, attribute = _find_attribute(document, change["handle"], change["tag"])
                value = str(attribute.TextString)
            except Exception as exc:
                failures.append(
                    {
                        "handle": change["handle"],
                        "tag": change["tag"],
                        "reason": "READBACK_FAILED",
                        "error_category": type(exc).__name__,
                    }
                )
                continue
            if value != change["new_value"]:
                failures.append(
                    {
                        "handle": change["handle"],
                        "tag": change["tag"],
                        "reason": "READBACK_MISMATCH",
                        "expected": change["new_value"],
                        "actual": value,
                    }
                )
                continue
            readback.append({"handle": change["handle"], "tag": change["tag"], "value": value})
    finally:
        document.EndUndoMark()
    return {
        "document_identity": identity,
        "readback": readback,
        "no_save_confirmed": True,
        "document_saved": bool(document.Saved),
        "status": "PARTIAL" if failures else "READ_BACK_OK",
        "failures": failures,
    }


def _serve(pipe: str) -> int:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    try:
        with Listener(pipe, family="AF_PIPE") as listener:
            with listener.accept() as connection:
                request = json.loads(connection.recv_bytes().decode("utf-8"))
                try:
                    _send_progress(connection, "com_connect_started")
                    application = _active_application()
                    _send_progress(connection, "com_connected")
                    document, identity = _require_document(
                        application, str(request.get("expected_document_identity", ""))
                    )
                    _send_progress(connection, "document_identity_verified")
                    operation = request.get("operation")
                    if operation == "document_identity":
                        result = _document_info(document, identity)
                    elif operation == "scan":
                        result = _scan(
                            document,
                            identity,
                            set(request.get("definition_names", [])),
                            lambda stage: _send_progress(connection, stage),
                        )
                    elif operation == "insert_census":
                        if not request.get("read_id") or not request.get(
                            "expected_document_identity"
                        ):
                            raise RuntimeError("Explicit census identity required")
                        result = {
                            "document_identity": identity,
                            "read_id": request["read_id"],
                            "census": _insert_census(document, identity),
                            "complete": True,
                            "unfiltered": True,
                        }
                    elif operation == "scan_working_layers":
                        if not request.get("read_id") or not request.get(
                            "expected_document_identity"
                        ):
                            raise RuntimeError("Explicit filtered read identity required")
                        result = _scan_working_layers(
                            document,
                            identity,
                            request.get("tracked_handles", []),
                            set(request.get("definition_names", [])),
                            timeout_seconds=float(request.get("timeout_seconds", 15.0)),
                        )
                        result["read_id"] = request["read_id"]
                    elif operation == "scan_handles":
                        result = _scan_handles(
                            document,
                            identity,
                            [str(value) for value in request.get("handles", [])],
                            set(request.get("definition_names", [])),
                            lambda stage: _send_progress(connection, stage),
                        )
                    elif operation == "fingerprint":
                        _send_progress(connection, "fingerprint_started")
                        result = _fingerprints(
                            document,
                            identity,
                            timeout_seconds=float(request.get("timeout_seconds", 15.0)),
                        )
                        _send_progress(connection, "fingerprint_completed")
                    elif operation == "write_attributes":
                        result = _write_attributes(document, identity, request.get("changes", []))
                    else:
                        raise RuntimeError(f"unsupported operation: {operation}")
                    response = {"type": "response", "ok": True, "result": result}
                except Exception as exc:
                    response = {
                        "type": "response",
                        "ok": False,
                        "error_category": type(exc).__name__,
                        "message": str(exc),
                    }
                connection.send_bytes(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        return 0
    finally:
        pythoncom.CoUninitialize()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipe", required=True)
    args = parser.parse_args(argv)
    return _serve(args.pipe)


if __name__ == "__main__":
    raise SystemExit(main())
