"""Out-of-process AutoCAD COM adapter. Never imports application persistence code."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
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


def _definition_metadata(document, name: str) -> list[str] | None:
    try:
        definition = document.Blocks.Item(name)
    except Exception:
        return None
    tags: list[str] = []
    for entity in definition:
        try:
            if str(entity.ObjectName) == "AcDbAttributeDefinition":
                tags.append(str(entity.TagString))
        except (AttributeError, pythoncom.com_error):
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
) -> dict[str, Any]:
    if str(entity.ObjectName) != "AcDbBlockReference":
        raise RuntimeError(f"Handle {entity.Handle} is not a block reference")
    name = _effective_name(entity)
    if definition_names is None or name in definition_names:
        if name not in definition_cache:
            definition_cache[name] = _definition_metadata(document, name)
        definition_tags = definition_cache[name]
    else:
        definition_tags = None
    try:
        dynamic = bool(entity.IsDynamicBlock)
    except Exception:
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


def _scan(
    document,
    identity: str,
    definition_names: set[str] | None = None,
    progress=None,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    definition_cache: dict[str, list[str] | None] = {}
    if progress:
        progress("scan_modelspace_started")
    for index, entity in enumerate(document.ModelSpace, start=1):
        if progress and index % 250 == 0:
            progress(f"scan_modelspace_progress_{index}")
        if str(entity.ObjectName) != "AcDbBlockReference":
            continue
        observations.append(
            _observation_payload(document, entity, definition_names, definition_cache)
        )
    if progress:
        progress("scan_modelspace_completed")
    return {
        "document_identity": identity,
        "observations": observations,
        "source_metadata": _source_metadata(document),
    }


def _scan_handles(
    document,
    identity: str,
    handles: list[str],
    definition_names: set[str] | None = None,
    progress=None,
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
            _observation_payload(document, entity, definition_names, definition_cache)
        )
    if progress:
        progress("scan_handles_completed")
    return {
        "document_identity": identity,
        "observations": observations,
        "source_metadata": _source_metadata(document),
    }


def _fingerprint_lisp(output_path: Path) -> str:
    path = output_path.as_posix().replace('"', '"')
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
(setq ss (ssget "_X" (list (cons 0 "INSERT") (cons 410 "Model"))))
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


def _fingerprints(document, identity: str, *, timeout_seconds: float = 15.0) -> dict[str, Any]:
    fd, raw_path = tempfile.mkstemp(prefix="nlp3-cad-fingerprint-", suffix=".txt")
    os.close(fd)
    Path(raw_path).unlink(missing_ok=True)
    try:
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
        document.SendCommand(_fingerprint_lisp(Path(raw_path)) + "\n")
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
