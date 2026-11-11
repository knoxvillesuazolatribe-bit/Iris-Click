"""Version-1 messages for desktop calibration (website <-> this server <-> window).

Every message is a JSON object ``{"v": 1, "type": "...", ...}``. A message with
another version is refused with ``calibration.error`` so an old page or window
never acts on a format it does not understand. The existing ``/ws/calibration``
messages are separate and unchanged.

Website -> server   calibration.start, calibration.cancel
Window  -> server   calibration.started, .progress, .advice, .result, .cancelled, .error
Server  -> website  calibration.state (on connect), the window's events, tracking.status,
                    calibration.error
Server  -> window   calibration.cancel
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

VERSION = 1


class _Message(BaseModel):
    v: Literal[1]


# ---- website -> server
class StartRequest(_Message):
    type: Literal["calibration.start"]


class CancelRequest(_Message):
    type: Literal["calibration.cancel"]


SiteMessage = Annotated[StartRequest | CancelRequest, Field(discriminator="type")]
site_message = TypeAdapter(SiteMessage)


# ---- window -> server
class Started(_Message):
    type: Literal["calibration.started"]
    total: int = Field(ge=1)


class Progress(_Message):
    type: Literal["calibration.progress"]
    done: int = Field(ge=0)
    total: int = Field(ge=1)


class Advice(_Message):
    type: Literal["calibration.advice"]
    kind: Literal["face", "eyes", "distance", "lighting"] | None
    text: str | None = None


class Result(_Message):
    type: Literal["calibration.result"]
    status: Literal["success", "failed"]
    accuracy_percent: float | None = None
    low_accuracy: bool = False
    message: str = ""


class Cancelled(_Message):
    type: Literal["calibration.cancelled"]
    reason: str = "cancelled"


class Error(_Message):
    type: Literal["calibration.error"]
    message: str


AgentMessage = Annotated[Started | Progress | Advice | Result | Cancelled | Error,
                         Field(discriminator="type")]
agent_message = TypeAdapter(AgentMessage)


def event(kind: str, **fields: Any) -> dict:
    """A server-sent message: ``event("calibration.progress", done=3, total=13)``."""
    return {"v": VERSION, "type": kind, **fields}


def version_of(raw: Any) -> Any:
    return raw.get("v") if isinstance(raw, dict) else None
