from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.calibration import CalibrationProfileRead
from app.services.calibration_service import list_profile_summaries

router = APIRouter(prefix="/calibration-profiles", tags=["calibration"])


@router.get("", response_model=list[CalibrationProfileRead])
def list_calibration_profiles() -> list[CalibrationProfileRead]:
    return list_profile_summaries(get_settings())


@router.get("/latest", response_model=CalibrationProfileRead)
def latest_calibration_profile() -> CalibrationProfileRead:
    profiles = list_profile_summaries(get_settings())
    if not profiles:
        raise HTTPException(status_code=404, detail="No calibration profile yet.")
    return profiles[0]
