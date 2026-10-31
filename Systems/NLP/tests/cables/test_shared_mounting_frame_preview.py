"""Issue #216 Q03: a shared two-position frame is not a shared cable endpoint."""

from dataclasses import replace

from nl_project_2.cables.shared_mounting_frame_preview import (
    DeviceWitness,
    FrameWitness,
    preview_shared_mounting_frame,
)

DOC = "a" * 64
FRAME_ID = "00000000-0000-4000-8000-000000000001"
DEVICE_204 = "00000000-0000-4000-8000-000000000002"
DEVICE_205 = "00000000-0000-4000-8000-000000000003"
BOARD_ID = "00000000-0000-4000-8000-000000000004"
CONDUIT_ID = "00000000-0000-4000-8000-000000000005"
OTHER_FRAME = "00000000-0000-4000-8000-000000000006"
OTHER_BOARD = "00000000-0000-4000-8000-000000000007"
OTHER_CONDUIT = "00000000-0000-4000-8000-000000000008"
FRAME = FrameWitness(
    FRAME_ID,
    "AA82",
    DOC,
    "Дом_2",
    "Гостиная",
    2,
    "19173.767744",
    "11140.146291",
    "19553.767744",
    "11340.146291",
)
FIRST = DeviceWitness(
    DEVICE_204,
    "AA88",
    DOC,
    "Дом_2",
    "Гостиная",
    "900",
    "19373.767744",
    "11160.146291",
    "204",
    BOARD_ID,
    CONDUIT_ID,
)
SECOND = DeviceWitness(
    DEVICE_205,
    "AA9A",
    DOC,
    "Дом_2",
    "Гостиная",
    "900",
    "19193.767744",
    "11160.146291",
    "205",
    BOARD_ID,
    CONDUIT_ID,
)


def proof(*, frame=FRAME, devices=(FIRST, SECOND), all_frames=(FRAME,), fresh=True, confirmed=True):
    return preview_shared_mounting_frame(
        frame=frame,
        devices=devices,
        all_frames=all_frames,
        fresh_complete_dwg_witness=fresh,
        common_tube_confirmed_by_engineer=confirmed,
    )


def test_shared_frame_and_explicit_confirmation_only_prove_endpoint():
    result = proof()
    assert result.state == "ENDPOINT_CANDIDATE"
    assert result.frame_owner_id == FRAME_ID
    assert result.member_device_ids == (DEVICE_204, DEVICE_205)
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
    competing = replace(FRAME, field_device_id=OTHER_FRAME, handle="BB33")
    result = proof(all_frames=(FRAME, competing))
    assert result.state == "BLOCKED"
    assert "AMBIGUOUS_FRAME_MEMBERSHIP" in result.issues


def test_different_document_or_outside_frame_rejected():
    result = proof(devices=(FIRST, replace(SECOND, dwg_fingerprint="stale", x_mm="17000")))
    assert result.state == "BLOCKED"
    assert "DEVICE_DWG_WITNESS_DIFFERS" in result.issues
    assert "DEVICE_OUTSIDE_VERIFIED_FRAME" in result.issues


def test_different_height_or_board_rejected():
    result = proof(
        devices=(FIRST, replace(SECOND, mount_height_mm="910", board_owner_id=OTHER_BOARD))
    )
    assert result.state == "BLOCKED"
    assert "MOUNT_HEIGHT_NOT_SHARED" in result.issues
    assert "SOURCE_BOARD_NOT_SHARED" in result.issues


def test_different_conduit_cannot_form_shared_tube():
    result = proof(devices=(FIRST, replace(SECOND, assigned_conduit_id=OTHER_CONDUIT)))
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


def test_noncanonical_frame_and_conduit_owners_are_blocked():
    invalid_frame = replace(FRAME, field_device_id="frame-visible-label")
    result = proof(frame=invalid_frame, all_frames=(invalid_frame,))
    assert result.state == "BLOCKED"
    assert "FRAME_IDENTITY_MISSING" in result.issues
    other = proof(devices=(FIRST, replace(SECOND, assigned_conduit_id="146.PP20")))
    assert other.state == "BLOCKED"
    assert "DEVICE_IDENTITY_MISSING" in other.issues


def test_informal_dwg_label_does_not_count_as_document_hash():
    informal = replace(FRAME, dwg_fingerprint="working.dwg")
    result = proof(frame=informal, all_frames=(informal,))
    assert result.state == "BLOCKED"
    assert "FRAME_IDENTITY_MISSING" in result.issues
