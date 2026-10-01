"""Automation, channel assignment, and LED calculation services."""

from .domain import (
    LED_LAYOUT,
    LedLoad,
    LedRuleError,
    ReelBin,
    ReelPacking,
    SegmentCut,
    assess_pwm_capacity,
    calculate_led_load,
    cut_segment,
    led_layout,
    normalize_led_kind,
    pack_reels,
)
from .service import (
    AutomationError,
    AutomationService,
    ChannelAssignmentResult,
    LedProfileResult,
)

__all__ = [
    "LED_LAYOUT",
    "LedLoad",
    "LedRuleError",
    "ReelBin",
    "ReelPacking",
    "SegmentCut",
    "AutomationError",
    "AutomationService",
    "ChannelAssignmentResult",
    "LedProfileResult",
    "assess_pwm_capacity",
    "calculate_led_load",
    "cut_segment",
    "led_layout",
    "normalize_led_kind",
    "pack_reels",
]
