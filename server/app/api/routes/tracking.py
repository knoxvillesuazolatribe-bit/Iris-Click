from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.schemas.tracking import WorkerStartRequest, WorkerStatusRead
from app.services.tracking_service import get_tracking_service

router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.get("/status", response_model=WorkerStatusRead)
def tracking_status() -> WorkerStatusRead:
    return get_tracking_service().status()


@router.post("/start", response_model=WorkerStatusRead)
async def start_tracking(body: WorkerStartRequest | None = None) -> WorkerStatusRead:
    try:
        return await run_in_threadpool(
            get_tracking_service().start, body.profile_id if body else None)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop", response_model=WorkerStatusRead)
async def stop_tracking() -> WorkerStatusRead:
    return await run_in_threadpool(get_tracking_service().stop)
