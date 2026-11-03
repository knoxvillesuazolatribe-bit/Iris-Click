import pytest

from app.core.camera.timing import delivery_report


def test_regular_delivery_has_no_stalls_or_bursts():
    deliveries = [(i / 30, i * 1000 / 30) for i in range(90)]
    report = delivery_report(deliveries)
    assert report["fps"] == pytest.approx(30.0, abs=0.1)
    assert report["stall_rate"] == 0.0
    assert report["burst_rate"] == 0.0
    assert report["relative_age_ms"]["max"] == pytest.approx(0.0, abs=1e-6)


def test_batched_delivery_shows_stalls_bursts_and_age():
    # Frames exposed every 33 ms but handed over three at a time every 100 ms,
    # the pattern measured on Media Foundation in s1.jsonl.
    deliveries = []
    for i in range(90):
        exposed_ms = i * 100 / 3
        delivered_s = ((i // 3) * 100 + 100 + (i % 3) * 2) / 1000
        deliveries.append((delivered_s, exposed_ms))
    report = delivery_report(deliveries)
    assert report["stall_rate"] == pytest.approx(1 / 3, abs=0.02)
    assert report["burst_rate"] == pytest.approx(2 / 3, abs=0.02)
    # The first frame of each batch waited ~67 ms longer than the last.
    assert report["relative_age_ms"]["max"] == pytest.approx(64, abs=3)


def test_missing_or_frozen_driver_clock_gives_no_age():
    assert "relative_age_ms" not in delivery_report([(i / 30, None) for i in range(30)])
    assert "relative_age_ms" not in delivery_report([(i / 30, 5.0) for i in range(30)])
    assert delivery_report([(0.0, None)]) == {"frames": 1}


def test_driver_clock_running_at_the_wrong_rate_gives_no_age():
    # 15 fps delivery stamped as if it were 30 fps (frame_count / nominal fps).
    report = delivery_report([(i / 15, i * 1000 / 30) for i in range(60)])
    assert report["driver_clock_ratio"] == pytest.approx(0.5)
    assert "relative_age_ms" not in report
