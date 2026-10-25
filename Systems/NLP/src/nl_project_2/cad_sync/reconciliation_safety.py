"""Declared snapshot authority, not independent proof of DWG completeness."""

from collections.abc import Mapping


def is_authoritative_scan_metadata(source_metadata: object) -> bool:
    """Allow legacy unfiltered metadata; reject partial or malformed declarations.

    Only literal booleans are valid flags. Unrelated metadata is ignored.
    A supplied exclusion count must be a nonnegative integer and zero; positive
    exclusions contradict full-snapshot authority even if flags were omitted.
    """
    if not isinstance(source_metadata, Mapping):
        return False
    # Diagnostic provenance cannot be promoted by deleting/flipping completeness flags.
    if source_metadata.get("scan_mode") in ("FILTERED_FINGERPRINT", "FILTERED_COM_FALLBACK"):
        return False
    if "layer_filter_applied" in source_metadata:
        if source_metadata["layer_filter_applied"] is not False:
            return False
    if "scan_is_complete_for_reconciliation" in source_metadata:
        if source_metadata["scan_is_complete_for_reconciliation"] is not True:
            return False
    if "skipped_block_references" in source_metadata:
        skipped = source_metadata["skipped_block_references"]
        if type(skipped) is not int or skipped != 0:
            return False
    return True
