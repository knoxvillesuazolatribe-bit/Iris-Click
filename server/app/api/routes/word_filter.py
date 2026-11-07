"""Word filter check for the signed-in assistive user (extension).

The site calls this before speaking or showing text. Saving is filtered on
the server anyway, so a site that skips this call still stores masked text.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_assistive
from app.models.user import User
from app.schemas.word_filter import CheckRead, CheckRequest
from app.services import word_filter_service

router = APIRouter(prefix="/me/filter", tags=["word filter"], route_class=DatabaseSafeRoute)


@router.post("/check", response_model=CheckRead)
def check(body: CheckRequest, _user: User = Depends(require_assistive), db: Session = Depends(get_db)):
    result = word_filter_service.check(db, body.text)
    return CheckRead(masked_text=result.masked_text, was_filtered=result.was_filtered,
                     matches_count=result.matches_count, speak_text=result.speak_text)
