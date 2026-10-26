"""Conservative face-exposure warnings; never used to move the cursor."""

import cv2
import numpy as np

LIGHTING_GUIDANCE = {
    "too_dark": "Your face is too dark. Add soft light in front of you.",
    "overexposed": "Your face is washed out. Move bright light away from the camera.",
}


def face_lighting_status(frame, landmarks) -> str:
    """Return "ok", "too_dark", "overexposed" or "unknown"."""
    if frame is None or not landmarks:
        return "unknown"
    height, width = frame.shape[:2]
    try:
        points = np.array([(float(lm.x) * width, float(lm.y) * height)
                           for lm in landmarks[:468]], dtype=float)
        if not np.all(np.isfinite(points)):
            return "unknown"
        x0 = max(0, int(np.min(points[:, 0])))
        x1 = min(width, int(np.max(points[:, 0])) + 1)
        y0 = max(0, int(np.min(points[:, 1])))
        y1 = min(height, int(np.max(points[:, 1])) + 1)
        if x1 - x0 < 20 or y1 - y0 < 20:
            return "unknown"
        crop = frame[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        median = float(np.median(gray))
        if median < 35 or float(np.mean(gray <= 20)) > 0.60:
            return "too_dark"
        if median > 230 or float(np.mean(gray >= 245)) > 0.60:
            return "overexposed"
    except (IndexError, TypeError, ValueError, cv2.error):
        return "unknown"
    return "ok"
