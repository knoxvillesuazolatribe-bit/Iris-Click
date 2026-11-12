"""Site access code for the online copy.

On the PC, assistive users sign in by choosing their name tile. On the
internet that would let anyone sign in as them, so the online copy first asks
for an access code that PDAO staff and caregivers know. A device that entered
it keeps a cookie; changing IRISCLICK_ACCESS_CODE in Vercel signs every device
out. Without a code set (or one shorter than MIN_CODE_LENGTH) the online copy
stays closed.
"""

import hashlib
import hmac
import logging
import os
import threading
import time
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.accounts import open_site

logger = logging.getLogger("irisclick.cloud.access")

CODE_ENV = "IRISCLICK_ACCESS_CODE"
MIN_CODE_LENGTH = 8
COOKIE_NAME = "irisclick_access"
COOKIE_MAX_AGE_S = 180 * 24 * 3600
# Wrong codes: a short wait each time, and a pause after too many from one address.
WRONG_CODE_DELAY_S = 1.0
MAX_WRONG = 10
WRONG_WINDOW_S = 15 * 60

ACCESS_REQUIRED = "Enter the IrisClick access code first."
NOT_SET_UP = "The online copy of IrisClick is not set up yet. Ask the PDAO office."
WRONG_CODE = "That access code is not right. Please try again."
TOO_MANY = "Too many wrong codes. Please wait 15 minutes and try again."

router = APIRouter(prefix="/cloud", tags=["online copy"])


def configured_code() -> str | None:
    code = os.environ.get(CODE_ENV, "").strip()
    return code if len(code) >= MIN_CODE_LENGTH else None


def token_for(code: str) -> str:
    return hmac.new(code.encode("utf-8"), b"irisclick-online-access-v1", hashlib.sha256).hexdigest()


def has_access(request: Request) -> bool:
    code = configured_code()
    cookie = request.cookies.get(COOKIE_NAME, "")
    return code is not None and hmac.compare_digest(cookie, token_for(code))


def is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (forwarded or request.url.scheme) == "https"


class _WrongCodes:
    """Wrong attempts per address on this server instance."""

    def __init__(self):
        self._lock = threading.Lock()
        self._seen: dict[str, list[float]] = {}

    def blocked(self, address: str, now: float) -> bool:
        with self._lock:
            recent = [t for t in self._seen.get(address, []) if now - t < WRONG_WINDOW_S]
            self._seen[address] = recent
            return len(recent) >= MAX_WRONG

    def add(self, address: str, now: float) -> None:
        with self._lock:
            self._seen.setdefault(address, []).append(now)

    def clear(self, address: str) -> None:
        with self._lock:
            self._seen.pop(address, None)


wrong_codes = _WrongCodes()
sleep: Callable[[float], None] = time.sleep  # replaced in tests


def client_address(request: Request) -> str:
    # Vercel sets x-real-ip / x-forwarded-for to the visitor's address.
    forwarded = (request.headers.get("x-real-ip")
                 or request.headers.get("x-forwarded-for", "").split(",")[0]).strip()
    return forwarded or (request.client.host if request.client else "unknown")


class AccessStatus(BaseModel):
    online_copy: bool = True
    ready: bool
    access: bool


class AccessRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


@router.get("/status", response_model=AccessStatus)
def status(request: Request) -> AccessStatus:
    if open_site.open_without_code():  # D1: accounts with PINs, no access code set
        return AccessStatus(ready=True, access=True)
    return AccessStatus(ready=configured_code() is not None, access=has_access(request))


@router.post("/access", response_model=AccessStatus)
def enter_code(body: AccessRequest, request: Request, response: Response) -> AccessStatus:
    code = configured_code()
    if code is None:
        raise HTTPException(status_code=503, detail=NOT_SET_UP)
    address = client_address(request)
    now = time.monotonic()
    if wrong_codes.blocked(address, now):
        raise HTTPException(status_code=429, detail=TOO_MANY)
    if not hmac.compare_digest(body.code.strip().encode("utf-8"), code.encode("utf-8")):
        wrong_codes.add(address, now)
        logger.warning("Wrong online access code from %s", address)
        sleep(WRONG_CODE_DELAY_S)
        raise HTTPException(status_code=401, detail=WRONG_CODE)
    wrong_codes.clear(address)
    response.set_cookie(COOKIE_NAME, token_for(code), max_age=COOKIE_MAX_AGE_S, path="/",
                        httponly=True, samesite="lax", secure=is_https(request))
    logger.info("Online access code entered from %s", address)
    return AccessStatus(ready=True, access=True)


def gate(api_prefix: str):
    """Middleware: every API request needs the access cookie, except these."""
    open_paths = {f"{api_prefix}/cloud/status", f"{api_prefix}/cloud/access", f"{api_prefix}/health",
                  f"{api_prefix}/signin/mode",
                  f"{api_prefix}/cloud/computers/claim",
                  *(f"{api_prefix}/desktop/{p}" for p in ("session", "profile", "calibrations", "logs"))}
    # The desktop routes are protected by signed tokens instead (app/cloud/desktop.py, desktop_api.py).

    async def middleware(request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if request.method == "OPTIONS" or not path.startswith(api_prefix) or path in open_paths:
            return await call_next(request)
        if configured_code() is None:
            if open_site.open_without_code():  # D1
                return await call_next(request)
            return JSONResponse({"detail": NOT_SET_UP, "code": "not_set_up"}, status_code=503)
        if not has_access(request):
            return JSONResponse({"detail": ACCESS_REQUIRED, "code": "access_required"},
                                status_code=401)
        return await call_next(request)

    return middleware
