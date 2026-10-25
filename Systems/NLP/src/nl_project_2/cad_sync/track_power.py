"""D10: canonical ownership checks for internal 48 V DALI track power.

The approved CAD contract makes LIGHT_TRACK_DALI_48V/CABLE_SOURCE=TRACK.NNN
an *internal rail membership*, not a measured external cable segment.
The accepted field_device CABLE_SOURCE is retained; no physical cable,
length, conduit or PSU can be inferred from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select

from nl_project_2.persistence.schema import field_device

_TRACK = re.compile(r"^TRACK\.[0-9]{3}$")
_POWER_LINE = re.compile(r"^4[0-9]{2}(?:\.[0-9]{2})?$")
_DALI_POINT = re.compile(r"^(9[0-9]{2})\.[0-9]{3}$")


class TrackInternalPowerError(RuntimeError):
    """An internal track source cannot be adopted without an exact Project owner."""


@dataclass(frozen=True, slots=True)
class TrackInternalPowerLink:
    light_field_device_id: str
    light_handle: str
    track_field_device_id: str
    track_id: str
    cable_base: str
    bus_id: str
    length_m_decimal: None = None
    conduit_id: None = None


def selected_internal_track_power(
    connection,
    *,
    project_id: str,
    active_handles: set[str],
    device_ids: dict[str, str],
) -> tuple[TrackInternalPowerLink, ...]:
    """Resolve selected lights against all ACTIVE accepted Project track owners.

    Called *within the existing DWG sync transaction*, after selected
    field_device rows are upserted. Partial DWG scans may refer to a
    previously accepted track; missing/duplicate/cross-bus owners are rejected.
    """
    selected_ids = {device_ids[h] for h in active_handles if h in device_ids}
    if not selected_ids:
        return ()
    rows = list(
        connection.execute(
            select(
                field_device.c.id,
                field_device.c.entity_handle,
                field_device.c.block_kind,
                field_device.c.normalized_fields_json,
            ).where(
                field_device.c.project_id == project_id,
                field_device.c.lifecycle == "ACTIVE",
            )
        ).mappings()
    )
    tracks: dict[str, list] = {}
    for row in rows:
        if row["block_kind"] != "TRACK_DALI":
            continue
        fields = dict(row["normalized_fields_json"] or {})
        track_id = str(fields.get("TRACK_ID") or "").strip()
        if track_id:
            tracks.setdefault(track_id, []).append(row)

    result = []
    for row in rows:
        if row["id"] not in selected_ids or row["block_kind"] != "LIGHT_TRACK_DALI_48V":
            continue
        fields = dict(row["normalized_fields_json"] or {})
        source = str(fields.get("CABLE_SOURCE") or "").strip()
        if not source.startswith("TRACK"):
            continue
        if not _TRACK.fullmatch(source):
            raise TrackInternalPowerError(f"TRACK_POWER_SOURCE_FORMAT:{source}")
        candidates = tracks.get(source, [])
        if len(candidates) != 1:
            raise TrackInternalPowerError(f"TRACK_POWER_OWNER_MISSING_OR_AMBIGUOUS:{source}")
        track = candidates[0]
        if track["id"] == row["id"]:
            raise TrackInternalPowerError(f"TRACK_POWER_SELF_SOURCE:{source}")
        track_fields = dict(track["normalized_fields_json"] or {})
        cable_id = str(fields.get("CABLE_ID") or "").strip()
        track_cable = str(track_fields.get("CABLE_ID") or "").strip()
        if not _POWER_LINE.fullmatch(cable_id) or not _POWER_LINE.fullmatch(track_cable):
            raise TrackInternalPowerError(f"TRACK_POWER_4YY_REQUIRED:{source}")
        base = cable_id.split(".", 1)[0]
        if track_cable.split(".", 1)[0] != base:
            raise TrackInternalPowerError(f"TRACK_POWER_CABLE_OWNER_MISMATCH:{source}")
        bus_id = str(track_fields.get("BUS_ID") or "").strip()
        point = _DALI_POINT.fullmatch(str(fields.get("BUS_POINT_ID") or "").strip())
        if (
            point is None
            or point.group(1) != bus_id
            or str(fields.get("BUS_SOURCE") or "").strip() != source
        ):
            raise TrackInternalPowerError(f"TRACK_POWER_BUS_OWNER_MISMATCH:{source}")
        result.append(
            TrackInternalPowerLink(
                light_field_device_id=row["id"],
                light_handle=str(row["entity_handle"] or ""),
                track_field_device_id=track["id"],
                track_id=source,
                cable_base=base,
                bus_id=bus_id,
            )
        )
    return tuple(sorted(result, key=lambda p: (p.cable_base, p.track_id, p.light_field_device_id)))
