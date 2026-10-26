"""Small, image-based pupil localizer for the webcam tracker.

MediaPipe's iris landmarks are an excellent *prior*, but their four-point
average is still a landmark estimate of the iris, not the visible pupil.  This
module makes a bounded second pass in each eye ROI.  It deliberately fails
closed: when contrast, geometry, or visibility is not good enough it returns
the iris prior instead of inventing a pupil position.  That makes it safe for
blink/occlusion frames and keeps old calibration profiles usable.

The implementation uses only OpenCV and NumPy, both already required by the
application.  ``fitEllipse`` gives a floating-point (sub-pixel) centre; local
CLAHE/adaptive thresholds make the candidate search less sensitive to uneven
webcam illumination.  No image is retained after ``estimate`` returns.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np


# Face-mesh points surrounding the visible eye aperture.  They are intentionally
# kept separate from the four iris-ring points: the aperture gives a tight mask
# while the ring supplies the scale/centre prior.  These are the standard
# MediaPipe Face Mesh indices and work with the 478-point FaceLandmarker output.
LEFT_EYE_CONTOUR = (362, 382, 381, 380, 374, 373, 390, 249,
                    263, 466, 388, 387, 386, 385, 384, 398)
RIGHT_EYE_CONTOUR = (33, 7, 163, 144, 145, 153, 154, 155,
                     133, 173, 157, 158, 159, 160, 161, 246)


@dataclass(frozen=True)
class PupilEstimate:
    """Result of one eye search.

    ``center`` is always finite.  It is the fitted pupil centre when
    ``detected`` is true and the iris-ring prior otherwise.  ``confidence`` is
    a bounded quality score (not a probability) useful for diagnostics.
    """

    center: tuple[float, float]
    detected: bool
    confidence: float
    reason: str = "ok"
    ellipse: Optional[tuple[float, float, float, float, float]] = None
    contrast: float = 0.0
    processing_ms: float = 0.0
    blended_center: Optional[tuple[float, float]] = None


def _point(landmarks, index: int, width: int, height: int) -> np.ndarray:
    lm = landmarks[index]
    return np.array((float(lm.x) * width, float(lm.y) * height), dtype=float)


def _finite_point(point: Sequence[float]) -> bool:
    return len(point) >= 2 and all(math.isfinite(float(v)) for v in point[:2])


def _ellipse_residual(points: np.ndarray, ellipse) -> np.ndarray:
    """Approximate normalized radial residuals for a cv2 RotatedRect."""
    (cx, cy), (major, minor), angle = ellipse
    if major < minor:
        major, minor = minor, major
        angle += 90.0
    theta = math.radians(float(angle))
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx, dy = points[:, 0] - cx, points[:, 1] - cy
    x = cos_t * dx + sin_t * dy
    y = -sin_t * dx + cos_t * dy
    norm = np.sqrt((x / max(major / 2.0, 1e-6)) ** 2
                   + (y / max(minor / 2.0, 1e-6)) ** 2)
    return np.abs(norm - 1.0)


class PupilLocalizer:
    """Localize a pupil in one eye using a landmark-bounded ROI.

    The search is intentionally bounded to ``max_roi`` pixels and a radius
    around the iris prior so its cost is predictable on the 1280x720 webcam
    stream.  ``estimate`` accepts the full BGR/RGB frame; channel ordering is
    irrelevant because only grayscale intensity is used.
    """

    def __init__(self, max_roi: int = 160, padding: int = 2,
                 centroid_blend: float = 0.0, min_contrast: float = 2.0):
        self.max_roi = int(max(32, max_roi))
        self.padding = int(max(0, padding))
        self.centroid_blend = float(max(0.0, min(1.0, centroid_blend)))
        self.min_contrast = float(max(0.0, min_contrast))

    @staticmethod
    def _prior(landmarks, iris_indices: Iterable[int], width: int,
               height: int):
        ring = np.array([_point(landmarks, i, width, height)
                         for i in iris_indices], dtype=float)
        if ring.ndim != 2 or ring.shape[0] < 3 or not np.all(np.isfinite(ring)):
            return None, None
        center = ring.mean(axis=0)
        radius = float(np.median(np.linalg.norm(ring - center, axis=1)))
        if radius < 1.5:
            # A tiny projected iris has insufficient pixels for a reliable
            # image search; returning the prior is safer than magnifying it.
            return center, None
        return center, max(radius, 2.0)

    def _fallback(self, center, reason: str, started: float, contrast=0.0):
        if center is None or not _finite_point(center):
            center = (0.0, 0.0)
        return PupilEstimate((float(center[0]), float(center[1])), False, 0.0,
                             reason, None, float(contrast),
                             (time.perf_counter() - started) * 1000.0)

    def estimate(self, frame, landmarks, iris_indices: Sequence[int],
                 eye_indices: Sequence[int], *, width: Optional[int] = None,
                 height: Optional[int] = None, iris_center=None,
                 iris_radius: Optional[float] = None,
                 eye_open: bool = True) -> PupilEstimate:
        started = time.perf_counter()
        if frame is None or landmarks is None:
            return self._fallback(iris_center, "missing_frame", started)
        image_h, image_w = frame.shape[:2]
        width = int(image_w if width is None else width)
        height = int(image_h if height is None else height)
        try:
            prior, measured_radius = self._prior(landmarks, iris_indices, width, height)
        except (IndexError, TypeError, ValueError):
            return self._fallback(iris_center, "invalid_iris_landmarks", started)
        center = np.asarray(iris_center if iris_center is not None else prior,
                            dtype=float) if (iris_center is not None or prior is not None) else None
        if center is None or center.shape[0] < 2 or not np.all(np.isfinite(center)):
            return self._fallback(center, "invalid_prior", started)
        if iris_radius is None:
            iris_radius = measured_radius
        if not eye_open:
            return self._fallback(center, "eye_closed", started)
        if iris_radius is None or not math.isfinite(float(iris_radius)) or iris_radius < 1.5:
            return self._fallback(center, "tiny_iris", started)

        try:
            eye_points = np.array([_point(landmarks, i, width, height)
                                   for i in eye_indices], dtype=float)
        except (IndexError, TypeError, ValueError):
            return self._fallback(center, "invalid_eye_landmarks", started)
        if eye_points.ndim != 2 or len(eye_points) < 6 or not np.all(np.isfinite(eye_points)):
            return self._fallback(center, "invalid_eye_landmarks", started)

        # Build a clamped polygon ROI.  Downsample only a large close-up; never
        # upscale a small eye because that would create false precision.
        x0 = max(0, int(math.floor(np.min(eye_points[:, 0])) - self.padding))
        y0 = max(0, int(math.floor(np.min(eye_points[:, 1])) - self.padding))
        x1 = min(image_w, int(math.ceil(np.max(eye_points[:, 0])) + self.padding + 1))
        y1 = min(image_h, int(math.ceil(np.max(eye_points[:, 1])) + self.padding + 1))
        if x1 - x0 < 8 or y1 - y0 < 6:
            return self._fallback(center, "tiny_roi", started)
        roi = frame[y0:y1, x0:x1]
        if roi.size == 0:
            return self._fallback(center, "empty_roi", started)
        roi_scale = min(1.0, self.max_roi / float(max(roi.shape[:2])))
        if roi_scale < 0.999:
            roi = cv2.resize(roi, None, fx=roi_scale, fy=roi_scale,
                             interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        gray = np.asarray(gray, dtype=np.uint8)
        # A small blur suppresses single-pixel lashes/glints while retaining a
        # pupil boundary. CLAHE is used only for candidate thresholding.
        blurred = cv2.GaussianBlur(gray, (3, 3), 0.65)
        normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(2, 2)).apply(blurred)
        eye_points = (eye_points - np.array((x0, y0))) * roi_scale
        local_center = (center - np.array((x0, y0), dtype=float)) * roi_scale
        iris_radius = float(iris_radius) * roi_scale
        polygon = np.round(eye_points).astype(np.int32)
        eye_mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.fillPoly(eye_mask, [polygon], 255)

        # Search around the iris but leave a margin so a whole dark iris cannot
        # win merely by having more pixels than the pupil.
        search_radius = max(3.0, min(float(iris_radius) * 0.78,
                                     max(gray.shape) * 0.45))
        yy, xx = np.ogrid[:gray.shape[0], :gray.shape[1]]
        prior_mask = ((xx - local_center[0]) ** 2 + (yy - local_center[1]) ** 2
                      <= search_radius ** 2).astype(np.uint8) * 255
        search_mask = cv2.bitwise_and(eye_mask, prior_mask)
        if int(cv2.countNonZero(search_mask)) < 12:
            return self._fallback(center, "small_search", started)

        # Glints are bright and should not split/shift the dark component. The
        # candidate mask is formed from both local adaptive and Otsu thresholds;
        # the best geometrically plausible component wins.
        block = int(max(7, min(31, min(gray.shape) // 2 * 2 + 1)))
        adaptive = cv2.adaptiveThreshold(normalized, 255,
                                         cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         cv2.THRESH_BINARY_INV, block, 3)
        search_values = blurred[search_mask > 0]
        if search_values.size < 12:
            return self._fallback(center, "small_search", started)
        _, otsu = cv2.threshold(blurred, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Otsu often chooses the *iris-vs-sclera* split on a dark iris.  A
        # second, deliberately lower split isolates the pupil-vs-iris valley.
        # It is relative to this eye's local minimum/median, so exposure shifts
        # do not require a global magic threshold.
        dark = float(np.percentile(search_values, 5))
        mid = float(np.percentile(search_values, 65))
        deep_threshold = dark + 0.42 * max(1.0, mid - dark)
        _, deep = cv2.threshold(blurred, deep_threshold, 255,
                                cv2.THRESH_BINARY_INV)
        percentile = float(np.percentile(search_values, 20))
        _, low = cv2.threshold(blurred, percentile, 255, cv2.THRESH_BINARY_INV)
        masks = (adaptive, deep, low, otsu)
        best = None
        rejects = Counter()
        best_rejected_contrast = None
        for mask in masks:
            candidate_mask = cv2.bitwise_and(mask, search_mask)
            # The old 2x2 opening erased nearly pixel-sized pupils on distant
            # laptop webcams. Preserve tiny candidates and let geometry,
            # contrast and angular support reject isolated lashes/noise.
            if iris_radius >= 7.0:
                candidate_mask = cv2.morphologyEx(
                    candidate_mask, cv2.MORPH_OPEN,
                    np.ones((2, 2), np.uint8),
                )
            contours, _ = cv2.findContours(candidate_mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_NONE)
            if not contours:
                rejects["no_dark_component"] += 1
            for contour in contours:
                if len(contour) < 5:
                    rejects["too_few_pixels"] += 1
                    continue
                area = float(cv2.contourArea(contour))
                if area < 2.0:
                    rejects["too_few_pixels"] += 1
                    continue
                try:
                    ellipse = cv2.fitEllipse(contour)
                except cv2.error:
                    rejects["irregular_boundary"] += 1
                    continue
                (cx, cy), (axis_a, axis_b), angle = ellipse
                major, minor = max(axis_a, axis_b), min(axis_a, axis_b)
                if minor < 2.0 or major <= 0:
                    rejects["too_few_pixels"] += 1
                    continue
                if major > float(iris_radius) * 1.70 or major < 2.0:
                    rejects["wrong_size"] += 1
                    continue
                ratio = minor / major
                if ratio < 0.42:
                    rejects["irregular_boundary"] += 1
                    continue
                distance = float(np.linalg.norm(np.array((cx, cy)) - local_center))
                if distance > float(iris_radius) * 0.72:
                    rejects["outside_iris_prior"] += 1
                    continue
                residual = _ellipse_residual(contour[:, 0, :].astype(float), ellipse)
                residual_median = float(np.median(residual))
                if residual_median > 0.40:
                    rejects["irregular_boundary"] += 1
                    continue
                perimeter = max(float(cv2.arcLength(contour, True)), 1.0)
                circularity = min(1.0, 4.0 * math.pi * area / (perimeter * perimeter))
                # Intensity contrast is evaluated on the original blurred ROI,
                # not the equalized image. A bright-glint fraction is a hard
                # rejection only when it dominates the putative pupil.
                mask_inside = np.zeros(gray.shape, np.uint8)
                cv2.ellipse(mask_inside, ellipse, 255, -1)
                mask_inside = cv2.bitwise_and(mask_inside, search_mask)
                inner_values = blurred[mask_inside > 0]
                annulus = cv2.subtract(cv2.dilate(mask_inside, np.ones((5, 5), np.uint8)),
                                       mask_inside)
                annulus = cv2.bitwise_and(annulus, eye_mask)
                outer_values = blurred[annulus > 0]
                if inner_values.size < 4 or outer_values.size < 4:
                    rejects["too_few_pixels"] += 1
                    continue
                contrast = float(np.median(outer_values) - np.median(inner_values))
                bright_fraction = float(np.mean(inner_values >= 235))
                if bright_fraction > 0.25:
                    rejects["reflection"] += 1
                    continue
                if best_rejected_contrast is None or contrast > best_rejected_contrast:
                    best_rejected_contrast = contrast
                if contrast < self.min_contrast:
                    rejects["low_contrast"] += 1
                    continue
                # Require support in at least three angular quadrants. This
                # rejects a dark eyelash/eyelid fragment and partial blobs.
                points = contour[:, 0, :].astype(float)
                angles = (np.arctan2(points[:, 1] - cy, points[:, 0] - cx)
                          + math.pi) % (2 * math.pi)
                quadrants = len(set((angles / (math.pi / 2)).astype(int)))
                if quadrants < 3:
                    rejects["partial_boundary"] += 1
                    continue
                prior_score = max(0.0, 1.0 - distance / (float(iris_radius) * 0.72))
                score = (2.0 * min(1.0, contrast / 35.0)
                         + 1.2 * prior_score + 0.8 * ratio
                         + 0.6 * circularity - 1.5 * residual_median)
                if best is None or score > best[0]:
                    best = (score, ellipse, contrast, ratio, residual_median)

        if best is None:
            reason = (rejects.most_common(1)[0][0] if rejects
                      else "no_confident_candidate")
            return self._fallback(center, reason, started,
                                  best_rejected_contrast or 0.0)
        score, ellipse, contrast, ratio, residual = best
        (cx, cy), (axis_a, axis_b), angle = ellipse
        # FitEllipse is already sub-pixel. Keep the historical darkness-weighted
        # candidate for v1 compatibility and paired validation, but v2 defaults
        # to the raw ellipse centre: the intensity shift proved gaze-dependent
        # rather than zero-mean in held-out mapping tests.
        fitted_mask = np.zeros(gray.shape, np.uint8)
        cv2.ellipse(fitted_mask, ellipse, 255, -1)
        fitted_values = blurred[fitted_mask > 0]
        weighted_center = np.array((cx, cy), dtype=float)
        if fitted_values.size >= 4:
            baseline = float(np.percentile(fitted_values, 85))
            yy_i, xx_i = np.indices(gray.shape)
            weights = np.maximum(0.0, baseline - blurred.astype(float))
            weights *= fitted_mask > 0
            total = float(weights.sum())
            if total > 1e-6:
                weighted_center = np.array(((xx_i * weights).sum() / total,
                                             (yy_i * weights).sum() / total))
        shift = weighted_center - np.array((cx, cy), dtype=float)
        max_shift = max(1.0, float(iris_radius) * 0.20)
        if np.linalg.norm(shift) > max_shift:
            shift *= max_shift / np.linalg.norm(shift)
        raw_center = np.array((cx, cy), dtype=float)
        legacy_center = raw_center + 0.70 * shift
        cx, cy = (raw_center + self.centroid_blend * shift).tolist()
        result_center = (float(cx / roi_scale + x0), float(cy / roi_scale + y0))
        blended_center = (float(legacy_center[0] / roi_scale + x0),
                          float(legacy_center[1] / roi_scale + y0))
        confidence = max(0.0, min(1.0,
            0.30 * min(1.0, contrast / 35.0)
            + 0.25 * ratio + 0.25 * max(0.0, 1.0 - residual / 0.40)
            + 0.20 * max(0.0, 1.0 - np.linalg.norm(np.array((cx, cy)) - local_center)
                          / (float(iris_radius) * 0.72))))
        return PupilEstimate(
            result_center, True, float(confidence), "ok",
            (result_center[0], result_center[1], float(axis_a / roi_scale),
             float(axis_b / roi_scale), float(angle)),
            float(contrast), (time.perf_counter() - started) * 1000.0,
            blended_center,
        )
