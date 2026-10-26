import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import calibration, cameras, health, tracking
from app.api.websocket import calibration_ws
from app.api.websocket.connection_manager import ConnectionManager
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.state.calibration_connections = ConnectionManager()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (health.router, calibration.router, cameras.router, tracking.router,
                   calibration_ws.router):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
