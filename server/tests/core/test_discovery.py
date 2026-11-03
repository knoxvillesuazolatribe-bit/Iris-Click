import numpy as np

from app.core.camera import discovery
from app.core.camera.discovery import LIVE_FRAMES_NEEDED, read_live_frames


def _frame(level: int) -> np.ndarray:
    return np.full((36, 64, 3), level, dtype=np.uint8)


class ScriptedCapture:
    def __init__(self, frames: list[np.ndarray]):
        self._frames = iter(frames)

    def read(self):
        frame = next(self._frames, None)
        return (frame is not None), frame


def test_skips_stale_and_blank_startup_frames_of_virtual_camera():
    stale = _frame(150)
    live = [_frame(100 + i) for i in range(LIVE_FRAMES_NEEDED)]
    cap = ScriptedCapture([_frame(1), stale, stale, stale, _frame(0), *live])

    frames, last = read_live_frames(cap)

    assert [int(f[0, 0, 0]) for f in frames] == [100 + i for i in range(LIVE_FRAMES_NEEDED)]
    assert last is live[-1]


def test_camera_that_stays_black_returns_last_frame_only(monkeypatch):
    monkeypatch.setattr(discovery, "WARMUP_TIMEOUT_S", 0.05)
    black = _frame(0)
    cap = ScriptedCapture([black] * 5)

    frames, last = read_live_frames(cap)

    assert frames == []
    assert last is black
