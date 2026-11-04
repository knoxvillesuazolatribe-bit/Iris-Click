from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.accessibility_settings import DWELL_MS_RANGE, VOICE_VOLUME_RANGE


class AccessibilitySettingsWrite(BaseModel):
    dwell_enabled: bool
    dwell_ms: int = Field(ge=DWELL_MS_RANGE[0], le=DWELL_MS_RANGE[1])
    smoothing: Literal["low", "medium", "high"]
    blink_to_click: bool
    blink_sensitivity: int = Field(ge=1, le=5)
    edge_scroll_enabled: bool
    voice_volume: int = Field(ge=VOICE_VOLUME_RANGE[0], le=VOICE_VOLUME_RANGE[1])


class AccessibilitySettingsRead(AccessibilitySettingsWrite):
    model_config = ConfigDict(from_attributes=True)

    is_default: bool
    defaults: AccessibilitySettingsWrite
