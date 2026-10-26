import logging

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models.database import check_connection
from app.schemas.health import DatabaseHealthRead, HealthRead

logger = logging.getLogger("irisclick.health")

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok", app_name=get_settings().app_name)


@router.get("/database", response_model=DatabaseHealthRead)
async def database_health() -> DatabaseHealthRead:
    settings = get_settings()
    backend = "postgresql" if settings.uses_postgres else "sqlite"
    host = settings.db_host or None
    try:
        await run_in_threadpool(check_connection)
    except SQLAlchemyError as exc:
        # Driver messages can echo connection details; log them, return a summary.
        logger.warning("Database health check failed: %s", exc)
        return DatabaseHealthRead(status="unreachable", backend=backend, host=host,
                                  detail=type(exc.orig or exc).__name__)
    return DatabaseHealthRead(status="ok", backend=backend, host=host)
