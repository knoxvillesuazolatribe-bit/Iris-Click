from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class GestureRead(BaseModel):
    gesture: str
    action: str


class HomeRead(BaseModel):
    full_name: str
    gestures: list[GestureRead]


class CalibrationSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: str
    profile_name: str
    calibrated_at: datetime | None
    accuracy_score: Decimal | None


class GazePointRead(BaseModel):
    x: int
    y: int
    screen_w: int
    screen_h: int


class WinkCountRead(BaseModel):
    left: int
    right: int


class LiveTrackingRead(BaseModel):
    status: str
    kind: str
    paused: bool
    gaze: GazePointRead | None
    winks: WinkCountRead


class TrackingViewRead(BaseModel):
    state: Literal["active", "paused", "inactive"]
    status_text: str | None
    running_profile_is_mine: bool | None
    started_at: datetime | None
    calibration: CalibrationSummaryRead | None
    calibration_unavailable_reason: str | None
    live: LiveTrackingRead | None
