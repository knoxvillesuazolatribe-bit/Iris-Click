"""One home, on the web: IrisClick Desktop's control bar asks the open IrisClick pages to show Home.

    POST /api/desktop/go-home   tracking worker only (refused for any web page); returns how many
                                IrisClick pages were asked, so the worker can open the app window
                                at the website's Home when none is open.

The desktop app has no screens of its own besides the control bar and calibration; every page,
Home included, lives on the website. Pages hear the request on the desktop calibration channel
(``app.go_home``), which they already keep open.
"""

from fastapi import APIRouter, HTTPException, Request

from app.desktop_calibration.relay import relay

router = APIRouter(tags=["desktop"])


@router.post("/desktop/go-home")
async def go_home(request: Request) -> dict:
    # Browsers always send an Origin header, so this keeps every web page out (as calibration/open).
    if request.headers.get("origin"):
        raise HTTPException(status_code=403, detail="Only IrisClick Desktop may ask for this.")
    return {"pages": await relay.go_home()}
