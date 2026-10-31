"""Issue #216: read-only shared mounting-frame physical ENDPOINT evidence.

This does not override strict full-span Q03, create a physical owner, change
electrical endpoints, or establish the centerline/length of a Conduit.
All input records must come from a fresh, complete same-DWG witness.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

State = Literal["ENDPOINT_CANDIDATE", "BLOCKED"]


@dataclass(frozen=True, slots=True)
class FrameWitness:
    field_device_id: str
    handle: str
    dwg_fingerprint: str
    building: str
    room: str
    posts: int
    # Actual AutoCAD bounding box, not the frame block's insertion coordinates.
    min_x_mm: str
    min_y_mm: str
    max_x_mm: str
    max_y_mm: str


@dataclass(frozen=True, slots=True)
class DeviceWitness:
    field_device_id: str
    handle: str
    dwg_fingerprint: str
    building: str
    room: str
    mount_height_mm: str
    x_mm: str
    y_mm: str
    line_designation: str
    board_owner_id: str
    assigned_conduit_id: str


@dataclass(frozen=True, slots=True)
class MountingGroupPreview:
    state: State
    frame_owner_id: str | None
    member_device_ids: tuple[str, ...]
    issues: tuple[str, ...]
    # Frame membership does not by itself prove physical Conduit extent.
    can_set_conduit_length: bool = False
    can_publish_quantity: bool = False


def _number(text: str) -> Decimal | None:
    try:
        result = Decimal(str(text))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return result if result.is_finite() else None


def _inside(frame: FrameWitness, point: DeviceWitness) -> bool:
    values = tuple(
        _number(value)
        for value in (
            frame.min_x_mm,
            frame.min_y_mm,
            frame.max_x_mm,
            frame.max_y_mm,
            point.x_mm,
            point.y_mm,
        )
    )
    if any(v is None for v in values):
        return False
    x0, y0, x1, y1, x, y = values
    return x0 < x1 and y0 < y1 and x0 <= x <= x1 and y0 <= y <= y1


def preview_shared_mounting_frame(
    *,
    frame: FrameWitness,
    devices: tuple[DeviceWitness, ...],
    all_frames: tuple[FrameWitness, ...],
    fresh_complete_dwg_witness: bool,
    common_tube_confirmed_by_engineer: bool,
) -> MountingGroupPreview:
    """Prove 2 devices occupy one unambiguous physical frame; never infer G.

    `all_frames` must be the *complete* frame inventory from one verified DWG,
    not a search for the nearest frame; source must attest inventory freshness.
    Even an ENDPOINT_CANDIDATE needs independent Conduit geometry/compatibility
    before an actual length or Q03 physical-owner write is permitted.
    """
    issues: list[str] = []
    if not fresh_complete_dwg_witness:
        issues.append("DWG_WITNESS_NOT_FRESH_AND_COMPLETE")
    if not common_tube_confirmed_by_engineer:
        issues.append("COMMON_PHYSICAL_TUBE_NOT_CONFIRMED")
    if not frame.field_device_id or not frame.handle or not frame.dwg_fingerprint:
        issues.append("FRAME_IDENTITY_MISSING")
    if frame.posts != 2:
        issues.append("NOT_TWO_POSITION_FRAME")
    if not frame.building.strip() or not frame.room.strip():
        issues.append("FRAME_LOCATION_MISSING")
    if len(devices) != 2:
        issues.append("EXACTLY_TWO_DEVICES_REQUIRED")
    if len({f.field_device_id for f in all_frames}) != len(all_frames):
        issues.append("DUPLICATE_FRAME_OWNER")
    if len({f.handle for f in all_frames}) != len(all_frames):
        issues.append("DUPLICATE_FRAME_HANDLE")
    if sum(f.field_device_id == frame.field_device_id for f in all_frames) != 1:
        issues.append("FRAME_NOT_UNIQUE_IN_COMPLETE_INVENTORY")
    if any(f.dwg_fingerprint != frame.dwg_fingerprint for f in all_frames):
        issues.append("MIXED_FRAME_DWG_WITNESS")
    if len(devices) == 2:
        if len({d.field_device_id for d in devices}) != 2 or len(
            {d.handle for d in devices}
        ) != 2:
            issues.append("DUPLICATE_DEVICE")
        if len({d.line_designation for d in devices}) != 2:
            issues.append("ELECTRICAL_LINE_IDENTITY_NOT_DISTINCT")
        if len({d.board_owner_id for d in devices}) != 1 or not all(
            d.board_owner_id for d in devices
        ):
            issues.append("SOURCE_BOARD_NOT_SHARED")
        if len({d.assigned_conduit_id for d in devices}) != 1 or not all(
            d.assigned_conduit_id for d in devices
        ):
            issues.append("CONDUIT_ASSIGNMENT_NOT_SHARED")
        heights = [_number(d.mount_height_mm) for d in devices]
        if any(h is None or h < 0 for h in heights) or heights[0] != heights[1]:
            issues.append("MOUNT_HEIGHT_NOT_SHARED")
        for d in devices:
            if not d.field_device_id or not d.handle or not d.line_designation:
                issues.append("DEVICE_IDENTITY_MISSING")
            if d.dwg_fingerprint != frame.dwg_fingerprint:
                issues.append("DEVICE_DWG_WITNESS_DIFFERS")
            if (d.building, d.room) != (frame.building, frame.room):
                issues.append("BUILDING_ROOM_DIFFERS")
            if not _inside(frame, d):
                issues.append("DEVICE_OUTSIDE_VERIFIED_FRAME")
            candidates = [f for f in all_frames if _inside(f, d)]
            if len(candidates) != 1 or candidates[0].field_device_id != frame.field_device_id:
                issues.append("AMBIGUOUS_FRAME_MEMBERSHIP")
    normalized = tuple(sorted(set(issues)))
    return MountingGroupPreview(
        state="BLOCKED" if normalized else "ENDPOINT_CANDIDATE",
        frame_owner_id=frame.field_device_id if not normalized else None,
        member_device_ids=tuple(sorted(d.field_device_id for d in devices)),
        issues=normalized,
    )
