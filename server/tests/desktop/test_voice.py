import pytest

from app.desktop.voice import VoiceGuide


class RecordingSpeaker:
    def __init__(self):
        self.lines = []

    def say(self, text):
        self.lines.append(text)


@pytest.fixture
def guide():
    return VoiceGuide(RecordingSpeaker(), persist_s=1.5, repeat_s=25.0, gap_s=6.0)


def _hold(guide, key, start, end, step=0.1):
    t = start
    while t <= end:
        guide.observe(key, f"say {key}", t)
        t += step


def test_problem_is_spoken_only_after_it_persists(guide):
    _hold(guide, "closer", 0.0, 1.4)
    assert guide.speaker.lines == []

    _hold(guide, "closer", 1.5, 1.7)
    assert guide.speaker.lines == ["say closer"]


def test_short_dropout_like_a_blink_stays_silent(guide):
    _hold(guide, "no_face", 0.0, 1.0)
    guide.observe(None, None, 1.1)
    _hold(guide, "no_face", 1.2, 2.0)
    assert guide.speaker.lines == []


def test_same_line_is_not_repeated_too_soon(guide):
    _hold(guide, "closer", 0.0, 20.0)
    assert guide.speaker.lines == ["say closer"]

    _hold(guide, "closer", 20.1, 30.0)
    assert guide.speaker.lines == ["say closer", "say closer"]


def test_lines_are_spaced_apart(guide):
    _hold(guide, "closer", 0.0, 2.0)
    _hold(guide, "no_face", 2.1, 7.0)
    assert guide.speaker.lines == ["say closer"]

    _hold(guide, "no_face", 7.1, 8.5)
    assert guide.speaker.lines == ["say closer", "say no_face"]


def test_disabled_guide_is_silent(guide):
    guide.enabled = False
    _hold(guide, "closer", 0.0, 5.0)
    guide.announce("Tracking paused.", 6.0)
    assert guide.speaker.lines == []
