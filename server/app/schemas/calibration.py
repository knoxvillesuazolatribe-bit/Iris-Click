from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Point2 = tuple[float, float]


class ScreenSize(BaseModel):
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)


class CandidateScore(BaseModel):
    feature_source: str
    error_fraction: float


class CalibrationProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_name: str
    created_at: datetime
    feature_source: str
    accuracy_fraction: float
    low_accuracy: bool
    sample_count: int
    screen: ScreenSize | None = None
    # A calibration only fits the camera (and position) it was made with.
    camera_index: int | None = None
    deep_gaze_available: bool
    candidates: list[CandidateScore]


class CalibrationProfileFile(CalibrationProfileRead):
    # Fitted CalibrationModel.to_dict(); never sent to the site.
    model: dict[str, Any]


class CalibrationStartMessage(BaseModel):
    type: Literal["start"]
    profile_name: str = Field(min_length=1, max_length=60)
    screen: ScreenSize
    # None: use the camera last chosen on this computer.
    camera_index: int | None = Field(default=None, ge=0)


class CalibrationCollectMessage(BaseModel):
    type: Literal["collect"]
    index: int = Field(ge=0)


class CalibrationCancelMessage(BaseModel):
    type: Literal["cancel"]


CalibrationClientMessage = Annotated[
    CalibrationStartMessage | CalibrationCollectMessage | CalibrationCancelMessage,
    Field(discriminator="type"),
]


class CalibrationPoint(BaseModel):
    x: float
    y: float


class SessionReadyMessage(BaseModel):
    type: Literal["ready"] = "ready"
    points: list[CalibrationPoint]
    deep_gaze_available: bool
    max_point_retries: int


class EyeLine(BaseModel):
    pointer: Point2
    line_centre: Point2
    left_eye: Point2
    right_eye: Point2
    left_iris: Point2
    right_iris: Point2
    eye_distance: float
    nose_bridge: Point2 | None = None
    nose_tip: Point2 | None = None


class FrameStatusMessage(BaseModel):
    type: Literal["frame_status"] = "frame_status"
    face_found: bool
    eyes_open: bool
    registered: bool
    eye_line: EyeLine | None = None
    distance_advice: Literal["closer", "back"] | None = None
    guidance: str | None = None
    pupils_detected: bool
    deep_active: bool


class PointResultMessage(BaseModel):
    type: Literal["point_result"] = "point_result"
    index: int
    status: Literal["accepted", "retry", "failed"]
    sample_count: int
    message: str | None = None


class CalibrationResultMessage(BaseModel):
    type: Literal["result"] = "result"
    status: Literal["success", "failed"]
    message: str
    profile: CalibrationProfileRead | None = None
    worker_started: bool = False


class CalibrationErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
    fatal: bool = False
