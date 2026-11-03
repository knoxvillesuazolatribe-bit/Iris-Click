from typing import Literal

from pydantic import BaseModel, Field


class CameraRead(BaseModel):
    index: int
    available: bool
    in_use: bool = False
    width: int = 0
    height: int = 0
    brightness: float = 0.0
    face_found: bool = False
    has_snapshot: bool = False
    selected: bool = False


class DeviceSettings(BaseModel):
    """Per-computer choices, stored in storage/device_settings.json (camera indices are local)."""

    camera_index: int = Field(default=0, ge=0)
    # None: use Settings.edge_sensitivity.
    edge_sensitivity: Literal["off", "low", "medium", "high"] | None = None
