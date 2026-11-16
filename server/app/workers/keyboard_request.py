"""Adviser: the "On-Screen Keyboard" app tile asks the tracking worker to show or hide its keyboard.

The keyboard (app/workers/virtual_keyboard.py) lives in the tracking worker, a separate process.
The server leaves a small request file beside the worker's pid file; the worker takes it on its
next frame (_handle_commands) and does what the control bar's Keyboard button does.
"""

from pathlib import Path

from app.services.apps_service import AppError

FILE_NAME = "keyboard_request"
NOT_RUNNING = "Start eye tracking to use the On-Screen Keyboard."


def request_path(settings) -> Path:
    return Path(settings.worker_pid_path).with_name(FILE_NAME)


def _tracking_running() -> bool:
    from app.services.tracking_service import get_tracking_service
    return get_tracking_service().status().running


def ask(settings=None, running=None) -> None:
    """Asks the running worker to toggle the keyboard. Raises AppError when tracking is off."""
    if settings is None:
        from app.config import get_settings
        settings = get_settings()
    if not (running if running is not None else _tracking_running()):
        raise AppError(409, NOT_RUNNING)
    request_path(settings).write_text("toggle", encoding="utf-8")


def take(settings) -> bool:
    """True once per request: the worker toggles the keyboard."""
    path = request_path(settings)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
