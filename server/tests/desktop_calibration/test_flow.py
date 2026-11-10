from app.desktop_calibration import flow as F

POINTS = [{"x": 0.5, "y": 0.5}, {"x": 0.04, "y": 0.04}, {"x": 0.96, "y": 0.96}]
STEADY = {"type": "frame_status", "face_found": True, "eyes_open": True, "registered": True,
          "distance_advice": None, "guidance": None}
NO_FACE = {"type": "frame_status", "face_found": False, "eyes_open": False, "registered": False,
           "guidance": "We cannot see your face. Face the camera."}


def ready_flow(now=0.0, **kw):
    f = F.CalibrationFlow("Desktop test", (1920, 1080), now, **kw)
    f.connected(now)
    assert f.take_outgoing() == [{"type": "start", "profile_name": "Desktop test",
                                  "screen": {"width": 1920, "height": 1080}}]
    f.on_message({"type": "ready", "points": POINTS}, now)
    return f


def run(f, start, end, step=0.05):
    t = start
    while t <= end:
        f.tick(t)
        t = round(t + step, 4)
    return t


def test_ready_reports_started_and_speaks_intro():
    f = ready_flow()
    assert f.phase == F.CHECKING
    assert f.take_events() == [{"v": 1, "type": "calibration.started", "total": 3}]
    assert F.SAY_INTRO in f.take_speech()


def test_countdown_waits_for_two_steady_seconds():
    f = ready_flow()
    f.on_message(STEADY, 0.0)
    run(f, 0.0, 1.9)
    assert f.phase == F.CHECKING
    run(f, 1.95, 2.1)
    assert f.phase == F.COUNTDOWN


def test_losing_the_face_restarts_the_steady_timer():
    f = ready_flow()
    f.on_message(STEADY, 0.0)
    run(f, 0.0, 1.5)
    f.on_message(NO_FACE, 1.5)
    run(f, 1.5, 3.0)
    assert f.phase == F.CHECKING
    f.on_message(STEADY, 3.0)
    run(f, 3.0, 5.1)
    assert f.phase == F.COUNTDOWN


def test_nobody_in_front_never_starts():
    f = ready_flow()
    f.on_message(NO_FACE, 0.0)
    run(f, 0.0, 30.0, step=0.5)
    assert f.phase == F.CHECKING


def test_visible_but_unregistered_face_starts_after_the_limit():
    f = ready_flow()
    f.on_message({**STEADY, "registered": False}, 0.0)
    run(f, 0.0, F.REGISTRATION_MAX_S - 0.1, step=0.5)
    assert f.phase == F.CHECKING
    run(f, F.REGISTRATION_MAX_S, F.REGISTRATION_MAX_S + 0.1)
    assert f.phase == F.COUNTDOWN


def test_enter_or_space_start_at_once_and_enter_skips_the_countdown():
    for key in ("enter", "space"):
        f = ready_flow()
        f.key(key, 0.0)
        assert f.phase == F.COUNTDOWN
    f.key("enter", 0.1)
    assert f.phase == F.DOTS


def test_countdown_speaks_three_two_one_then_dots():
    f = ready_flow()
    f.key("space", 0.0)
    f.take_speech()
    run(f, 0.0, 2.99)
    assert f.take_speech() == ["3", "2", "1"]
    f.tick(3.0)
    assert f.phase == F.DOTS


def collect_all(f, t):
    """Accept every dot like the server does; returns the time at the end."""
    for index in range(len(POINTS)):
        while not f.collecting:
            t = round(t + 0.05, 4)
            f.tick(t)
        assert f.take_outgoing() == [{"type": "collect", "index": index}]
        f.on_message({"type": "point_result", "index": index, "status": "accepted", "sample_count": 20}, t)
    return t


def test_dots_use_the_website_timing_and_report_progress():
    f = ready_flow()
    f.key("enter", 0.0)
    f.key("enter", 0.0)
    f.take_events()
    run(f, 0.0, F.FIRST_DOT_SETTLE_S - 0.05)
    assert f.take_outgoing() == []
    f.tick(F.FIRST_DOT_SETTLE_S)
    assert f.take_outgoing() == [{"type": "collect", "index": 0}]
    t = F.FIRST_DOT_SETTLE_S
    f.on_message({"type": "point_result", "index": 0, "status": "accepted", "sample_count": 20}, t)
    assert f.take_events() == [{"v": 1, "type": "calibration.progress", "done": 1, "total": 3}]
    # green flash, then the short settle before the next dot
    run(f, t, t + F.ACCEPTED_FLASH_S + F.DOT_SETTLE_S - 0.06)
    assert f.take_outgoing() == []
    run(f, t + F.ACCEPTED_FLASH_S + F.DOT_SETTLE_S - 0.05, t + F.ACCEPTED_FLASH_S + F.DOT_SETTLE_S + 0.1)
    assert f.take_outgoing() == [{"type": "collect", "index": 1}]


def test_retry_rests_then_collects_the_same_dot():
    f = ready_flow()
    f.key("enter", 0.0)
    f.key("enter", 0.0)
    run(f, 0.0, 1.0)
    f.take_outgoing()
    f.on_message({"type": "point_result", "index": 0, "status": "retry", "sample_count": 2,
                  "message": "That dot was not clear."}, 1.0)
    assert f.view(1.0)["dot"]["state"] == "rest"
    # dot 1 keeps the longer first-dot settle, like the website
    run(f, 1.0, 1.0 + F.RETRY_REST_S + F.FIRST_DOT_SETTLE_S - 0.1)
    assert f.take_outgoing() == []
    run(f, 1.0 + F.RETRY_REST_S + F.FIRST_DOT_SETTLE_S, 1.0 + F.RETRY_REST_S + F.FIRST_DOT_SETTLE_S + 0.2)
    assert f.take_outgoing() == [{"type": "collect", "index": 0}]


def test_space_pauses_and_resumes():
    f = ready_flow()
    f.key("enter", 0.0)
    f.key("enter", 0.0)
    f.key("space", 0.1)
    assert f.paused and F.SAY_PAUSED in f.take_speech()
    run(f, 0.1, 5.0)
    assert f.take_outgoing() == []
    f.key("space", 5.0)
    run(f, 5.0, 5.0 + F.FIRST_DOT_SETTLE_S + 0.1)
    assert f.take_outgoing() == [{"type": "collect", "index": 0}]


def test_success_reports_accuracy_and_closes():
    f = ready_flow()
    f.key("enter", 0.0)
    f.key("enter", 0.0)
    t = collect_all(f, 0.0)
    assert f.phase == F.FITTING
    f.take_events()
    f.on_message({"type": "result", "status": "success", "message": "ok", "worker_started": True,
                  "profile": {"accuracy_fraction": 0.036, "low_accuracy": False}}, t)
    assert f.take_events() == [{"v": 1, "type": "calibration.result", "status": "success",
                                "accuracy_percent": 96.4, "low_accuracy": False, "message": "ok"}]
    run(f, t, t + F.CLOSE_AFTER_SUCCESS_S - 0.1)
    assert not f.close
    f.tick(t + F.CLOSE_AFTER_SUCCESS_S + 0.01)
    assert f.close


def test_failure_tries_again_by_itself_after_ten_seconds():
    f = ready_flow()
    f.on_message({"type": "result", "status": "failed", "message": "Not accurate enough."}, 1.0)
    assert f.phase == F.FAILED
    assert f.take_events()[-1]["status"] == "failed"
    assert f.view(1.0)["retry_in"] == 10
    run(f, 1.0, 1.0 + F.RETRY_AFTER_FAIL_S - 0.1)
    assert not f.restart
    f.tick(1.0 + F.RETRY_AFTER_FAIL_S)
    assert f.restart


def test_no_automatic_retry_after_the_limit_but_enter_still_works():
    f = ready_flow(auto_retry=False)
    f.on_message({"type": "result", "status": "failed", "message": "Not accurate enough."}, 1.0)
    run(f, 1.0, 30.0, step=0.5)
    assert not f.restart and not f.close
    f.key("enter", 30.0)
    assert f.restart


def test_escape_cancels_the_engine_session_and_tells_the_website():
    f = ready_flow()
    f.take_events()
    f.key("escape", 1.0)
    assert f.take_outgoing() == [{"type": "cancel"}]
    assert f.take_events() == [{"v": 1, "type": "calibration.cancelled", "reason": "cancelled"}]
    assert f.close


def test_cancel_from_the_website():
    f = ready_flow()
    f.take_events()
    f.cancel(1.0, reason="website")
    assert f.take_outgoing() == [{"type": "cancel"}]
    assert f.take_events()[-1]["reason"] == "website"


def test_lost_connection_closes_without_retrying():
    f = ready_flow()
    f.connection_lost(1.0)
    assert f.phase == F.FAILED and f.message == F.LOST
    run(f, 1.0, 1.0 + F.CLOSE_AFTER_LOST_S + 0.1, step=0.5)
    assert f.close and not f.restart


def test_advice_is_sent_once_per_change():
    f = ready_flow()
    f.take_events()
    f.on_message(NO_FACE, 0.0)
    f.on_message(NO_FACE, 0.1)
    f.on_message({**STEADY, "distance_advice": "closer", "registered": False,
                  "guidance": "Move a little closer."}, 0.2)
    f.on_message(STEADY, 0.3)
    assert [(e["kind"], e["text"]) for e in f.take_events()] == [
        ("face", "We cannot see your face. Face the camera."),
        ("distance", "Move a little closer."),
        (None, None),
    ]


def test_fatal_engine_error_is_a_failure():
    f = ready_flow()
    f.on_message({"type": "error", "message": "Camera stopped: busy", "fatal": True}, 1.0)
    assert f.phase == F.FAILED and f.message == "Camera stopped: busy"


def test_accuracy_percent_matches_the_saved_record():
    from app.services.calibration_records import accuracy_percent
    for fraction in (0.0, 0.036, 0.0612, 0.1, 1.5):
        assert F.accuracy_percent(fraction) == float(accuracy_percent(fraction))
