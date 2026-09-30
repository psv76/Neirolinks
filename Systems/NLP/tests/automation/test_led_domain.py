from decimal import Decimal

import pytest

from nl_project_2.automation import (
    LedRuleError,
    calculate_led_load,
    cut_segment,
    led_layout,
    normalize_led_kind,
    pack_reels,
)


def _cut(identifier, length, step=50, reel=15000):
    return cut_segment(identifier, length, step, reel)


def test_normalization_layout_and_all_cut_boundary_cases():
    with pytest.raises(LedRuleError, match="Unsupported canonical LED kind"):
        normalize_led_kind("MIX")
    assert led_layout("MONO") == (1, 2)
    assert led_layout("CCT") == (2, 3)
    assert led_layout("RGB") == (3, 4)
    assert led_layout("RGBW") == (4, 5)

    assert _cut("001", 1).cut_length_mm == 50
    assert _cut("002", 50).cut_length_mm == 50
    assert _cut("003", 51).cut_length_mm == 100
    assert _cut("004", 15000).cut_length_mm == 15000
    long = _cut("005", 15001)
    assert (long.cut_length_mm, long.error) == (
        Decimal("15050"),
        "LED_SEGMENT_EXCEEDS_REEL",
    )
    assert _cut("006", 0).error == "LED_INVALID_DESIGN_LENGTH"
    assert _cut("007", -1).error == "LED_INVALID_DESIGN_LENGTH"
    assert _cut("008", "27.79", "27.78", 5000).cut_length_mm == Decimal("55.56")
    assert _cut("009", "33.33", "33.33", 5000).cut_length_mm == Decimal("33.33")
    literal = _cut("010", 5000, "27.78", 5000)
    assert literal.cut_length_mm == Decimal("5000.40")
    assert literal.error == "LED_SEGMENT_EXCEEDS_REEL"


def test_deterministic_ffd_groups_remainders_and_whole_reels():
    segments = tuple(
        _cut(identifier, length)
        for identifier, length in (
            ("s8", 8000),
            ("s7", 7000),
            ("s6", 6000),
            ("s5", 5000),
        )
    )
    result = pack_reels(
        segments,
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=15000,
    )
    assert [reel.segment_ids for reel in result.reels] == [
        ("s8", "s7"),
        ("s6", "s5"),
    ]
    assert result.required_quantity_mm == 26000
    assert result.purchased_reels == 2
    assert result.purchased_length_mm == 30000
    assert result.remainder_mm == 4000
    assert result.unusable_remainder_mm == 0

    exact_fill = pack_reels(
        (_cut("nine", 9000), _cut("six", 6000)),
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=15000,
    )
    assert exact_fill.purchased_reels == 1
    assert exact_fill.remainder_mm == 0

    equal = (_cut("segment-B", 5000), _cut("segment-A", 5000))
    forward = pack_reels(
        equal,
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=15000,
    )
    reverse = pack_reels(
        tuple(reversed(equal)),
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=15000,
    )
    assert forward == reverse
    assert forward.reels[0].segment_ids == ("segment-A", "segment-B")

    fraction = pack_reels(
        (_cut("fraction", "27.78", "27.78", 5000),),
        reel_length_mm=5000,
        cut_increment_mm="27.78",
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=5000,
    )
    assert fraction.remainder_mm == Decimal("4972.22")
    assert fraction.unusable_remainder_mm == Decimal("27.38")


def test_invalid_segment_and_incomplete_purchase_never_create_hidden_split():
    long = _cut("long", 15001)
    blocked = pack_reels(
        (long,),
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="FULL_REEL",
        minimum_purchase_increment_mm=15000,
    )
    assert blocked.status == "BLOCKED"
    assert blocked.reels == ()
    assert blocked.errors == ("long:LED_SEGMENT_EXCEEDS_REEL",)
    incomplete = pack_reels(
        (_cut("valid", 50),),
        reel_length_mm=None,
        cut_increment_mm=50,
        sale_mode=None,
        minimum_purchase_increment_mm=None,
    )
    assert incomplete.status == "INCOMPLETE"
    assert len(incomplete.errors) == 3
    length_based = pack_reels(
        (_cut("valid", 50),),
        reel_length_mm=15000,
        cut_increment_mm=50,
        sale_mode="LENGTH_BASED",
        minimum_purchase_increment_mm=50,
    )
    assert length_based.status == "INCOMPATIBLE"
    assert length_based.errors == ("LED_UNSUPPORTED_SALE_MODE",)


def test_manual_length_change_uses_same_product_step():
    assert _cut("before", 1201).cut_length_mm == 1250
    assert _cut("after", 1251).cut_length_mm == 1300


def test_power_is_counted_once_and_channel_limits_are_separate():
    mono = calculate_led_load(
        led_kind="MONO",
        cut_lengths_mm=(50,),
        voltage_v=24,
        total_power_w_per_m=12,
    )
    assert mono.total_power_w == Decimal("0.6")
    assert mono.channel_current_a == (Decimal("0.025"),)

    cct = calculate_led_load(
        led_kind="CCT",
        cut_lengths_mm=(Decimal("27.78"),),
        voltage_v=24,
        total_power_w_per_m="9.6",
        channel_power_w_per_m={"warm": "4.8", "cool": "4.8"},
    )
    assert cct.led_kind == "CCT"
    assert cct.total_power_w == Decimal("0.266688")
    assert cct.channel_power_w == (Decimal("0.133344"), Decimal("0.133344"))

    rgbw = calculate_led_load(
        led_kind="RGBW",
        cut_lengths_mm=(Decimal("33.33"),),
        voltage_v=24,
        total_power_w_per_m="17.2",
        channel_power_w_per_m={"rgb_combined": "13.3", "white": "4.2"},
    )
    assert rgbw.total_power_w == Decimal("0.573276")
    assert sum(rgbw.channel_power_w) == Decimal("0.583275")
    assert rgbw.trace[0]["rule"] == "automation.led_total_power_once"
