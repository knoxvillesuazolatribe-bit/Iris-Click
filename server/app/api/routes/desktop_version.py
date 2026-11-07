"""GET /api/desktop/version: lets the hosted website find IrisClick Desktop on this PC.

The website calls http://127.0.0.1:8000/api/desktop/version. An answer means the
desktop app is installed and running (and the browser allowed the website to reach
it); no answer means "show the download page". The version lets the website say
when an update is available. Only allowed websites get an answer (origin_guard).
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.version import VERSION

router = APIRouter(prefix="/desktop", tags=["desktop"])


class DesktopVersion(BaseModel):
    app: str = "IrisClick Desktop"
    version: str


@router.get("/version", response_model=DesktopVersion)
def desktop_version() -> DesktopVersion:
    return DesktopVersion(version=VERSION)
