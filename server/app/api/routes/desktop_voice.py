"""Voice commands on IrisClick Desktop (127.0.0.1): what "Go to ..." may open, and valid-data checks.

    PUT  /api/desktop/voice-shortcuts   the website hands over the person's website tiles
    GET  /api/desktop/voice-shortcuts   every name "Go to ..." accepts right now
    POST /api/desktop/voice-check       classify a phrase: valid command / dictation / invalid

Only IrisClick's own websites reach these routes (app/api/origin_guard.py). Each
address is checked again (http/https, a real domain, no spaces or hidden user name);
invalid ones are counted and dropped, never stored or opened. No speech is sent here:
recognition happens inside the tracking worker, on this PC.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.voice import commands, shortcuts

router = APIRouter(tags=["desktop voice"])


class ShortcutIn(BaseModel):
    label: str = Field(max_length=80)
    url: str = Field(max_length=2048)


class ShortcutsIn(BaseModel):
    shortcuts: list[ShortcutIn] = Field(default_factory=list, max_length=shortcuts.MAX_SHORTCUTS)


class CheckIn(BaseModel):
    text: str = Field(max_length=600)
    typing: bool = False


@router.put("/desktop/voice-shortcuts")
def save_shortcuts(body: ShortcutsIn) -> dict:
    kept, rejected = shortcuts.save([s.model_dump() for s in body.shortcuts])
    return {"saved": kept, "rejected": rejected}


@router.get("/desktop/voice-shortcuts")
def list_shortcuts() -> dict:
    found = shortcuts.directory()
    names = sorted({f"{t.label}|{t.kind}" for t in found.values()})
    return {"names": sorted(found), "targets": [{"label": n.split("|")[0], "kind": n.split("|")[1]} for n in names]}


@router.post("/desktop/voice-check")
def check(body: CheckIn) -> dict:
    """The same classifier the microphone uses, for typed tests and the panel demo."""
    result = commands.classify(body.text, 1.0, body.typing, frozenset(shortcuts.directory()))
    return {"valid": result.valid, "kind": result.kind, "action": result.action,
            "name": result.name, "text": result.text, "message": result.reason}
