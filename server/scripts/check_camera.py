r"""Camera + engine smoke check: run from server\ with the venv Python.

    .venv\Scripts\python scripts\check_camera.py [seconds]

Prints frame rate, face/pupil/GazeFollower hit rates. Exits 1 if the camera
cannot start. Releases the camera before exiting.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.core.gaze.estimator import GazeTracker  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    settings = get_settings()
    tracker = GazeTracker(settings.face_model_path, camera_index=settings.camera_index,
                          deep_gaze=settings.deep_gaze_enabled)
    try:
        tracker.start()
    except RuntimeError as exc:
        print(f"camera: FAILED ({exc})")
        return 1
    frames = faces = pupils = deep = nose = 0
    last_id = 0
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            reading = tracker.read()
            if reading.frame_id != last_id:
                last_id = reading.frame_id
                frames += 1
                faces += reading.face_found
                pupils += reading.left_pupil_detected and reading.right_pupil_detected
                deep += reading.deep_features is not None
                nose += reading.nose_features is not None
            time.sleep(0.005)
    finally:
        tracker.stop()
    rate = lambda n: f"{n / frames:.0%}" if frames else "n/a"  # noqa: E731
    print(f"camera: ok, {frames / seconds:.1f} fps processed over {seconds:.0f}s")
    print(f"gazefollower loaded: {tracker.deep_gaze_available}")
    print(f"face found: {rate(faces)}  nose-eye pyramid: {rate(nose)}  "
          f"pupils fitted: {rate(pupils)}  deep estimate: {rate(deep)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
