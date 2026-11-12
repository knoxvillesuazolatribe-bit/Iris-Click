"""Desktop calibration routes on IrisClick Desktop's local server (127.0.0.1).

    GET  /api/desktop/calibration              which calibration screen this PC uses + run state
    POST /api/desktop/calibration/open         open the calibration window (launcher, tracking
                                               worker, tray); refused for any web page
    WS   /api/ws/desktop-calibration           the website: start / cancel, live progress
    WS   /api/ws/desktop-calibration/agent     the calibration window only; refused for any web page

The website channel is protected like every other route here: only allowed websites
pass the Origin guard (app/api/origin_guard.py), and ``calibration.start`` also needs a
person linked on this computer. Browsers always send an Origin header, so refusing one
on the agent channel and on ``open`` keeps every web page out of them.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.desktop_calibration import surface as surface_setting
from app.desktop_calibration.messages import VERSION, agent_message, event, site_message, version_of
from app.desktop_calibration.relay import relay
from app.services import active_user
from app.accounts import pending_calibration  # extension: accounts on this computer

logger = logging.getLogger("irisclick.desktop_calibration")

NOT_LINKED = "Choose your name on the IrisClick website first."
WRONG_VERSION = "This IrisClick page is out of date. Reload the page."
TRACKING_EVERY_S = 1.0

router = APIRouter(tags=["desktop calibration"])


class OpenRequest(BaseModel):
    reason: str = "tray"
    # First start of IrisClick Desktop: only in desktop mode, and only with someone linked.
    first_run: bool = False


def _port(url_port: int | None) -> int:
    from app.config import get_settings
    return url_port or get_settings().port


def tracking_status() -> str:
    from app.config import get_settings
    from app.services.tracking_service import get_tracking_service
    from app.workers.worker_state import read_state, state_path
    status = get_tracking_service().status()
    if not status.running:
        return "stopped"
    live = read_state(state_path(get_settings()), status.pid) if status.pid else None
    return "paused" if live and live.get("paused") else "active"


@router.get("/desktop/calibration")
def calibration_info() -> dict:
    return {"v": VERSION, "surface": surface_setting.surface(), "state": relay.snapshot(),
            "linked": active_user.get_user_id() is not None}


@router.post("/desktop/calibration/open")
async def open_window(request: Request, body: OpenRequest | None = None) -> dict:
    if request.headers.get("origin"):
        raise HTTPException(status_code=403, detail="Only IrisClick Desktop may open this window.")
    body = body or OpenRequest()
    if body.first_run:
        if surface_setting.surface() != surface_setting.DESKTOP:
            return {"opened": False, "reason": "web_mode"}
        if active_user.get_user_id() is None:
            return {"opened": False, "reason": "not_linked"}
    return await relay.open(_port(request.url.port), body.reason[:20])


@router.websocket("/ws/desktop-calibration")
async def site_socket(websocket: WebSocket):
    await websocket.accept()
    relay.add_site(websocket)
    pusher = asyncio.create_task(_push_tracking(websocket))
    try:
        await relay.send(websocket, relay.snapshot())
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except ValueError:
                await relay.send(websocket, event("calibration.error", message="Invalid message."))
                continue
            if version_of(data) != VERSION:
                await relay.send(websocket, event("calibration.error", message=WRONG_VERSION,
                                                reason="version"))
                continue
            try:
                message = site_message.validate_python(data)
            except ValidationError:
                await relay.send(websocket, event("calibration.error", message="Invalid message."))
                continue
            if message.type == "calibration.start":
                if active_user.get_user_id() is None and not pending_calibration.new_account_allowed():
                    await relay.send(websocket, event("calibration.error", message=NOT_LINKED,
                                                    reason="not_linked"))
                    continue
                result = await relay.open(_port(websocket.url.port), "website")
                if not result["opened"] and result["reason"] != "already_open":
                    await relay.send(websocket, event("calibration.error",
                                                    message="The calibration window could not open.",
                                                    reason=result["reason"]))
            else:
                await relay.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        pusher.cancel()
        relay.remove_site(websocket)


async def _push_tracking(websocket: WebSocket) -> None:
    last = None
    try:
        while True:
            try:
                current = await run_in_threadpool(tracking_status)
            except Exception:  # noqa: BLE001
                current = None
            if current is not None and current != last:
                await relay.send(websocket, event("tracking.status", status=current))
                last = current
            await asyncio.sleep(TRACKING_EVERY_S)
    except (asyncio.CancelledError, RuntimeError, WebSocketDisconnect):
        return
    except Exception:  # noqa: BLE001
        return


@router.websocket("/ws/desktop-calibration/agent")
async def agent_socket(websocket: WebSocket):
    if websocket.headers.get("origin"):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    if not await relay.agent_connected(websocket):
        await websocket.close(code=1013)
        return
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if version_of(data) != VERSION:
                continue
            try:
                message = agent_message.validate_python(data)
            except ValidationError:
                continue
            await relay.agent_event(message.model_dump())
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        await relay.agent_disconnected(websocket)
