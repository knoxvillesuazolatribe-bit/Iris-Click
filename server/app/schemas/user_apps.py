from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tile_id: int
    label: str
    kind: str
    icon: str
    note: str | None = None
    available: bool
    problem: str | None = None


class HiddenDefaultRead(BaseModel):
    tile_id: int
    label: str
    icon: str


class SuggestionRead(BaseModel):
    label: str
    url: str
    icon: str


class TilesRead(BaseModel):
    tiles: list[TileRead]
    hidden_defaults: list[HiddenDefaultRead]
    max_tiles: int
    suggestions: list[SuggestionRead]


class TileAdd(BaseModel):
    """One of: a hidden default (builtin_key), a Start Menu app (path), a website (label + url)."""

    kind: Literal["builtin", "installed_app", "website"]
    builtin_key: str | None = Field(None, max_length=20)
    path: str | None = Field(None, max_length=1024)
    label: str | None = Field(None, max_length=200)
    url: str | None = Field(None, max_length=4096)


class TileUpdate(BaseModel):
    position: int | None = Field(None, ge=0, le=100)
    is_visible: bool | None = None


class InstalledAppRead(BaseModel):
    name: str
    path: str


class LaunchRead(BaseModel):
    launched: bool
    label: str
