"""Admin settings (Phase 8): global accessibility defaults, system and app name.

Email credentials stay in server/.env (secrets never leave it); this only
shows whether email is set up and sends a real test email.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.accounts import sms
from app.accounts.guards import NO_GLOBAL_DEFAULTS, legacy_only
from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.config import get_settings
from app.models.user import User
from app.schemas.accessibility import AccessibilitySettingsWrite
from app.schemas.admin import (
    AppInfoRead,
    AppNameUpdate,
    EmailStatus,
    GlobalDefaultsRead,
    SystemRead,
    TestEmailRequest,
    TestResult,
)
from app.services import accessibility_service, system_settings_service
from app.services.accessibility_service import FriendlySettings, SettingsError
from app.services.sos_delivery import DeliveryError, EmailSender
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/admin/settings", tags=["admin"], route_class=DatabaseSafeRoute)
public = APIRouter(tags=["app"], route_class=DatabaseSafeRoute)


@public.get("/app-info", response_model=AppInfoRead)
def app_info(db: Session = Depends(get_db)):
    """The app name for the sign-in screen and tab title (no sign-in needed)."""
    return AppInfoRead(app_name=system_settings_service.app_name(db, get_settings()))


# --- Global accessibility defaults ---------------------------------------------------------

def _defaults(db: Session) -> GlobalDefaultsRead:
    env = get_settings()
    return GlobalDefaultsRead(
        **asdict(accessibility_service.standard(db, env)),
        is_default=not system_settings_service.has_global_defaults(db),
        env_defaults=AccessibilitySettingsWrite(**asdict(accessibility_service.defaults(env))))


@router.get("/defaults", response_model=GlobalDefaultsRead)
def read_defaults(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return _defaults(db)


@router.put("/defaults", response_model=GlobalDefaultsRead,
            dependencies=[Depends(legacy_only(NO_GLOBAL_DEFAULTS))])
def save_defaults(body: AccessibilitySettingsWrite, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    try:
        accessibility_service.save_global(db, FriendlySettings(**body.model_dump()), admin)
    except SettingsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _defaults(db)


@router.post("/defaults/reset", response_model=GlobalDefaultsRead,
             dependencies=[Depends(legacy_only(NO_GLOBAL_DEFAULTS))])
def reset_defaults(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    accessibility_service.reset_global(db, admin)
    return _defaults(db)


# --- System ----------------------------------------------------------------------------------

def _system(db: Session) -> SystemRead:
    env = get_settings()
    sender = EmailSender(env)
    return SystemRead(
        app_name=system_settings_service.app_name(db, env), app_name_default=env.app_name,
        email=EmailStatus(configured=sender.configured(), host=env.smtp_host or None,
                          port=env.smtp_port, security=env.smtp_security,
                          from_address=sender.from_address or None),
        sms_configured=sms.configured())


@router.get("/system", response_model=SystemRead)
def read_system(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return _system(db)


@router.put("/system/app-name", response_model=SystemRead)
def save_app_name(body: AppNameUpdate, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    row = system_settings_service.row_for_update(db)
    row.app_name = body.app_name or None
    row.updated_by = admin.user_id
    name = body.app_name or get_settings().app_name
    log_activity("app_name_updated", f"{admin.full_name} set the app name to \"{name}\"",
                 admin.user_id, session=db)
    db.commit()
    return _system(db)


@router.post("/system/test-email", response_model=TestResult)
def test_email(body: TestEmailRequest, db: Session = Depends(get_db),
               admin: User = Depends(require_admin)):
    """Sends a real email and reports exactly what happened (never a fake success)."""
    name = system_settings_service.app_name(db, get_settings())
    try:
        EmailSender(get_settings()).send(
            body.to, f"{name} test email",
            f"This is a test email from {name}.\n\nIf you received it, Emergency SOS "
            f"emails can be sent from this computer.\n\nSent by {admin.full_name}.")
        result = TestResult(sent=True, detail=f"Test email sent to {body.to}. Check that inbox "
                                              "(and its Spam folder).")
    except DeliveryError as exc:
        result = TestResult(sent=False, detail=exc.message)
    log_activity("email_test", f"{admin.full_name} sent a test email to {body.to}: "
                 + ("sent" if result.sent else f"failed ({result.detail})"),
                 admin.user_id, session=db)
    db.commit()
    return result


SMS_TEST_NOT_SET_UP = ("No SMS was sent: SMS sending is not set up yet. A paid SMS gateway "
                       "(for example Semaphore) has to be connected first.")


@router.post("/system/test-sms", response_model=TestResult)
def test_sms(_admin: User = Depends(require_admin)):
    if not sms.configured():
        return TestResult(sent=False, detail=SMS_TEST_NOT_SET_UP)
    lock = sms.only_to()  # extension: Semaphore (file 07, Phase 5); tests go only to SMS_ONLY_TO
    if not lock:
        return TestResult(sent=False, detail="Set SMS_ONLY_TO in server/.env to the number that gets test texts.")
    try:
        sms.send(lock[0], "IrisClick test message: SMS sending works.")
    except sms.SmsError:
        return TestResult(sent=False, detail="Semaphore did not send the text. Check the API key and the credits.")
    return TestResult(sent=True, detail="Test text sent to the SMS_ONLY_TO number.")
