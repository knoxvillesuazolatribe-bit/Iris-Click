"""Home Suite and Gaze Tracking page for the signed-in assistive user."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.config import get_settings
from app.models.user import User
from app.schemas.home import HomeRead, TrackingViewRead
from app.services import home_service
from app.services.home_service import HomeError
from app.services.tracking_service import get_tracking_service

router = APIRouter(prefix="/me", tags=["home"], route_class=DatabaseSafeRoute)


@router.get("/home", response_model=HomeRead)
def home(user: User = Depends(require_assistive)) -> HomeRead:
    return HomeRead(full_name=user.full_name,
                    gestures=home_service.gesture_guide(get_settings()))


@router.get("/tracking", response_model=TrackingViewRead)
def tracking(user: User = Depends(require_assistive),
             db: Session = Depends(get_db)) -> TrackingViewRead:
    view = home_service.tracking_view(db, user, get_settings(), get_tracking_service())
    return TrackingViewRead.model_validate(view, from_attributes=True)


@router.post("/tracking/start", response_model=TrackingViewRead)
def start_tracking(user: User = Depends(require_assistive),
                   db: Session = Depends(get_db)) -> TrackingViewRead:
    """Starts tracking with the signed-in user's own latest calibration."""
    try:
        view = home_service.start_tracking(db, user, get_settings(), get_tracking_service())
    except HomeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return TrackingViewRead.model_validate(view, from_attributes=True)


@router.post("/tracking/stop", response_model=TrackingViewRead)
def stop_tracking(user: User = Depends(require_assistive),
                  db: Session = Depends(get_db)) -> TrackingViewRead:
    view = home_service.stop_tracking(db, user, get_settings(), get_tracking_service())
    return TrackingViewRead.model_validate(view, from_attributes=True)
