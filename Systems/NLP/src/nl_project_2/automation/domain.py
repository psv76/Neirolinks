"""Pure LED cut, reel packing, and PWM-load calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any


class LedRuleError(ValueError):
    pass


LED_LAYOUT = {
    "MONO": (1, 2),
    "CCT": (2, 3),
    "RGB": (3, 4),
    "RGBW": (4, 5),
}


@dataclass(frozen=True, slots=True)
class SegmentCut:
    segment_id: str
    design_length_mm: Decimal
    cut_length_mm: Decimal | None
    status: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReelBin:
    index: int
    segment_ids: tuple[str, ...]
    used_length_mm: Decimal
    remainder_mm: Decimal
    unusable_remainder_mm: Decimal


@dataclass(frozen=True, slots=True)
class ReelPacking:
    status: str
    reels: tuple[ReelBin, ...]
    required_quantity_mm: Decimal
    purchased_reels: int
    purchased_length_mm: Decimal
    remainder_mm: Decimal
    unusable_remainder_mm: Decimal
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LedLoad:
    status: str
    led_kind: str
    channels: int
    conductors: int
    cut_length_mm: Decimal
    total_power_w: Decimal
    channel_power_w: tuple[Decimal, ...]
    channel_current_a: tuple[Decimal, ...]
    trace: tuple[dict[str, Any], ...]


def normalize_led_kind(value: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in LED_LAYOUT:
        raise LedRuleError(f"Unsupported canonical LED kind: {value}")
    return normalized


def led_layout(value: str) -> tuple[int, int]:
    return LED_LAYOUT[normalize_led_kind(value)]


def cut_segment(
    segment_id: str,
    design_length_mm,
    cut_increment_mm,
    reel_length_mm,
) -> SegmentCut:
    design = _positive_decimal(design_length_mm)
    increment = _positive_decimal(cut_increment_mm)
    reel = _positive_decimal(reel_length_mm)
    if design is None:
        return SegmentCut(
            segment_id,
            _decimal(design_length_mm) or Decimal("0"),
            None,
            "INVALID",
            "LED_INVALID_DESIGN_LENGTH",
        )
    if increment is None:
        return SegmentCut(
            segment_id,
            design,
            None,
            "INCOMPLETE",
            "LED_CUT_INCREMENT_MISSING_OR_INVALID",
        )
    if reel is None:
        return SegmentCut(
            segment_id,
            design,
            None,
            "INCOMPLETE",
            "LED_REEL_LENGTH_MISSING_OR_INVALID",
        )
    steps = (design / increment).to_integral_value(rounding=ROUND_CEILING)
    cut = steps * increment
    if cut > reel:
        return SegmentCut(
            segment_id,
            design,
            cut,
            "BLOCKED",
            "LED_SEGMENT_EXCEEDS_REEL",
        )
    return SegmentCut(segment_id, design, cut, "VALID")


def pack_reels(
    segments: tuple[SegmentCut, ...],
    *,
    reel_length_mm,
    cut_increment_mm,
    sale_mode: str | None,
    minimum_purchase_increment_mm,
) -> ReelPacking:
    reel_length = _positive_decimal(reel_length_mm)
    cut_increment = _positive_decimal(cut_increment_mm)
    minimum_purchase = _positive_decimal(minimum_purchase_increment_mm)
    missing = []
    if reel_length is None:
        missing.append("REEL_LENGTH")
    if cut_increment is None:
        missing.append("CUT_INCREMENT")
    if not sale_mode:
        missing.append("SALE_MODE")
    if minimum_purchase is None:
        missing.append("MIN_PURCHASE_INCREMENT")
    if missing:
        return ReelPacking(
            "INCOMPLETE",
            (),
            Decimal("0"),
            0,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            tuple(f"LED_PRODUCT_DATA_MISSING:{field}" for field in missing),
        )
    if str(sale_mode).upper() != "FULL_REEL":
        return ReelPacking(
            "INCOMPATIBLE",
            (),
            Decimal("0"),
            0,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            ("LED_UNSUPPORTED_SALE_MODE",),
        )
    assert reel_length is not None and cut_increment is not None
    if minimum_purchase != reel_length:
        return ReelPacking(
            "INCOMPATIBLE",
            (),
            Decimal("0"),
            0,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            ("LED_FULL_REEL_PURCHASE_INCREMENT_MISMATCH",),
        )
    invalid = tuple(
        f"{segment.segment_id}:{segment.error}"
        for segment in segments
        if segment.status != "VALID" or segment.cut_length_mm is None
    )
    if invalid:
        return ReelPacking(
            "BLOCKED",
            (),
            Decimal("0"),
            0,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            invalid,
        )
    ordered = sorted(
        segments,
        key=lambda item: (-item.cut_length_mm, item.segment_id),
    )
    bins: list[dict[str, Any]] = []
    for segment in ordered:
        assert segment.cut_length_mm is not None
        for reel in bins:
            if reel["used"] + segment.cut_length_mm <= reel_length:
                reel["segments"].append(segment.segment_id)
                reel["used"] += segment.cut_length_mm
                break
        else:
            bins.append({"segments": [segment.segment_id], "used": segment.cut_length_mm})
    result_bins = []
    for index, item in enumerate(bins, start=1):
        remainder = reel_length - item["used"]
        result_bins.append(
            ReelBin(
                index,
                tuple(item["segments"]),
                item["used"],
                remainder,
                remainder % cut_increment,
            )
        )
    required = sum(
        (segment.cut_length_mm for segment in ordered),
        Decimal("0"),
    )
    purchased = len(result_bins) * reel_length
    return ReelPacking(
        "VERIFIED",
        tuple(result_bins),
        required,
        len(result_bins),
        purchased,
        purchased - required,
        sum(
            (item.unusable_remainder_mm for item in result_bins),
            Decimal("0"),
        ),
    )


def calculate_led_load(
    *,
    led_kind: str,
    cut_lengths_mm: tuple[Any, ...],
    voltage_v,
    total_power_w_per_m,
    channel_power_w_per_m=None,
) -> LedLoad:
    normalized = normalize_led_kind(led_kind)
    channels, conductors = led_layout(normalized)
    voltage = _positive_decimal(voltage_v)
    total_per_m = _positive_decimal(total_power_w_per_m)
    lengths = tuple(_positive_decimal(value) for value in cut_lengths_mm)
    if voltage is None or total_per_m is None or any(value is None for value in lengths):
        raise LedRuleError("LED load requires positive voltage, power and cut lengths")
    total_length = sum((value for value in lengths if value is not None), Decimal("0"))
    metres = total_length / Decimal("1000")
    per_channel = _channel_power_per_m(normalized, total_per_m, channel_power_w_per_m)
    channel_power = tuple(value * metres for value in per_channel)
    channel_current = tuple(value / voltage for value in channel_power)
    total_power = total_per_m * metres
    return LedLoad(
        "VERIFIED",
        normalized,
        channels,
        conductors,
        total_length,
        total_power,
        channel_power,
        channel_current,
        (
            {
                "rule": "automation.led_total_power_once",
                "actual": str(total_power),
                "basis": {
                    "cut_length_mm": str(total_length),
                    "total_power_w_per_m": str(total_per_m),
                },
            },
            {
                "rule": "automation.led_channel_currents",
                "actual": [str(value) for value in channel_current],
                "voltage_v": str(voltage),
            },
        ),
    )


def assess_pwm_capacity(
    load: LedLoad,
    *,
    selected_channel_count: int,
    maximum_current_a_per_channel,
    maximum_combined_current_a,
) -> tuple[str, tuple[dict[str, Any], ...]]:
    per_channel_limit = _positive_decimal(maximum_current_a_per_channel)
    combined_limit = _positive_decimal(maximum_combined_current_a)
    trace = []
    if selected_channel_count != load.channels:
        trace.append(
            {
                "rule": "automation.led_channel_count",
                "result": "INCOMPATIBLE",
                "actual": selected_channel_count,
                "required": load.channels,
            }
        )
        return "INCOMPATIBLE", tuple(trace)
    if per_channel_limit is None or combined_limit is None:
        return (
            "DATA_INCOMPLETE",
            (
                {
                    "rule": "automation.pwm_limits",
                    "result": "DATA_INCOMPLETE",
                    "actual": {
                        "per_channel": _text(per_channel_limit),
                        "combined": _text(combined_limit),
                    },
                },
            ),
        )
    over_channels = [
        index for index, current in enumerate(load.channel_current_a) if current > per_channel_limit
    ]
    combined = sum(load.channel_current_a, Decimal("0"))
    exceeded = bool(over_channels) or combined > combined_limit
    trace.append(
        {
            "rule": "automation.pwm_current_capacity",
            "result": "LIMIT_EXCEEDED" if exceeded else "PASS",
            "actual": {
                "channel_current_a": [str(value) for value in load.channel_current_a],
                "combined_current_a": str(combined),
                "over_limit_channels": over_channels,
            },
            "required": {
                "maximum_current_a_per_channel": str(per_channel_limit),
                "maximum_combined_current_a": str(combined_limit),
            },
        }
    )
    return ("LIMIT_EXCEEDED" if exceeded else "VERIFIED"), tuple(trace)


def _channel_power_per_m(kind, total, provided) -> tuple[Decimal, ...]:
    channels = LED_LAYOUT[kind][0]
    if not isinstance(provided, dict):
        return tuple(total / channels for _ in range(channels))
    values = {str(key).lower(): _decimal(value) for key, value in provided.items()}
    if kind == "CCT" and values.get("warm") is not None and values.get("cool") is not None:
        return values["warm"], values["cool"]
    if kind == "RGBW":
        if all(values.get(key) is not None for key in ("r", "g", "b", "w")):
            return values["r"], values["g"], values["b"], values["w"]
        if values.get("rgb_combined") is not None and values.get("white") is not None:
            rgb = values["rgb_combined"] / Decimal("3")
            return rgb, rgb, rgb, values["white"]
    return tuple(total / channels for _ in range(channels))


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _positive_decimal(value) -> Decimal | None:
    result = _decimal(value)
    return result if result is not None and result > 0 else None


def _text(value) -> str | None:
    return None if value is None else str(value)
