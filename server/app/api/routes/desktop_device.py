"""GET /api/desktop/device: this computer's ID, for "accounts on this computer".

The hosted website asks IrisClick Desktop (http://127.0.0.1:8000) for the ID and
sends it to the hosted server in the X-IrisClick-Device header. Only allowed
websites get an answer (origin_guard), and the answer is never cached.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.accounts import device_id

router = APIRouter(prefix="/desktop", tags=["desktop"])


class DesktopDevice(BaseModel):
    device_id: str


@router.get("/device", response_model=DesktopDevice)
def desktop_device(response: Response) -> DesktopDevice:
    response.headers["Cache-Control"] = "no-store"
    return DesktopDevice(device_id=device_id.this_computer_id())
