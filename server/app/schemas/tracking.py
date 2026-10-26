from datetime import datetime

from pydantic import BaseModel


class WorkerStatusRead(BaseModel):
    running: bool
    pid: int | None = None
    profile_id: str | None = None
    started_at: datetime | None = None
    message: str | None = None


class WorkerStartRequest(BaseModel):
    profile_id: str | None = None
