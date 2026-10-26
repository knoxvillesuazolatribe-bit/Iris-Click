from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

APP_DIR = Path(__file__).resolve().parent
SERVER_DIR = APP_DIR.parent
STORAGE_DIR = APP_DIR / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVER_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "IrisClick"
    debug: bool = False
    api_prefix: str = "/api"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Supabase PostgreSQL; an empty db_host falls back to the local SQLite file.
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "postgres"
    db_user: str = ""
    db_password: SecretStr = SecretStr("")
    db_sslmode: str = "require"
    sqlite_path: Path = SERVER_DIR / "irisclick.db"

    # Site page the worker's tray opens for "Recalibrate".
    site_url: str = "http://localhost:5173"

    # Camera & engine. camera_index is only the default until the user picks a
    # camera on the calibration page (saved in device_settings_path).
    camera_index: int = 0
    device_settings_path: Path = STORAGE_DIR / "device_settings.json"
    face_model_path: Path = STORAGE_DIR / "face_landmarker.task"
    profiles_dir: Path = STORAGE_DIR / "calibration_profiles"
    worker_pid_path: Path = STORAGE_DIR / "tracking_worker.pid"
    worker_log_path: Path = STORAGE_DIR / "tracking_worker.log"
    refine_pupils: bool = True
    deep_gaze_enabled: bool = True
    low_power: bool = False

    # Worker behaviour
    auto_start_worker: bool = True
    cursor_smoothing: float = 0.25
    # Off by default: clicks come only from a deliberate left wink.
    dwell_click_enabled: bool = False
    voice_guidance_enabled: bool = True
    dwell_ms: int = 700
    dwell_radius_px: int = 45
    dwell_cooldown_ms: int = 500
    blink_threshold: float = 0.18
    # Snap gaze onto the nearest clickable control within this radius (physical
    # px); webcam gaze error (~90 px) is larger than small buttons.
    target_snap_enabled: bool = True
    target_snap_radius_px: int = 140
    # Eyes place the cursor; small head turns fine-tune it (see core/gaze/head_nudge.py).
    head_fine_tune_enabled: bool = True
    head_fine_tune_gain_px: float = 3000.0
    head_fine_tune_max_px: float = 200.0
    # Gaze resumes this long after the physical mouse stops moving.
    mouse_handoff_s: float = 2.0
    right_blink_action: Literal["go_back", "undo"] = "go_back"
    # MediaPipe labels eyes on the mirrored frame. Flip this if a wink of one
    # eye triggers the other eye's command on your camera.
    swap_blink_sides: bool = False

    @property
    def uses_postgres(self) -> bool:
        return bool(self.db_host)

    @property
    def database_url(self) -> URL:
        if not self.uses_postgres:
            return URL.create("sqlite", database=str(self.sqlite_path))
        # URL.create escapes the password; a hand-built string would break on @ / : %.
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
