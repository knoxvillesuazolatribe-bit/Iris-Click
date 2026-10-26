from app.core.gaze.blink_anchor import BlinkAnchor

OPEN = 0.30


def test_anchor_is_last_point_before_the_lid_started_dropping():
    anchor = BlinkAnchor()
    for i in range(20):
        anchor.record(i * 0.033, 1890.0, 20.0, OPEN)
    # The lid starts dropping and drags the cursor down before "closed".
    anchor.record(0.70, 1885.0, 60.0, 0.24)
    anchor.record(0.73, 1880.0, 95.0, 0.20)
    assert anchor.anchor() == (1890.0, 20.0)


def test_no_history_gives_no_anchor():
    assert BlinkAnchor().anchor() is None


def test_old_history_is_forgotten():
    anchor = BlinkAnchor()
    anchor.record(0.0, 100.0, 100.0, OPEN)
    anchor.record(5.0, 500.0, 500.0, OPEN)
    assert anchor.anchor() == (500.0, 500.0)
    assert len(anchor._history) == 1


def test_baseline_adapts_to_a_user_with_narrow_eyes():
    anchor = BlinkAnchor()
    for i in range(200):
        anchor.record(i * 0.033, 300.0, 300.0, 0.22)
    anchor.record(7.0, 310.0, 340.0, 0.17)
    assert anchor.anchor() == (300.0, 300.0)
