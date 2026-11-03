r"""Gaze and camera benchmarks on recorded, repeatable input.

Run from server\ with the venv Python, with the tracking worker stopped (it
owns the camera):

    python scripts\benchmark_gaze.py record s2.jsonl [--trials 24]
        [--camera-backend dshow --fourcc MJPG] [--all-engines]
    python scripts\benchmark_gaze.py replay s2.jsonl [--screen-width-cm 34.5]
        [--distance-cm 40] [--sweep] [--include-snapping]
    python scripts\benchmark_gaze.py compare s1.jsonl s2.jsonl [--screen-width-cm 34.5]
    python scripts\benchmark_gaze.py camera [--configs msmf dshow:MJPG@1 msmf@2/1080p]
        [--seconds 15] [--pupils]

record   Full-screen buttons; look at the blue one until it moves. Do not
         wink. Saves every tracker reading (features, eye openness, stage
         timings; no images), each trial's buttons and the camera delivery
         log. Never overwrites an existing file: recordings are baselines.
replay   Calibration in-sample vs held-out error, camera frame timing, raw
         gaze accuracy per target (no snapping), head-vs-eye analysis, then
         navigation modes on identical input.
compare  The headline numbers of several recordings side by side.
camera   Runs the real tracker for each backend[:FOURCC][@index][/1080p] and reports frame
         intervals, stalls, bursts, drops and relative frame age. DirectShow
         numbers cameras differently from MSMF, hence the optional @index.

Snapping modes are excluded unless --include-snapping: snapping hides gaze
error instead of measuring it. The replay omits the worker's blink hold and
glide; capture -> cursor latency is measured live with DIAGNOSTICS_ENABLED.
"""

import argparse
import dataclasses
import json
import math
import random
import sys
import time
import tkinter as tk
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.core.actions.target_snap import TargetRect  # noqa: E402
from app.core.calibration.profile import load_profile  # noqa: E402
from app.core.calibration.recenter import load_recenter  # noqa: E402
from app.core.camera.timing import delivery_report  # noqa: E402
from app.core.detection.blink_detector import BlinkDetector  # noqa: E402
from app.core.gaze.diagnostics import summarize  # noqa: E402
from app.core.gaze.estimator import GazeReading  # noqa: E402
from app.core.gaze.evaluation import (  # noqa: E402
    CursorSample,
    Trial,
    accuracy_summary,
    button_layout,
    eye_distance_cm,
    held_out_signal_models,
    per_target,
    pose_correlations,
    score_session,
)
from app.core.gaze.feature_sources import model_feature_source  # noqa: E402
from app.core.gaze.navigation import CursorNavigator, NavigationConfig  # noqa: E402
from app.core.gaze.pipeline import TRANSIENT_REASONS, GazePipeline  # noqa: E402
from app.core.gaze.screen_mapper import ScreenCorrection  # noqa: E402
from app.desktop.display import enable_dpi_awareness  # noqa: E402
from app.services.tracking_service import pid_alive  # noqa: E402
from app.workers.tracking_worker import start_tracker  # noqa: E402

TRIAL_S = 2.5
COUNTDOWN_S = 3.0
POLL_MS = 5
# Goal centres: a 6x4 grid between 8% and 92% of the screen, shuffled.
GRID_X = (0.08, 0.25, 0.42, 0.58, 0.75, 0.92)
GRID_Y = (0.08, 0.36, 0.64, 0.92)
SWEEP_MINCUTOFF = (0.3, 0.5, 0.8, 1.2, 1.8)
SWEEP_BETA = (0.003, 0.01, 0.03, 0.06)
CAMERA_CONFIGS = ("msmf", "msmf:MJPG", "dshow@1", "dshow:MJPG@1", "msmf")
CAMERA_SECONDS = 15.0
CAMERA_RELEASE_S = 1.0
CAMERA_WARMUP_S = 4.0
# Only when a recording lacks the eye geometry to measure it.
DEFAULT_DISTANCE_CM = 55.0


def _rect(values) -> TargetRect:
    return TargetRect(*values[:4], values[4] if len(values) > 4 else "")


def _worker_running(settings) -> bool:
    try:
        pid = json.loads(settings.worker_pid_path.read_text("utf-8")).get("pid")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(pid, int) and pid_alive(pid)


def _camera_settings(settings, backend: str | None, fourcc: str | None,
                     resolution: str | None = None):
    update = {}
    if resolution:
        update["camera_resolution"] = resolution
    if backend:
        update["camera_backend"] = backend
    if fourcc is not None:
        update["camera_fourcc"] = fourcc.upper()
    return settings.model_copy(update=update)


def _camera_index(settings, profile) -> int:
    return profile.camera_index if profile.camera_index is not None else settings.camera_index


def _fmt(value, spec: str = ".0f", suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return f"{value:{spec}}{suffix}"


def record(path: Path, trials: int, profile_id: str | None, backend: str | None,
           fourcc: str | None, all_engines: bool = False) -> int:
    if path.exists():
        print(f"{path} already exists. Recordings are baselines and are never overwritten; "
              "choose a new name.")
        return 1
    settings = _camera_settings(get_settings(), backend, fourcc)
    if _worker_running(settings):
        print("The tracking worker is running and owns the camera. Quit it from the tray first.")
        return 1
    profile, model = load_profile(settings.profiles_dir, profile_id)
    correction = load_recenter(settings.recenter_path, profile.id) if profile else None
    if model is None:
        print("No usable calibration profile. Calibrate first.")
        return 1
    enable_dpi_awareness()
    # All engines record every candidate source (pupil fit, MGazeNet) so
    # compare_estimators.py can score them; it lowers the frame rate.
    tracker = start_tracker(settings, _camera_index(settings, profile),
                            None if all_engines else model)

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
    canvas = tk.Canvas(root, bg="#1e1e1e", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    rng = random.Random(7)
    centres = [(x, y) for x in GRID_X for y in GRID_Y]
    rng.shuffle(centres)
    centres = (centres * math.ceil(trials / len(centres)))[:trials]

    out = path.open("x", encoding="utf-8")
    out.write(json.dumps({
        "type": "meta", "profile_id": profile.id, "feature_source": model.feature_source,
        "screen": [screen_w, screen_h], "camera": tracker.camera_info,
        "camera_settings": {"backend": settings.camera_backend, "fourcc": settings.camera_fourcc},
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # Readings are uncorrected features; replay applies this like the worker.
        "recenter": correction.as_list() if correction is not None else None,
    }) + "\n")
    state = {"last_frame": 0, "trial": -1, "trial_end": 0.0}
    started = time.perf_counter()

    def show_trial(index: int):
        canvas.delete("all")
        cx, cy = centres[index]
        goal, targets = button_layout(cx * screen_w, cy * screen_h, screen_w, screen_h)
        for target in targets:
            colour = "#3fa7ff" if target == goal else "#555555"
            canvas.create_rectangle(target.left, target.top, target.right, target.bottom,
                                    fill=colour, outline="")
        root.update_idletasks()
        onset = time.perf_counter()
        state.update(trial=index, trial_end=onset + TRIAL_S)
        out.write(json.dumps({
            "type": "trial", "index": index, "onset": onset, "end": onset + TRIAL_S,
            "goal": dataclasses.astuple(goal),
            "targets": [dataclasses.astuple(t) for t in targets],
        }) + "\n")

    def tick():
        now = time.perf_counter()
        reading = tracker.read()
        if reading.frame_id != state["last_frame"]:
            state["last_frame"] = reading.frame_id
            row = {k: v for k, v in dataclasses.asdict(reading).items() if k != "preview"}
            out.write(json.dumps({"type": "frame", **row}) + "\n")
        if tracker.last_error:
            print(f"Camera stopped: {tracker.last_error}")
            root.destroy()
            return
        if now - started < COUNTDOWN_S:
            canvas.delete("all")
            canvas.create_text(screen_w / 2, screen_h / 2, fill="white", font=("Segoe UI", 20),
                               text="Look at the blue button until it moves. Do not wink.\n"
                                    f"Starting in {COUNTDOWN_S - (now - started):.0f} s")
        elif now >= state["trial_end"]:
            if state["trial"] + 1 >= trials:
                root.destroy()
                return
            show_trial(state["trial"] + 1)
        root.after(POLL_MS, tick)

    root.bind("<Escape>", lambda _: root.destroy())
    root.after(POLL_MS, tick)
    try:
        root.mainloop()
    finally:
        tracker.stop()
        out.write(json.dumps({"type": "deliveries", "frames": tracker.delivery_log()}) + "\n")
        out.close()
    print(f"Saved {path} (camera: {tracker.camera_info})")
    return 0


def load_session(path: Path):
    meta, trials, readings, deliveries = {}, [], [], []
    fields = {f.name for f in dataclasses.fields(GazeReading)}
    for line in path.read_text("utf-8").splitlines():
        row = json.loads(line)
        kind = row.pop("type")
        if kind == "meta":
            meta = row
        elif kind == "trial":
            trials.append(Trial(_rect(row["goal"]), row["onset"], row["end"],
                                tuple(_rect(t) for t in row["targets"])))
        elif kind == "frame":
            readings.append(GazeReading(**{k: v for k, v in row.items() if k in fields}))
        elif kind == "deliveries":
            deliveries = [tuple(d) for d in row["frames"]]
    return meta, trials, readings, deliveries


def replay_mode(config: NavigationConfig, model, readings, trials, screen, smoothing):
    pipeline = GazePipeline()
    navigator = CursorNavigator(config, *screen)
    samples, cost_ms = [], []
    trial_index = 0
    for reading in readings:
        t = reading.captured_at
        while trial_index + 1 < len(trials) and t >= trials[trial_index + 1].onset:
            trial_index += 1
        targets = trials[trial_index].targets if trials and t >= trials[0].onset else ()
        started = time.perf_counter()
        estimate = pipeline.process(reading, model, smoothing, output_size=screen, now=t)
        if estimate is None:
            if pipeline.reason not in TRANSIENT_REASONS:
                navigator.reset()
            continue
        step = navigator.update(estimate, reading, targets, now=t)
        cost_ms.append((time.perf_counter() - started) * 1000.0)
        samples.append(CursorSample(t, step.x, step.y))
    return samples, cost_ms


def tracker_report(readings, deliveries) -> dict:
    stages: dict[str, list] = {}
    for reading in readings:
        for name, value in (reading.timings or {}).items():
            stages.setdefault(name, []).append(value)
    span = readings[-1].captured_at - readings[0].captured_at
    dropped = sum(r.dropped for r in readings)
    blink = BlinkDetector(threshold=get_settings().blink_threshold)
    winks = [side for r in readings
             if (side := blink.update(r.left_ear, r.right_ear, now=r.captured_at)) is not None]
    report = {
        "processed_fps": round(len(readings) / span, 1),
        "camera_fps": round((len(readings) + dropped) / span, 1),
        "dropped_rate": round(dropped / max(1, len(readings) + dropped), 3),
        "face_rate": round(sum(r.face_found for r in readings) / len(readings), 3),
        "processed_frames": delivery_report([(r.captured_at, r.camera_ms) for r in readings]),
        "stages_ms": {name: summarize(values) for name, values in stages.items()},
        "blink_events_while_told_not_to_wink": winks,
    }
    if deliveries:
        report["camera_deliveries"] = delivery_report(deliveries)
    return report


def analyze(path: Path, profile_id: str | None, cm_per_px: float | None,
            distance_cm: float | None) -> dict | None:
    """``distance_cm`` None: measured from the recording (DEFAULT_DISTANCE_CM if unknown)."""
    settings = get_settings()
    meta, trials, readings, deliveries = load_session(path)
    if not readings or not trials:
        print(f"{path}: no frames or trials.")
        return None
    if distance_cm is None:
        camera = meta.get("camera") or {}
        measured = (eye_distance_cm(readings, camera["width"], camera["height"])
                    if camera.get("width") else None)
        distance_cm = measured or DEFAULT_DISTANCE_CM
    _, model = load_profile(settings.profiles_dir, profile_id or meta.get("profile_id"))
    if model is None:
        print(f"{path}: its calibration profile {meta.get('profile_id')} is missing.")
        return None
    screen = tuple(meta["screen"])
    source = model_feature_source(model)
    def raw_targets():
        raw, _ = replay_mode(NavigationConfig(mode="raw"), model, readings, trials, screen,
                             settings.cursor_smoothing)
        return per_target(raw, trials)

    uncorrected = raw_targets()
    targets, recenter = uncorrected, meta.get("recenter")
    if recenter:
        model.set_correction(ScreenCorrection(recenter))
        targets = raw_targets()
    return {
        "path": path, "meta": meta, "model": model, "source": source, "screen": screen,
        "trials": trials, "readings": readings, "distance_cm": distance_cm,
        "calibration": {
            "in_sample": model.fixation_error, "held_out": model.validation_error,
            # RMS is dominated by corner dots, which become extrapolation when held out.
            "held_out_median": (float(np.median(list(model.held_out_dot_errors.values())))
                                if model.held_out_dot_errors else None),
        },
        "tracker": tracker_report(readings, deliveries),
        "targets": targets,
        "accuracy": accuracy_summary(targets, screen[1], cm_per_px, distance_cm),
        "recentered": bool(recenter),
        "accuracy_without_recenter": accuracy_summary(uncorrected, screen[1], cm_per_px,
                                                      distance_cm),
        "pose": pose_correlations(readings, targets, source),
        "signals": held_out_signal_models(readings, trials, source),
    }


def _print_analysis(result: dict):
    meta, screen = result["meta"], result["screen"]
    calibration = result["calibration"]
    print(f"== {result['path']}  profile {meta.get('profile_id')} ({result['source']}), "
          f"screen {screen[0]}x{screen[1]}, camera {meta.get('camera', 'not recorded')}, "
          f"eye distance {result['distance_cm']:.0f} cm")
    width = screen[0]
    print(f"Calibration per-dot error: in-sample {_fmt(calibration['in_sample'], '.3f')} "
          f"(~{_fmt((calibration['in_sample'] or math.nan) * width)} px), held-out "
          f"{_fmt(calibration['held_out'], '.3f')} "
          f"(~{_fmt((calibration['held_out'] or math.nan) * width)} px; n/a = profile "
          "calibrated before held-out scoring existed)")
    print(json.dumps(result["tracker"], indent=2))

    accuracy = result["accuracy"]
    if result["recentered"]:
        before = result["accuracy_without_recenter"]
        print(f"\nSaved re-centre applied (as live). Without it: median error "
              f"{_fmt(before['error_px_p50'])} px, bias x {_fmt(before['bias_x_px'], '+.0f')} "
              f"y {_fmt(before['bias_y_px'], '+.0f')} px, top-row reach "
              f"{_fmt(before['top_row_reach_rate'] * 100, '.0f', '%')}")
    print("\nRaw calibrated gaze, no filtering or snapping (one value per target):")
    print(f"  median error {_fmt(accuracy['error_px_p50'])} px "
          f"({_fmt(accuracy.get('error_deg_p50'), '.2f', ' deg')}), p95 "
          f"{_fmt(accuracy['error_px_p95'])} px; bias x {_fmt(accuracy['bias_x_px'], '+.0f')} "
          f"y {_fmt(accuracy['bias_y_px'], '+.0f')} px (+y = too low); spread while fixating "
          f"{_fmt(accuracy['spread_px'])} px")
    print(f"  reached within 100 px: all {accuracy['reach_rate']:.0%}, top row "
          f"{_fmt(accuracy['top_row_reach_rate'] * 100, '.0f', '%')} of "
          f"{accuracy['top_row_targets']} (top-row y bias "
          f"{_fmt(accuracy['top_row_bias_y_px'], '+.0f')} px)")
    print(f"  {'goal x,y':>12}  {'median x,y':>12}  {'offset':>12}  {'spread':>9}  reached")
    for r in sorted(result["targets"], key=lambda r: (r.goal[1], r.goal[0])):
        print(f"  {r.goal[0]:5.0f},{r.goal[1]:5.0f}  {r.median[0]:5.0f},{r.median[1]:5.0f}  "
              f"{r.offset[0]:+5.0f},{r.offset[1]:+5.0f}  {r.spread[0]:3.0f},{r.spread[1]:3.0f}  "
              f"{'yes' if r.reached else 'NO'}")

    pose = result["pose"]
    if pose:
        print("\nCorrelation with goal height (|r| near 1 = carries the vertical aim):")
        print("  " + "  ".join(f"{k} {v:+.2f}" for k, v in pose["goal_y_vs"].items()))
        print("Correlation with vertical error (large |r| = this signal causes the error):")
        print("  " + "  ".join(f"{k} {v:+.2f}" for k, v in pose["error_y_vs"].items()))
    if result["signals"]:
        print("\nHeld-out (leave-one-target-out) models fitted on this session:")
        for name, s in result["signals"].items():
            print(f"  {name:<10} median {s['error_px_p50']:5.0f} px, mean "
                  f"{s['error_px_mean']:5.0f} px, |vertical| median {s['abs_error_y_px_p50']:4.0f} px")


def _mode_row(name: str, score: dict, cost_ms) -> str:
    cost = summarize(cost_ms) if cost_ms else {"p50": math.nan, "p95": math.nan}
    deg = (f"{score['error_deg_p50']:5.2f}/{score['error_deg_p95']:5.2f}"
           if "error_deg_p50" in score else "    -/-    ")
    return (f"{name:<28} {score['error_px_p50']:6.0f}/{score['error_px_p95']:4.0f}  {deg}  "
            f"{score['jitter_px_rms']:6.1f}  {score['acquired_rate']:5.0%}  "
            f"{_fmt(score['acquire_ms_p50'], '7.0f')}  {score['wrong_target_rate']:6.1%}  "
            f"{cost['p50']:5.2f}/{cost['p95']:5.2f}")


def replay(path: Path, sweep: bool, snapping: bool, profile_id: str | None,
           screen_width_cm: float | None, distance_cm: float | None) -> int:
    settings = get_settings()
    meta, *_ = load_session(path)
    cm_per_px = screen_width_cm / meta["screen"][0] if screen_width_cm else None
    result = analyze(path, profile_id, cm_per_px, distance_cm)
    if result is None:
        return 1
    _print_analysis(result)
    distance_cm = result["distance_cm"]

    model, readings, trials, screen = (result["model"], result["readings"], result["trials"],
                                       result["screen"])
    print(f"\n{'mode':<28} {'err px p50/p95':>14}  {'deg p50/p95':>11}  {'jitter':>6}  "
          f"{'acq':>5}  {'acq ms':>7}  {'wrong':>6}  {'cost ms p50/p95':>15}")
    configs = [(mode, NavigationConfig.from_settings(settings, mode=mode, snap_enabled=False))
               for mode in ("raw", "filtered", "head", "steer")]
    configs.append(("steer (edge off)", NavigationConfig.from_settings(
        settings, mode="steer", snap_enabled=False, edge_sensitivity="off")))
    configs.append(("legacy (no snap)", NavigationConfig.from_settings(
        settings, mode="legacy", snap_enabled=False)))
    if snapping:
        configs += [
            ("steer (snap)", NavigationConfig.from_settings(settings, mode="steer",
                                                            snap_enabled=True)),
            ("legacy", NavigationConfig.from_settings(settings, mode="legacy", snap_enabled=True)),
            ("assisted", NavigationConfig.from_settings(settings, mode="assisted")),
            ("assisted (no fixation)", NavigationConfig.from_settings(
                settings, mode="assisted", assist_enabled=False)),
        ]
    if sweep:
        configs += [(f"filtered fc={fc} b={beta}", NavigationConfig.from_settings(
            settings, mode="filtered", filter_mincutoff=fc, filter_beta=beta))
            for fc in SWEEP_MINCUTOFF for beta in SWEEP_BETA]
    for name, config in configs:
        samples, cost = replay_mode(config, model, readings, trials, screen,
                                    settings.cursor_smoothing)
        print(_mode_row(name, score_session(samples, trials, cm_per_px, distance_cm), cost))
    return 0


def compare(paths: list[Path], screen_width_cm: float | None, distance_cm: float | None) -> int:
    results = []
    for path in paths:
        meta, *_ = load_session(path)
        cm_per_px = screen_width_cm / meta["screen"][0] if screen_width_cm else None
        result = analyze(path, None, cm_per_px, distance_cm)
        if result is None:
            return 1
        results.append(result)

    def tracker(r, *keys):
        value = r["tracker"]
        for key in keys:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        return value if not isinstance(value, dict) else None

    def first(*values):
        return next((v for v in values if v is not None), math.nan)

    def width(r):
        return r["screen"][0]

    rows = [
        ("profile", lambda r: r["meta"].get("profile_id", "?")[:24]),
        ("feature source", lambda r: r["source"]),
        ("camera", lambda r: "{backend} {fourcc} {width}x{height}".format(
            **r["meta"]["camera"]) if r["meta"].get("camera") else "not recorded"),
        ("calib in-sample err px", lambda r: _fmt((r["calibration"]["in_sample"] or math.nan)
                                                  * width(r))),
        ("calib held-out err px", lambda r: _fmt((r["calibration"]["held_out"] or math.nan)
                                                 * width(r))),
        ("calib held-out median px", lambda r: _fmt(
            (r["calibration"]["held_out_median"] or math.nan) * width(r))),
        ("eye distance cm", lambda r: _fmt(r["distance_cm"])),
        ("re-centre applied", lambda r: "yes" if r["recentered"] else "no"),
        ("raw err px p50", lambda r: _fmt(r["accuracy"]["error_px_p50"])),
        ("  without re-centre", lambda r: _fmt(r["accuracy_without_recenter"]["error_px_p50"])),
        ("raw err deg p50", lambda r: _fmt(r["accuracy"].get("error_deg_p50"), ".2f")),
        ("raw err px p95", lambda r: _fmt(r["accuracy"]["error_px_p95"])),
        ("bias x px", lambda r: _fmt(r["accuracy"]["bias_x_px"], "+.0f")),
        ("bias y px (+ = low)", lambda r: _fmt(r["accuracy"]["bias_y_px"], "+.0f")),
        ("fixation spread px", lambda r: _fmt(r["accuracy"]["spread_px"])),
        ("reach <=100px all", lambda r: _fmt(r["accuracy"]["reach_rate"] * 100, ".0f", "%")),
        ("reach <=100px top row", lambda r: _fmt(r["accuracy"]["top_row_reach_rate"] * 100,
                                                 ".0f", "%")),
        ("r(goal_y, eye_y)", lambda r: _fmt(r["pose"].get("goal_y_vs", {}).get(
            "eye_y", r["pose"].get("goal_y_vs", {}).get("gaze_y")), "+.2f")),
        ("r(goal_y, pitch)", lambda r: _fmt(r["pose"].get("goal_y_vs", {}).get("pitch"), "+.2f")),
        ("r(y error, pitch)", lambda r: _fmt(r["pose"].get("error_y_vs", {}).get("pitch"),
                                             "+.2f")),
        ("held-out eye-only px", lambda r: _fmt(r["signals"].get("eye_only", {}).get(
            "error_px_p50"))),
        ("held-out head-only px", lambda r: _fmt(r["signals"].get("head_only", {}).get(
            "error_px_p50"))),
        ("held-out combined px", lambda r: _fmt(r["signals"].get("combined", {}).get(
            "error_px_p50"))),
        ("processed fps", lambda r: _fmt(r["tracker"]["processed_fps"], ".1f")),
        ("camera fps", lambda r: _fmt(r["tracker"]["camera_fps"], ".1f")),
        ("dropped", lambda r: _fmt(r["tracker"]["dropped_rate"] * 100, ".0f", "%")),
        # Recordings without a delivery log fall back to processed-frame timing.
        ("frame interval p95 ms", lambda r: _fmt(first(
            tracker(r, "camera_deliveries", "interval_ms", "p95"),
            tracker(r, "processed_frames", "interval_ms", "p95")))),
        ("frame stalls", lambda r: _fmt(first(
            tracker(r, "camera_deliveries", "stall_rate"),
            tracker(r, "processed_frames", "stall_rate")) * 100, ".0f", "%")),
        ("relative frame age p95 ms", lambda r: _fmt(
            tracker(r, "camera_deliveries", "relative_age_ms", "p95"), ".0f")),
        ("detect ms p50", lambda r: _fmt(tracker(r, "stages_ms", "detect", "p50"), ".1f")),
        ("tracker total ms p50", lambda r: _fmt(tracker(r, "stages_ms", "total", "p50"), ".1f")),
    ]
    names = [r["path"].name for r in results]
    print(f"{'metric':<27}" + "".join(f"{n:>26}" for n in names))
    for label, value in rows:
        print(f"{label:<27}" + "".join(f"{value(r):>26}" for r in results))
    return 0


def _parse_camera_config(config: str, default_index: int) -> tuple[str, str, int, str]:
    """``backend[:FOURCC][@index][/720p|1080p|1440p]``.

    DirectShow numbers devices differently from MSMF.
    """
    config, _, resolution = config.partition("/")
    spec, _, index = config.partition("@")
    backend, _, fourcc = spec.partition(":")
    return backend, fourcc, int(index) if index else default_index, resolution or "720p"


def feature_jitter(readings, attribute: str) -> float | None:
    """Median frame-to-frame change of a gaze feature pair (x1000) while the gaze is held still.

    Features are normalised by eye spacing, so values compare across resolutions.
    """
    points = [values[:2] for r in readings if (values := getattr(r, attribute)) is not None]
    if len(points) < 10:
        return None
    steps = np.linalg.norm(np.diff(np.asarray(points, dtype=float), axis=0), axis=1)
    return float(np.median(steps)) * 1000.0


def camera(configs: list[str], seconds: float, warmup: float, profile_id: str | None,
           pupils: bool = False) -> int:
    base = get_settings()
    if _worker_running(base):
        print("The tracking worker is running and owns the camera. Quit it from the tray first.")
        return 1
    profile, model = load_profile(base.profiles_dir, profile_id)
    if model is None:
        print("No usable calibration profile; the tracker needs one to choose its engines.")
        return 1
    rows = []
    for config in configs:
        backend, fourcc, index, resolution = _parse_camera_config(
            config, _camera_index(base, profile))
        settings = _camera_settings(base, backend, fourcc, resolution)
        if pupils:
            # Pupil fitting on, MGazeNet off: measures the eye-crop path alone.
            settings = settings.model_copy(update={"refine_pupils": True,
                                                   "deep_gaze_enabled": False})
        tracker = None
        try:
            tracker = start_tracker(settings, index, None if pupils else model)
            # Auto-exposure settles in the first seconds and lowers the frame
            # rate meanwhile; it would penalise whichever config runs first.
            measure_from = time.perf_counter() + warmup
            readings, last = [], 0
            deadline = measure_from + seconds
            while time.perf_counter() < deadline:
                reading = tracker.read()
                if reading.frame_id != last and reading.captured_at >= measure_from:
                    readings.append(reading)
                last = reading.frame_id
                time.sleep(0.002)
            deliveries = [d for d in tracker.delivery_log() if d[0] >= measure_from]
            info = tracker.camera_info
        except RuntimeError as exc:
            rows.append((config, f"FAILED: {exc}", None, None, []))
            continue
        finally:
            if tracker is not None:
                try:
                    tracker.stop()
                except RuntimeError:
                    pass
            time.sleep(CAMERA_RELEASE_S)
        faces = [r for r in readings if r.face_found]
        rows.append((config, info, delivery_report(deliveries),
                     tracker_report(readings, []) if len(readings) > 2 else None,
                     faces))

    print(f"{'config':<18} {'negotiated':<26} {'cam fps':>7} {'interval p50/p95/max':>21} "
          f"{'stall':>6} {'burst':>6} {'age p50/p95':>12} {'proc fps':>8} {'drop':>5} "
          f"{'detect':>6} {'face':>5} {'clock':>6}")
    jitter_rows = []
    for config, info, deliveries, processed, faces in rows:
        if deliveries is None:
            print(f"{config:<18} {info}")
            continue
        negotiated = f"{info['backend']} {info['fourcc']} {info['width']}x{info['height']}"
        interval = deliveries.get("interval_ms", {})
        age = deliveries.get("relative_age_ms")
        processed = processed or {}
        detect = processed.get("stages_ms", {}).get("detect", {}).get("p50")
        interval_text = "/".join(_fmt(interval.get(k)) for k in ("p50", "p95", "max"))
        age_text = f"{_fmt(age['p50'])}/{_fmt(age['p95'])}" if age else "n/a"
        clock = deliveries.get('driver_clock_ratio')
        print(f"{config:<18} {negotiated:<26} {_fmt(deliveries.get('fps'), '7.1f')} "
              f"{interval_text:>21} {_fmt(deliveries.get('stall_rate', math.nan) * 100, '5.0f', '%')} "
              f"{_fmt(deliveries.get('burst_rate', math.nan) * 100, '5.0f', '%')} {age_text:>12} "
              f"{_fmt(processed.get('processed_fps'), '8.1f')} "
              f"{_fmt(processed.get('dropped_rate', math.nan) * 100, '4.0f', '%')} "
              f"{_fmt(detect, '6.1f')} "
              f"{_fmt(processed.get('face_rate', math.nan) * 100, '4.0f', '%')} "
              f"{_fmt(clock, '6.3f')}")
        if faces:
            iris = [r.eye_line["eye_distance"] * info["width"] for r in faces
                    if r.eye_line and "eye_distance" in r.eye_line]
            pupil_rate = sum(r.left_pupil_detected and r.right_pupil_detected
                             for r in faces) / len(faces)
            jitter_rows.append((config, np.median(iris) if iris else math.nan,
                                feature_jitter(faces, "midpoint_features"),
                                feature_jitter(faces, "pupil_midpoint_features"), pupil_rate))
    print("\nstall: interval > 2 frame periods; burst: < 0.5 periods; age: extra delivery "
          "delay over the least-delayed frame (needs a real-time driver clock); clock: driver "
          "timestamp rate vs host clock, 1.000 = real time.")
    if jitter_rows:
        print(f"\n{'config':<18} {'eye px':>7} {'landmark jitter':>16} {'pupil jitter':>13} "
              f"{'pupils fitted':>14}")
        for config, eye_px, landmark, pupil, rate in jitter_rows:
            print(f"{config:<18} {_fmt(eye_px, '7.0f')} {_fmt(landmark, '16.2f')} "
                  f"{_fmt(pupil, '13.2f')} {_fmt(rate * 100, '13.0f', '%')}")
        print("eye px: eye-centre spacing in pixels. jitter: median frame-to-frame feature "
              "change x1000 with the gaze held still; lower = steadier eye signal.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("session", type=Path)
    rec.add_argument("--trials", type=int, default=24)
    rec.add_argument("--profile-id")
    rec.add_argument("--camera-backend", choices=("auto", "msmf", "dshow"))
    rec.add_argument("--fourcc", help='pixel format, e.g. MJPG; "" for the default')
    rec.add_argument("--all-engines", action="store_true",
                     help="also run pupil fitting and MGazeNet, for compare_estimators.py")
    rep = sub.add_parser("replay")
    rep.add_argument("session", type=Path)
    rep.add_argument("--sweep", action="store_true")
    rep.add_argument("--include-snapping", action="store_true")
    rep.add_argument("--profile-id")
    for p in (rep, cmp := sub.add_parser("compare")):
        p.add_argument("--screen-width-cm", type=float,
                       help="visible screen width, e.g. 34.5 for a 15.6\" 16:9 laptop")
        p.add_argument("--distance-cm", type=float,
                       help="eye-to-screen distance for degrees (default: measured)")
    cmp.add_argument("sessions", type=Path, nargs="+")
    cam = sub.add_parser("camera")
    cam.add_argument("--configs", nargs="+", default=list(CAMERA_CONFIGS),
                     help="backend[:FOURCC][@index][/720p|1080p|1440p], "
                          "e.g. msmf dshow:MJPG@1 msmf@2/1080p")
    cam.add_argument("--seconds", type=float, default=CAMERA_SECONDS)
    cam.add_argument("--warmup", type=float, default=CAMERA_WARMUP_S,
                     help="seconds discarded while auto-exposure settles")
    cam.add_argument("--profile-id")
    cam.add_argument("--pupils", action="store_true",
                     help="force pupil fitting on (MGazeNet off) to compare eye-crop jitter")
    args = parser.parse_args()
    if args.command == "record":
        return record(args.session, args.trials, args.profile_id, args.camera_backend,
                      args.fourcc, args.all_engines)
    if args.command == "replay":
        return replay(args.session, args.sweep, args.include_snapping, args.profile_id,
                      args.screen_width_cm, args.distance_cm)
    if args.command == "compare":
        return compare(args.sessions, args.screen_width_cm, args.distance_cm)
    return camera(args.configs, args.seconds, args.warmup, args.profile_id, args.pupils)


if __name__ == "__main__":
    sys.exit(main())
