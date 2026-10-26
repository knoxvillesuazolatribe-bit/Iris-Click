"""Calibration profile files in storage/calibration_profiles/.

Profiles are written and read through the ``CalibrationProfileFile`` Pydantic
model; the regression itself is rebuilt with ``CalibrationModel.from_dict``.
"""

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.core.calibration.processor import CalibrationOutcome
from app.core.gaze.screen_mapper import CalibrationModel
from app.schemas.calibration import CalibrationProfileFile, CandidateScore, ScreenSize

logger = logging.getLogger("irisclick.profiles")

_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{8}$")


def _profile_path(profiles_dir: Path, profile_id: str) -> Path:
    if not _ID_PATTERN.match(profile_id):
        raise ValueError("Invalid calibration profile id.")
    return profiles_dir / f"{profile_id}.json"


def save_profile(profiles_dir: Path, outcome: CalibrationOutcome, profile_name: str,
                 sample_count: int, screen: ScreenSize | None,
                 deep_gaze_available: bool, camera_index: int | None = None) -> CalibrationProfileFile:
    created_at = datetime.now().astimezone()
    profile = CalibrationProfileFile(
        id=f"{created_at:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
        profile_name=profile_name,
        created_at=created_at,
        feature_source=outcome.model.feature_source,
        accuracy_fraction=round(outcome.accuracy, 6),
        low_accuracy=outcome.low_accuracy,
        sample_count=sample_count,
        screen=screen,
        camera_index=camera_index,
        deep_gaze_available=deep_gaze_available,
        candidates=[CandidateScore(feature_source=s, error_fraction=round(e, 6))
                    for s, e in outcome.candidates],
        model=outcome.model.to_dict(),
    )
    profiles_dir.mkdir(parents=True, exist_ok=True)
    path = _profile_path(profiles_dir, profile.id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return profile


def list_profiles(profiles_dir: Path) -> list[CalibrationProfileFile]:
    """Valid profiles, newest first. Unreadable files are skipped and logged."""
    profiles = []
    for path in profiles_dir.glob("*.json"):
        try:
            profiles.append(CalibrationProfileFile.model_validate_json(path.read_text("utf-8")))
        except (OSError, ValidationError) as exc:
            logger.warning("Skipping unreadable calibration profile %s: %s", path.name, exc)
    return sorted(profiles, key=lambda p: p.created_at, reverse=True)


def load_profile(profiles_dir: Path, profile_id: str | None = None):
    """Return (profile, model) for ``profile_id`` or the newest profile, or (None, None)."""
    if profile_id is None:
        candidates = list_profiles(profiles_dir)
    else:
        path = _profile_path(profiles_dir, profile_id)
        if not path.is_file():
            return None, None
        candidates = [CalibrationProfileFile.model_validate_json(path.read_text("utf-8"))]
    for profile in candidates:
        model = CalibrationModel.from_dict(profile.model)
        if model is not None:
            return profile, model
        logger.warning("Calibration profile %s has an incompatible model", profile.id)
    return None, None
