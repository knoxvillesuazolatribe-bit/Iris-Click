import cv2
import pytest

from app.core.camera import capture


class FakeCapture:
    def __init__(self, *args):
        self.props = {}

    def isOpened(self):
        return True

    def set(self, prop, value):
        self.props[prop] = value

    def release(self):
        pass


@pytest.fixture
def fake_capture(monkeypatch):
    monkeypatch.setattr(capture.cv2, "VideoCapture", FakeCapture)


@pytest.mark.parametrize("resolution, size", [("720p", (1280, 720)), ("1080p", (1920, 1080))])
def test_open_camera_requests_resolution(fake_capture, resolution, size):
    cap = capture.open_camera(0, resolution=resolution)
    assert (cap.props[cv2.CAP_PROP_FRAME_WIDTH], cap.props[cv2.CAP_PROP_FRAME_HEIGHT]) == size


def test_open_camera_rejects_unknown_resolution(fake_capture):
    with pytest.raises(RuntimeError, match="resolution"):
        capture.open_camera(0, resolution="4k")
