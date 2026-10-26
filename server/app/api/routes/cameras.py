from fastapi import APIRouter, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from app.schemas.camera import CameraRead
from app.services.camera_service import get_camera_service

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
async def list_cameras() -> list[CameraRead]:
    return await run_in_threadpool(get_camera_service().scan)


@router.get("/{index}/snapshot", response_class=Response)
def camera_snapshot(index: int) -> Response:
    jpeg = get_camera_service().snapshot(index)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="No snapshot for this camera. Scan again.")
    # Snapshots are the user's own face; never let a proxy or the browser keep them.
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})
