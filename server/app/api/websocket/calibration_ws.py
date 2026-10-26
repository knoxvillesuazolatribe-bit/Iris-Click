import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.api.websocket.connection_manager import ConnectionManager
from app.config import get_settings
from app.schemas.calibration import (
    CalibrationCancelMessage,
    CalibrationClientMessage,
    CalibrationCollectMessage,
    CalibrationErrorMessage,
    CalibrationStartMessage,
)
from app.services.calibration_service import CalibrationError, CalibrationSession
from app.services.camera_service import get_camera_service
from app.services.tracking_service import get_tracking_service

logger = logging.getLogger("irisclick.calibration_ws")

router = APIRouter()
_client_message = TypeAdapter(CalibrationClientMessage)


@router.websocket("/ws/calibration")
async def calibration_socket(websocket: WebSocket):
    await websocket.accept()
    manager: ConnectionManager = websocket.app.state.calibration_connections
    if not await manager.acquire(websocket):
        await websocket.send_text(CalibrationErrorMessage(
            message="Another calibration is already running.", fatal=True).model_dump_json())
        await websocket.close(code=1013)
        return

    async def send(message):
        await manager.send(websocket, message)

    session = CalibrationSession(get_settings(), get_tracking_service(), get_camera_service(), send)
    try:
        while not session.finished:
            try:
                message = _client_message.validate_python(json.loads(await websocket.receive_text()))
            except (ValueError, ValidationError) as exc:
                await send(CalibrationErrorMessage(message=f"Invalid message: {exc}"))
                continue
            if isinstance(message, CalibrationStartMessage):
                await session.start(message)
            elif isinstance(message, CalibrationCollectMessage):
                await session.collect(message.index)
            elif isinstance(message, CalibrationCancelMessage):
                break
    except WebSocketDisconnect:
        logger.info("Calibration page disconnected")
    except CalibrationError as exc:
        await send(CalibrationErrorMessage(message=str(exc), fatal=True))
    finally:
        await session.close()
        manager.release(websocket)
        if not session.finished:
            logger.info("Calibration ended before completion")
