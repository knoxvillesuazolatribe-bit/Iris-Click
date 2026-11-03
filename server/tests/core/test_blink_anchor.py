from app.core.gaze.blink_anchor import BlinkAnchor

OPEN = 0.30


def _record(anchor, t, x, y, left, right=None):
    anchor.record(t, x, y, left, left if right is None else right)


def test_anchor_is_last_point_before_the_lid_started_dropping():
    anchor = BlinkAnchor()
    for i in range(20):
        _record(anchor, i * 0.033, 1890.0, 20.0, OPEN)
    # The lid starts dropping and drags the cursor down before "closed".
    _record(anchor, 0.70, 1885.0, 60.0, 0.24)
    _record(anchor, 0.73, 1880.0, 95.0, 0.20)
    assert anchor.anchor() == (1890.0, 20.0)


def test_a_closing_wink_eye_is_not_an_anchor():
    anchor = BlinkAnchor()
    for i in range(20):
        _record(anchor, i * 0.033, 500.0, 500.0, OPEN)
    _record(anchor, 0.70, 505.0, 530.0, 0.20, OPEN)
    assert anchor.anchor() == (500.0, 500.0)


def test_no_history_gives_no_anchor():
    assert BlinkAnchor().anchor() is None


def test_old_history_is_forgotten():
    anchor = BlinkAnchor()
    _record(anchor, 0.0, 100.0, 100.0, OPEN)
    _record(anchor, 5.0, 500.0, 500.0, OPEN)
    assert anchor.anchor() == (500.0, 500.0)
    assert len(anchor._history) == 1


def test_baseline_adapts_to_a_user_with_narrow_eyes():
    anchor = BlinkAnchor()
    for i in range(200):
        _record(anchor, i * 0.033, 300.0, 300.0, 0.22)
    _record(anchor, 7.0, 310.0, 340.0, 0.17)
    assert anchor.anchor() == (300.0, 300.0)


def test_looking_down_at_the_taskbar_still_anchors_there():
    anchor = BlinkAnchor()
    for i in range(30):
        _record(anchor, i * 0.033, 900.0, 100.0, OPEN)
    # Both lids narrow while the gaze stays low (s4: ~0.13 on the bottom row).
    for i in range(30):
        _record(anchor, 1.0 + i * 0.033, 900.0, 1040.0, 0.13)
    assert anchor.anchor() == (900.0, 1040.0)
