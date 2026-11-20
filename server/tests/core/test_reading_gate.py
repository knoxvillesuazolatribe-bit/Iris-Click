"""The frame gate in front of the gaze mapping: closed eyes, missing faces, broken landmarks,
stale or repeated frames never reach the cursor."""

import math
from types import SimpleNamespace

import pytest

from app.core.gaze.pipeline import POST_BLINK_SETTLE_S, ReadingGate

GOOD = (0.5, 0.5, 0.0, 0.0, 0.0, 0.0)


def frame(t, left=0.3, right=0.3, face=True, features=GOOD):
    return SimpleNamespace(captured_at=t, face_found=face, features=features,
                           left_ear=left, right_ear=right)


def test_a_clear_frame_passes():
    gate = ReadingGate()
    assert gate.accept(frame(10.0), now=10.01) and gate.reason is None


@pytest.mark.parametrize(("reading", "reason"), [
    (frame(10.0, face=False), "no_face"),
    (frame(10.0, features=(0.5, 0.5)), "invalid_features"),
    (frame(10.0, features=(0.5, math.nan, 0, 0, 0, 0)), "invalid_features"),
    (frame(10.0, left=math.nan), "invalid_eyes"),
    (frame(10.0, left=0.05, right=0.05), "eyes_closed"),
    (frame(10.0, left=0.05, right=0.3), "eyes_closed"),  # a wink or squint: no gaze sample
])
def test_unusable_frames_are_rejected(reading, reason):
    gate = ReadingGate()
    assert not gate.accept(reading, now=10.01)
    assert gate.reason == reason


def test_old_frames_are_stale():
    gate = ReadingGate(max_age=0.25)
    assert not gate.accept(frame(10.0), now=10.5) and gate.reason == "stale"


def test_a_frame_is_used_once():
    gate = ReadingGate()
    assert gate.accept(frame(10.0), now=10.01)
    assert not gate.accept(frame(10.0), now=10.02) and gate.reason == "duplicate"


@pytest.mark.parametrize("stamp", [0.0, -1.0, math.nan, 11.0])
def test_impossible_timestamps_are_rejected(stamp):
    gate = ReadingGate()
    assert not gate.accept(frame(stamp), now=10.0) and gate.reason == "invalid_timestamp"


def test_the_eyes_settle_after_a_blink_before_frames_count_again():
    gate = ReadingGate()
    assert not gate.accept(frame(10.0, left=0.05, right=0.05), now=10.01)
    assert not gate.accept(frame(10.0 + POST_BLINK_SETTLE_S / 2), now=10.06)
    assert gate.reason == "recovering"
    assert gate.accept(frame(10.0 + POST_BLINK_SETTLE_S + 0.01), now=10.12)


def test_reset_forgets_the_last_frame():
    gate = ReadingGate()
    gate.accept(frame(10.0), now=10.01)
    gate.reset()
    assert gate.accept(frame(10.0), now=10.01)
