from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    # Postgres schema holding the IrisClick tables. Supabase's public schema
    # keeps the legacy tables, two of which share names with ours.
    db_schema: str = Field("irisclick", pattern=r"^[a-z_][a-z0-9_]*$")

    # Email for Emergency SOS (team decision D8). Empty host: SOS alerts fail
    # with "email is not set up" instead of pretending to send.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_s: float = Field(15.0, gt=0)

    # Time zone for dates and times people read (report PDFs, SOS messages). Servers
    # such as Vercel run on UTC, so this is set here rather than taken from the server.
    display_timezone: str = "Asia/Manila"

    # Site page the worker's tray opens for "Recalibrate".
    site_url: str = "http://localhost:5173"

    # Camera & engine. camera_index is only the default until the user picks a
    # camera on the calibration page (saved in device_settings_path).
    camera_index: int = 0
    device_settings_path: Path = STORAGE_DIR / "device_settings.json"
    face_model_path: Path = STORAGE_DIR / "face_landmarker.task"
    profiles_dir: Path = STORAGE_DIR / "calibration_profiles"
    # Geometric gaze sources need the screen's physical size and assume the
    # webcam sits centred just above its top edge (laptop or monitor-top
    # camera). Empty sizes are read from the display's EDID.
    screen_width_cm: float | None = Field(None, gt=0)
    screen_height_cm: float | None = Field(None, gt=0)
    camera_above_screen_cm: float = Field(0.8, ge=0)
    # Latest quick re-centre, kept per calibration profile.
    recenter_path: Path = STORAGE_DIR / "recenter.json"
    worker_pid_path: Path = STORAGE_DIR / "tracking_worker.pid"
    worker_log_path: Path = STORAGE_DIR / "tracking_worker.log"
    # Both-eye blink screenshots (team decision D2): <dir>/<user id>/<time>.png
    screenshots_dir: Path = STORAGE_DIR / "screenshots"
    # Capture backend and pixel format (see core/camera/capture.py). "auto"
    # and an empty FOURCC keep OpenCV's defaults; compare alternatives with
    # scripts/benchmark_gaze.py camera before changing them.
    camera_backend: Literal["auto", "msmf", "dshow"] = "auto"
    camera_fourcc: str = Field("", pattern=r"^([A-Z0-9]{4})?$")
    # Higher sizes give the pupil fit more pixels per eye; drivers that cannot
    # deliver one fall back to their nearest size (logged as "Camera N opened").
    camera_resolution: Literal["720p", "1080p", "1440p"] = "720p"
    refine_pupils: bool = True
    deep_gaze_enabled: bool = True
    low_power: bool = False

    # Worker behaviour
    auto_start_worker: bool = True
    cursor_smoothing: float = 0.25
    # Off by default: clicks come only from a deliberate left wink.
    dwell_click_enabled: bool = False
    # A left wink clicks. A user may turn it off only while dwell click is on
    # (Accessibility Settings, Phase 7); otherwise they could not click at all.
    blink_click_enabled: bool = True
    voice_guidance_enabled: bool = True
    dwell_ms: int = 700
    dwell_radius_px: int = 45
    dwell_cooldown_ms: int = 500
    blink_threshold: float = 0.18
    # How little eye travel reaches the left/right screen edge (see
    # core/gaze/edge_reach.py). Default only: the control bar's choice is saved
    # in device_settings_path and wins.
    edge_sensitivity: Literal["off", "low", "medium", "high"] = "medium"
    # Look at the top/bottom band for dwell_ms to scroll (app/workers/edge_scroll.py).
    # Separate from edge_sensitivity above, which only affects left/right reach.
    edge_scroll_enabled: bool = True
    edge_scroll_band: float = Field(0.08, gt=0, le=0.25)
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

    # Cursor navigation mode (see core/gaze/navigation.py). "steer": eyes move
    # the cursor; once the gaze rests it snaps to a nearby control and small
    # head movements fine-aim. "legacy" is the original stacked filters. Filter
    # values are One Euro parameters in Hz and screen pixels.
    gaze_mode: Literal["legacy", "raw", "filtered", "head", "assisted", "steer"] = "steer"
    gaze_filter_mincutoff: float = Field(0.8, gt=0)
    gaze_filter_beta: float = Field(0.01, ge=0)
    fixation_assist_enabled: bool = True
    fixation_assist_radius_px: float = Field(50.0, gt=0)

    # Floating camera preview with a line from the eyes to the cursor, the
    # recent cursor path and the raw gaze point; toggled from the control bar.
    camera_preview_enabled: bool = True

    # Gaze diagnostics: JSON stage/latency summaries in the worker log every
    # interval; the optional trace adds one JSON line per gaze frame.
    diagnostics_enabled: bool = False
    diagnostics_interval_s: float = Field(10.0, gt=0)
    diagnostics_trace_path: Path | None = None

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
