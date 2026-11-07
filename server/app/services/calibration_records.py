"""Database copy of every calibration attempt (team decision D5: dual-write).

The JSON profile in storage/ stays what the tracker loads; this module only
mirrors attempts into calibration_profiles plus a system_logs row. Both
functions return at once: the write runs on the background writer, so a slow
or unreachable database never delays the calibration result, and a failed
write is logged and dropped.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from app.models import database
from app.models.calibration_record import STATUS_FAILED, STATUS_SUCCESSFUL, CalibrationRecord
from app.schemas.calibration import CalibrationProfileFile
from app.services import active_user
from app.services.background_db import writer
from app.services.system_log_service import log_activity

logger = logging.getLogger("irisclick.calibration_records")

FAILURE_REASONS = {
    "dot_not_clear": "Not enough clear eye images at a calibration dot.",
    "fit_failed": "The calibration model did not fit.",
    "not_accurate_enough": "The calibration was not accurate enough.",
}

LOG_SUCCESS = "calibration"
LOG_FAILED = "calibration_failed"


def accuracy_percent(error_fraction: float | None) -> Decimal | None:
    """round((1 - error) * 100, 2), kept within 0-100; None when unknown."""
    if error_fraction is None:
        return None
    value = Decimal(str((1.0 - float(error_fraction)) * 100.0))
    value = min(max(value, Decimal(0)), Decimal(100))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def record_success(profile: CalibrationProfileFile) -> None:
    """Queue a 'Successful' row for a profile that was just saved to storage/."""
    user_id = active_user.get_user_id()
    accuracy = accuracy_percent(profile.accuracy_fraction)
    record = dict(
        user_id=user_id,
        profile_file_id=profile.id,
        profile_name=profile.profile_name,
        accuracy_score=accuracy,
        error_fraction=profile.accuracy_fraction,
        low_accuracy=profile.low_accuracy,
        feature_source=profile.feature_source,
        camera_index=profile.camera_index,
        sample_count=profile.sample_count,
        calibration_data=profile.model_dump(mode="json"),
        status=STATUS_SUCCESSFUL,
        calibration_date=profile.created_at,
    )
    description = (f"Calibration '{profile.profile_name}' saved: accuracy {accuracy}% "
                   f"({profile.feature_source}, camera {profile.camera_index})")
    writer.submit(lambda: _write(record, LOG_SUCCESS, description))


def record_failure(profile_name: str, reason: str, camera_index: int | None,
                   error_fraction: float | None = None,
                   feature_source: str | None = None) -> None:
    """Queue a 'Failed' row; ``reason`` is a FAILURE_REASONS key."""
    user_id = active_user.get_user_id()
    text = FAILURE_REASONS.get(reason, reason)
    accuracy = accuracy_percent(error_fraction)
    record = dict(
        user_id=user_id,
        profile_name=profile_name or "",
        accuracy_score=accuracy,
        error_fraction=error_fraction,
        feature_source=feature_source,
        camera_index=camera_index,
        status=STATUS_FAILED,
        failure_reason=text,
    )
    description = f"Calibration '{profile_name}' failed: {text}"
    if accuracy is not None:
        description += f" Accuracy {accuracy}%."
    writer.submit(lambda: _write(record, LOG_FAILED, description))


def _write(record: dict, log_type: str, description: str) -> None:
    try:
        with database.get_session_factory()() as session:
            session.add(CalibrationRecord(**record))
            log_activity(log_type, description, record["user_id"], session=session)
            session.commit()
    except Exception as exc:
        logger.warning("Calibration record not saved to the database: %s", exc)
