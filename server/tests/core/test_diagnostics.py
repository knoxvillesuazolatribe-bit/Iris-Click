import json
import math

import pytest

from app.core.gaze.diagnostics import Diagnostics, percentile, summarize


def test_percentile_interpolates():
    assert percentile([0.0, 10.0], 0.5) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == pytest.approx(4.8)
    assert math.isnan(percentile([], 0.5))


def test_summarize_reports_p50_p95_max():
    summary = summarize(range(1, 101))
    assert summary["n"] == 100
    assert summary["p50"] == pytest.approx(50.5)
    assert summary["max"] == 100


def test_disabled_diagnostics_do_nothing(tmp_path):
    diagnostics = Diagnostics(enabled=False, trace_path=tmp_path / "trace.jsonl")
    diagnostics.record("tick", 5.0)
    diagnostics.count("frames")
    diagnostics.trace({"a": 1})
    assert diagnostics.maybe_report(100.0) is None
    assert not (tmp_path / "trace.jsonl").exists()


def test_report_covers_one_window_and_then_resets():
    diagnostics = Diagnostics(enabled=True, interval_s=10.0)
    assert diagnostics.maybe_report(0.0) is None
    for value in (10.0, 20.0, 30.0):
        diagnostics.record("tracker.detect", value)
    diagnostics.record("tick", math.nan)
    diagnostics.count("frames", 220)
    assert diagnostics.maybe_report(5.0) is None

    report = diagnostics.maybe_report(11.0)
    assert report["stages_ms"]["tracker.detect"]["p50"] == 20.0
    assert "tick" not in report["stages_ms"]
    assert report["rates_hz"]["frames"] == 20.0
    assert diagnostics.maybe_report(22.0)["counts"] == {}


def test_record_many_prefixes_stage_names():
    diagnostics = Diagnostics(enabled=True)
    diagnostics.maybe_report(0.0)
    diagnostics.record_many({"detect": 12.0, "deep": 30.0}, "tracker.")
    diagnostics.record_many(None)
    report = diagnostics.maybe_report(20.0)
    assert set(report["stages_ms"]) == {"tracker.detect", "tracker.deep"}


def test_trace_writes_json_lines(tmp_path):
    path = tmp_path / "trace.jsonl"
    diagnostics = Diagnostics(enabled=True, trace_path=path)
    diagnostics.trace({"frame": 1, "cursor": [1.0, 2.0]})
    diagnostics.close()
    assert json.loads(path.read_text("utf-8")) == {"frame": 1, "cursor": [1.0, 2.0]}
