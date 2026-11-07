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
    # Hybrid: only IrisClick's own websites (CORS_ORIGINS) may use this desktop app from a browser.
    from app.api.origin_guard import OriginGuard
    app.add_middleware(OriginGuard, allowed=settings.cors_origins)

    for router in (health.router, calibration.router, cameras.router, tracking.router,
                   calibration_ws.router):
        app.include_router(router, prefix=settings.api_prefix)
    # Account routes (sign-in, users). If they fail to load, the routes above still serve.
    try:
        from app.api.routes import (accessibility, admin_reports, admin_settings, admin_users,
                                    apps, assistive, auth, home, sos, voice)
        for router in (auth.router, assistive.router, admin_users.router, home.router,
                       voice.router, sos.router, accessibility.router, admin_settings.router,
                       admin_settings.public, admin_reports.router, apps.router):
            app.include_router(router, prefix=settings.api_prefix)
    except Exception:
        logging.getLogger("irisclick.api").exception("Account routes not loaded")
    # Extensions, loaded on their own so a failure here never takes down the routes above.
    try:
        from app.api.routes import (admin_speech, admin_user_apps, admin_voice_settings, admin_word_filter,
                                    desktop_link, neural_tts, speech, user_apps, word_filter)
        for router in (user_apps.router, admin_user_apps.router, word_filter.router,
                       admin_word_filter.router, speech.router, admin_speech.router,
                       neural_tts.router, admin_voice_settings.router, desktop_link.router):
            app.include_router(router, prefix=settings.api_prefix)
    except Exception:
        logging.getLogger("irisclick.api").exception("Extension routes not loaded")
    return app


app = create_app()
