from typing import Literal

from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str
    app_name: str


class DatabaseHealthRead(BaseModel):
    status: Literal["ok", "unreachable"]
    backend: Literal["postgresql", "sqlite"]
    host: str | None = None
    detail: str | None = None
