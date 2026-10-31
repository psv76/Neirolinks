"""Issue #216 Q03: a shared two-position frame is not a shared cable endpoint."""

from dataclasses import replace

from nl_project_2.cables.shared_mounting_frame_preview import (
    DeviceWitness,
    FrameWitness,
    preview_shared_mounting_frame,
)

DOC = "fresh-dwg-sha"
FRAME = FrameWitness(
    "frame-uuid", "AA82", DOC, "Дом_2", "Гостиная", 2,
    "19173.767744", "11140.146291", "19553.767744", "11340.146291",
)
FIRST = DeviceWitness(
    "device-204", "AA88", DOC, "Дом_2", "Гостиная", "900",
    "19373.767744", "11160.146291", "204", "board-20", "conduit-146",
)
SECOND = DeviceWitness(
    "device-205", "AA9A", DOC, "Дом_2", "Гостиная", "900",
    "19193.767744", "11160.146291", "205", "board-20", "conduit-146",
)


def proof(*, frame=FRAME, devices=(FIRST, SECOND), all_frames=(FRAME,),
          fresh=True, confirmed=True):
    return preview_shared_mounting_frame(
        frame=frame, devices=devices, all_frames=all_frames,
        fresh_complete_dwg_witness=fresh,
        common_tube_confirmed_by_engineer=confirmed,
    )


def test_shared_frame_and_explicit_confirmation_only_prove_endpoint():
    result = proof()
    assert result.state == "ENDPOINT_CANDIDATE"
    assert result.frame_owner_id == "frame-uuid"
    assert result.member_device_ids == ("device-204", "device-205")
    assert result.issues == ()
    assert result.can_set_conduit_length is False
    assert result.can_publish_quantity is False


def test_not_approved_by_proximity_alone():
    result = proof(confirmed=False)
    assert result.state == "BLOCKED"
    assert "COMMON_PHYSICAL_TUBE_NOT_CONFIRMED" in result.issues


def test_stale_or_incomplete_frame_inventory_is_blocked():
    result = proof(fresh=False)
    assert result.state == "BLOCKED"
    assert "DWG_WITNESS_NOT_FRESH_AND_COMPLETE" in result.issues


def test_same_room_proximity_but_two_frames_is_ambiguous():
    competing = replace(FRAME, field_device_id="another-frame", handle="BB33")
    result = proof(all_frames=(FRAME, competing))
    assert result.state == "BLOCKED"
    assert "AMBIGUOUS_FRAME_MEMBERSHIP" in result.issues


def test_different_document_or_outside_frame_rejected():
    result = proof(devices=(FIRST, replace(SECOND, dwg_fingerprint="stale", x_mm="17000")))
    assert result.state == "BLOCKED"
    assert "DEVICE_DWG_WITNESS_DIFFERS" in result.issues
    assert "DEVICE_OUTSIDE_VERIFIED_FRAME" in result.issues


def test_different_height_or_board_rejected():
    result = proof(devices=(FIRST, replace(SECOND, mount_height_mm="910", board_owner_id="other")))
    assert result.state == "BLOCKED"
    assert "MOUNT_HEIGHT_NOT_SHARED" in result.issues
    assert "SOURCE_BOARD_NOT_SHARED" in result.issues


def test_different_conduit_cannot_form_shared_tube():
    result = proof(devices=(FIRST, replace(SECOND, assigned_conduit_id="other")))
    assert result.state == "BLOCKED"
    assert "CONDUIT_ASSIGNMENT_NOT_SHARED" in result.issues


def test_missing_frame_inventory_and_duplicate_device_blocked():
    result = proof(devices=(FIRST, FIRST), all_frames=())
    assert result.state == "BLOCKED"
    assert "DUPLICATE_DEVICE" in result.issues
    assert "FRAME_NOT_UNIQUE_IN_COMPLETE_INVENTORY" in result.issues


def test_frame_has_no_physical_endpoint_with_three_posts():
    result = proof(frame=replace(FRAME, posts=3), all_frames=(replace(FRAME, posts=3),))
    assert result.state == "BLOCKED"
    assert "NOT_TWO_POSITION_FRAME" in result.issues
