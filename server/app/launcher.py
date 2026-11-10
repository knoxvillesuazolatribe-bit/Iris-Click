"""IrisClick Desktop launcher: what the IrisClick shortcut runs (launch_irisclick.pyw).

1. Starts the local server (FastAPI on 127.0.0.1:8000) with no console window, or
   reuses it. The server lets in the hosted IrisClick website (CORS_ORIGINS) and
   pages it opens (SITE_URL) are on that website.
2. Desktop mode (IRISCLICK_CLOUD_URL set, no DB_HOST): prepares the local database
   and keeps it in sync with the hosted server (app/desktop_sync/sync.py).
3. Starts eye tracking with the newest calibration (the existing POST
   /api/tracking/start), so a person can use their eyes from the first screen.
4. Opens the IrisClick website in a maximised Microsoft Edge app window (Edge asks
   once to allow the site to reach this PC; speech-to-text works there).
5. Shows a tray icon: Open IrisClick, Start with Windows, Quit IrisClick.
If the server cannot start, a large message with Try again appears and is spoken.

``--stop`` stops eye tracking and the server (used by the uninstaller).
Nothing here changes the calibration, the tracking worker or its services.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = SERVER_DIR / "app" / "storage"
HOST = "127.0.0.1"
DEFAULT_PORT = 8000
START_TIMEOUT_S = 90.0
POLL_S = 0.5
SERVER_LOG = "irisclick_server.log"
SERVER_PID = "irisclick_server.pid"
LAUNCHER_PID = "irisclick_launcher.pid"
LAUNCHER_LOG = "irisclick_launcher.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "IrisClick Desktop"

WELCOME_TRACKING = "IrisClick is ready. Look at a button and wink your left eye to choose."
WELCOME_NO_CALIBRATION = "IrisClick is ready. A helper needs to calibrate the eye tracking first."
START_FAILED = "IrisClick could not start. Choose Try again, or ask a helper."

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

logger = logging.getLogger("irisclick.launcher")


# --- where things are ---------------------------------------------------------------------------

def edge_candidates() -> list[Path]:
    places = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
              os.environ.get("ProgramFiles", r"C:\Program Files"),
              os.environ.get("LOCALAPPDATA", "")]
    return [Path(p) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for p in places if p]


def find_edge(candidates: list[Path] | None = None) -> Path | None:
    return next((p for p in (candidates or edge_candidates()) if p.is_file()), None)


def website_url() -> str:
    """The hosted IrisClick website (IRISCLICK_CLOUD_URL), else the local site (SITE_URL)."""
    from app.api.routes.desktop_link import cloud_url
    from app.config import get_settings
    return cloud_url() or get_settings().site_url.rstrip("/")


def base_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def console_python(executable: str | Path | None = None) -> Path:
    """python.exe beside the running interpreter (the shortcut runs pythonw.exe)."""
    exe = Path(executable or sys.executable)
    console = exe.with_name("python.exe")
    return console if console.is_file() else exe


def server_command(port: int, executable: str | Path | None = None) -> list[str]:
    return [str(console_python(executable)), "-m", "uvicorn", "app.api.main:app",
            "--host", HOST, "--port", str(port)]


def server_env(port: int, website: str, edge: Path | None, cors: list[str],
               base: dict | None = None) -> dict:
    env = dict(os.environ if base is None else base)
    env["HOST"] = HOST
    env["PORT"] = str(port)
    # Pages the worker opens (tray "Recalibrate", Home) are on the IrisClick website.
    env["SITE_URL"] = website
    # The website may use this desktop app (app/api/origin_guard.py and CORS).
    origins = list(dict.fromkeys([*cors, website.rstrip("/")]))
    env["CORS_ORIGINS"] = json.dumps(origins)
    if edge is not None:
        env["BROWSER"] = str(edge)  # Python's webbrowser (tray Recalibrate) opens Edge
    return env


# --- the local server ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 2.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local address only
        return response.status, response.read().decode("utf-8", "replace")


def _post(url: str, timeout: float = 20.0) -> tuple[int, str]:
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local address only
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def server_ready(port: int, get: Callable = _get) -> bool:
    try:
        status, body = get(f"{base_url(port)}/api/health")
        return status == 200 and json.loads(body).get("status") == "ok"
    except (OSError, ValueError):
        return False


def start_server(port: int, env: dict, storage: Path = STORAGE_DIR,
                 popen: Callable = subprocess.Popen) -> subprocess.Popen:
    storage.mkdir(parents=True, exist_ok=True)
    log = open(storage / SERVER_LOG, "ab")  # noqa: SIM115 - handed to the child process
    process = popen(server_command(port), cwd=SERVER_DIR, env=env, stdout=log,
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
    (storage / SERVER_PID).write_text(str(process.pid), encoding="utf-8")
    logger.info("Server started (pid %s, port %s)", process.pid, port)
    return process


def wait_until_ready(port: int, process=None, timeout: float = START_TIMEOUT_S,
                     ready: Callable[[int], bool] = server_ready, sleep: Callable = time.sleep,
                     clock: Callable = time.monotonic, tick: Callable[[], None] = lambda: None) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if ready(port):
            return True
        if process is not None and process.poll() is not None:
            logger.warning("Server exited with code %s", process.poll())
            return False
        tick()
        sleep(POLL_S)
    return False


def start_tracking(port: int, post: Callable = _post) -> bool:
    """True when eye tracking runs; False when there is no calibration yet (409) or it failed."""
    try:
        status, body = post(f"{base_url(port)}/api/tracking/start")
    except OSError as exc:
        logger.warning("Eye tracking could not start: %s", exc)
        return False
    if status != 200:
        logger.info("Eye tracking not started (%s): %s", status, body[:200])
        return False
    try:
        return bool(json.loads(body).get("running"))
    except ValueError:
        return False


def open_window(url: str, edge: Path | None, popen: Callable = subprocess.Popen,
                browser: Callable = webbrowser.open) -> None:
    if edge is not None:
        popen([str(edge), f"--app={url}/", "--start-maximized"])
    else:
        browser(f"{url}/")


def say(text: str) -> None:
    """Speaks with the offline Windows voice; silent if voice guidance is off or unavailable."""
    try:
        from app.config import get_settings
        if not get_settings().voice_guidance_enabled:
            return
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.say(text)
        engine.runAndWait()
    except Exception:  # noqa: BLE001 - speech is a courtesy, never a reason to fail
        logger.debug("Welcome not spoken", exc_info=True)


def stop(port: int, storage: Path = STORAGE_DIR, post: Callable = _post,
         kill: Callable[[int], None] | None = None) -> None:
    """Stops eye tracking, then the server this launcher started."""
    try:
        post(f"{base_url(port)}/api/tracking/stop")
    except OSError:
        pass
    for name in (SERVER_PID, LAUNCHER_PID):  # the server, then the tray launcher
        pid_file = storage / name
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if pid != os.getpid():
            (kill or _kill_tree)(pid)
        pid_file.unlink(missing_ok=True)


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                   creationflags=CREATE_NO_WINDOW, check=False)


# --- Start with Windows (current user only, no admin rights) -------------------------------------

def launch_command() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.is_file() else Path(sys.executable)
    return f'"{exe}" "{SERVER_DIR / "launch_irisclick.pyw"}"'


def starts_with_windows(registry=None) -> bool:
    try:
        reg = registry or __import__("winreg")
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.QueryValueEx(key, RUN_NAME)
            return True
    except OSError:
        return False


def set_start_with_windows(on: bool, registry=None) -> None:
    reg = registry or __import__("winreg")
    with reg.CreateKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            reg.SetValueEx(key, RUN_NAME, 0, reg.REG_SZ, launch_command())
        else:
            try:
                reg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


# --- windows the person sees ---------------------------------------------------------------------

class Splash:
    """A large "Starting IrisClick…" window while the server starts (tkinter)."""

    def __init__(self):
        self.root = None
        try:
            import tkinter as tk
            root = tk.Tk()
            root.title("IrisClick")
            root.configure(bg="#f3f7f7", padx=48, pady=36)
            root.attributes("-topmost", True)
            tk.Label(root, text="Starting IrisClick…", font=("Segoe UI", 28, "bold"),
                     bg="#f3f7f7", fg="#0f5c55").pack()
            tk.Label(root, text="Please wait a moment.", font=("Segoe UI", 18), bg="#f3f7f7").pack(pady=(12, 0))
            root.update_idletasks()
            x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
            y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
            root.geometry(f"+{x}+{y}")
            self.root = root
        except Exception:  # noqa: BLE001 - no splash is fine
            self.root = None

    def tick(self):
        if self.root is not None:
            try:
                self.root.update()
            except Exception:  # noqa: BLE001
                self.root = None

    def close(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except Exception:  # noqa: BLE001
                pass
            self.root = None


def ask_try_again(message: str) -> bool:
    """A large message with Try again / Close buttons; True for Try again."""
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001
        return False
    choice = {"retry": False}
    root = tk.Tk()
    root.title("IrisClick")
    root.configure(bg="white", padx=48, pady=36)
    root.attributes("-topmost", True)
    tk.Label(root, text=message, font=("Segoe UI", 22), wraplength=720, justify="left",
             bg="white", fg="#8a1c1c").pack(pady=(0, 28))
    row = tk.Frame(root, bg="white")
    row.pack()

    def pick(retry: bool):
        choice["retry"] = retry
        root.destroy()

    tk.Button(row, text="Try again", font=("Segoe UI", 22, "bold"), width=12, height=2, bg="#0f766e",
              fg="white", command=lambda: pick(True)).pack(side="left", padx=12)
    tk.Button(row, text="Close", font=("Segoe UI", 22), width=10, height=2,
              command=lambda: pick(False)).pack(side="left", padx=12)
    root.mainloop()
    return choice["retry"]


def tray_image(size: int = 64):
    """An eye in a teal circle (Pillow, already an IrisClick dependency)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.ellipse((2 * s, 2 * s, 62 * s, 62 * s), fill=(15, 118, 110, 255))
    d.chord((9 * s, 18 * s, 55 * s, 46 * s), 0, 360, fill=(255, 255, 255, 255))
    d.ellipse((23 * s, 20 * s, 41 * s, 38 * s), fill=(17, 24, 39, 255))
    d.ellipse((28 * s, 25 * s, 36 * s, 33 * s), fill=(250, 204, 21, 255))
    return img


def first_run_calibration(port: int) -> bool:
    """Desktop calibration hook: on a first run (no calibration yet) opens the calibration
    window, only in desktop mode with someone linked (app/desktop_calibration/hooks.py)."""
    try:
        from app.desktop_calibration.hooks import first_run_calibration as hook
        return hook(port)
    except Exception:  # noqa: BLE001 - never stops the launcher
        return False


def open_calibration_window() -> None:
    """Desktop calibration hook: tray "Calibrate here"."""
    try:
        from app.desktop_calibration.hooks import open_window
        open_window("tray")
    except Exception:  # noqa: BLE001
        pass


def run_tray(open_site: Callable[[], None], quit_all: Callable[[], None]) -> None:
    """Blocks until Quit; without pystray (not Windows) it just waits for Ctrl+C."""
    try:
        import pystray
    except Exception:  # noqa: BLE001
        threading.Event().wait()
        return

    def toggle_startup(icon, item):
        set_start_with_windows(not starts_with_windows())

    def quit_clicked(icon, item):
        quit_all()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open IrisClick", lambda icon, item: open_site(), default=True),
        pystray.MenuItem("Calibrate here", lambda icon, item: open_calibration_window()),
        pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda item: starts_with_windows()),
        pystray.MenuItem("Quit IrisClick", quit_clicked),
    )
    pystray.Icon("irisclick-desktop", tray_image(), "IrisClick Desktop", menu).run()


# --- start-up ------------------------------------------------------------------------------------

def run(port: int, *, window: bool = True, voice: bool = True, tracking: bool = True, tray: bool = True,
        ready: Callable[[int], bool] = server_ready, launch: Callable = start_server,
        wait: Callable = wait_until_ready, track: Callable = start_tracking,
        show: Callable = open_window, speak: Callable[[str], None] = say,
        retry: Callable[[str], bool] = ask_try_again, splash_factory: Callable = Splash,
        sync_loop: Callable | None = None, tray_loop: Callable = run_tray,
        settings_cors: Callable[[], list[str]] | None = None) -> int:
    edge = find_edge()
    website = website_url()
    already_running = ready(port)
    while not already_running:
        splash = splash_factory() if window else None
        try:
            cors = settings_cors() if settings_cors else _settings_cors()
            process = launch(port, server_env(port, website, edge, cors))
            if wait(port, process, tick=splash.tick if splash else (lambda: None)):
                break
        except OSError as exc:
            logger.exception("Server could not start: %s", exc)
        finally:
            if splash:
                splash.close()
        logger.warning(START_FAILED)
        if voice:
            speak(START_FAILED)
        if not retry(START_FAILED):
            return 1
    running = track(port) if tracking else False
    if tracking and not running:
        first_run_calibration(port)  # desktop calibration: desktop mode + someone linked only
    if window:
        show(website, edge)
    if voice:
        speak(WELCOME_TRACKING if running else WELCOME_NO_CALIBRATION)
    if already_running or not tray:
        return 0  # the first launcher keeps the tray icon and the sync running
    stop_sync = threading.Event()
    if sync_loop is not None:
        threading.Thread(target=sync_loop, args=(stop_sync,), name="desktop-sync", daemon=True).start()

    def quit_all():
        stop_sync.set()
        stop(port)

    pid_file = STORAGE_DIR / LAUNCHER_PID
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        tray_loop(lambda: show(website, edge), quit_all)
    finally:
        stop_sync.set()
        pid_file.unlink(missing_ok=True)
    return 0


def _settings_cors() -> list[str]:
    from app.config import get_settings
    return list(get_settings().cors_origins)


def desktop_sync_loop() -> Callable | None:
    """The sync loop in desktop mode (local database ready first), else None."""
    from app.desktop_sync import sync
    if not sync.desktop_mode():
        return None
    sync.prepare_local_db()
    return sync.run_forever


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start or stop IrisClick Desktop.")
    parser.add_argument("--stop", action="store_true", help="stop eye tracking and the server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("IRISCLICK_PORT", DEFAULT_PORT)))
    parser.add_argument("--no-window", action="store_true", help="do not open the IrisClick window")
    parser.add_argument("--no-voice", action="store_true", help="do not speak")
    parser.add_argument("--no-tracking", action="store_true", help="do not start eye tracking")
    parser.add_argument("--no-tray", action="store_true", help="exit after start-up (no tray icon)")
    args = parser.parse_args(argv)

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=STORAGE_DIR / LAUNCHER_LOG, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.stop:
        stop(args.port)
        return 0
    try:
        loop = desktop_sync_loop()
    except Exception:  # noqa: BLE001 - eye tracking must start even if sync cannot
        logger.exception("Desktop sync not started")
        loop = None
    return run(args.port, window=not args.no_window, voice=not args.no_voice,
               tracking=not args.no_tracking, tray=not args.no_tray, sync_loop=loop)
