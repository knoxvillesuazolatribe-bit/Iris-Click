"""Admin user management (Phase 2 list/create, Phase 8 detail, status, settings, contacts)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.accounts.guards import PEOPLE_CREATE, PEOPLE_SET, legacy_only
from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.config import get_settings
from app.models.user import ROLE_ASSISTIVE_USER, User
from app.schemas.accessibility import AccessibilitySettingsRead, AccessibilitySettingsWrite
from app.schemas.admin import AdminUserDetail, AdminUserRow, AdminUserUpdate, StatusUpdate
from app.schemas.auth import AdminUserRead, AssistiveCreateRequest
from app.schemas.sos import SosContactRead, SosContactWrite
from app.services import accessibility_service, admin_service, sos_service
from app.services.accessibility_service import FriendlySettings, SettingsError
from app.services.admin_service import AdminError
from app.services.sos_service import SosError
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/admin/users", tags=["admin"], route_class=DatabaseSafeRoute)


def _fail(exc: AdminError | SettingsError | SosError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _target(db: Session, user_id: int) -> User:
    try:
        return admin_service.assistive_user(db, user_id)
    except AdminError as exc:
        _fail(exc)


def _row(db: Session, user: User) -> AdminUserRow:
    summary = admin_service.calibration_summary(db, user.user_id)
    return AdminUserRow(**AdminUserRead.model_validate(user).model_dump(), **asdict(summary))


def _settings(db: Session, user: User) -> AccessibilitySettingsRead:
    base = get_settings()
    values, is_default = accessibility_service.current(db, user, base)
    return AccessibilitySettingsRead(
        **asdict(values), is_default=is_default,
        defaults=AccessibilitySettingsWrite(**asdict(accessibility_service.standard(db, base))))


@router.get("", response_model=list[AdminUserRow])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return [AdminUserRow(**AdminUserRead.model_validate(user).model_dump(), **asdict(summary))
            for user, summary in admin_service.list_users(db)]


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(legacy_only(PEOPLE_CREATE))])
def create_assistive_user(body: AssistiveCreateRequest, db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)) -> AdminUserRead:
    user = User(full_name=body.full_name, role=ROLE_ASSISTIVE_USER,
                address=body.address or None, barangay=body.barangay or None)
    db.add(user)
    db.flush()
    log_activity("user_created", f"{admin.full_name} created assistive user {user.full_name}",
                 admin.user_id, session=db)
    db.commit()
    return AdminUserRead.model_validate(user)


@router.get("/{user_id}", response_model=AdminUserDetail)
def user_detail(user_id: int, db: Session = Depends(get_db),
                _admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    return AdminUserDetail(
        user=_row(db, user), sos_location=sos_service.location_text(user),
        settings=_settings(db, user),
        contacts=[SosContactRead.model_validate(c) for c in sos_service.list_contacts(db, user)])


@router.put("/{user_id}", response_model=AdminUserRow)
def update_user(user_id: int, body: AdminUserUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    admin_service.update_profile(db, admin, user, body.full_name, body.address, body.barangay)
    return _row(db, user)


@router.post("/{user_id}/status", response_model=AdminUserRow)
def set_status(user_id: int, body: StatusUpdate, db: Session = Depends(get_db),
               admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    try:
        admin_service.set_status(db, admin, user, body.status)
    except AdminError as exc:
        _fail(exc)
    return _row(db, user)


# --- Accessibility settings (D7: editable by the admin too) -----------------------------

@router.get("/{user_id}/settings", response_model=AccessibilitySettingsRead)
def read_user_settings(user_id: int, db: Session = Depends(get_db),
                       _admin: User = Depends(require_admin)):
    return _settings(db, _target(db, user_id))


@router.put("/{user_id}/settings", response_model=AccessibilitySettingsRead,
            dependencies=[Depends(legacy_only(PEOPLE_SET))])
def save_user_settings(user_id: int, body: AccessibilitySettingsWrite,
                       db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    try:
        accessibility_service.save(db, user, FriendlySettings(**body.model_dump()), saved_by=admin)
    except SettingsError as exc:
        _fail(exc)
    return _settings(db, user)


@router.post("/{user_id}/settings/reset", response_model=AccessibilitySettingsRead,
             dependencies=[Depends(legacy_only(PEOPLE_SET))])
def reset_user_settings(user_id: int, db: Session = Depends(get_db),
                        admin: User = Depends(require_admin)):
    user = _target(db, user_id)
    accessibility_service.reset(db, user, saved_by=admin)
    return _settings(db, user)


# --- Emergency contacts ------------------------------------------------------------------

@router.post("/{user_id}/contacts", response_model=SosContactRead, status_code=201)
def add_contact(user_id: int, body: SosContactWrite, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    try:
        return SosContactRead.model_validate(
            sos_service.add_contact(db, _target(db, user_id), body.model_dump(), actor=admin))
    except SosError as exc:
        _fail(exc)


@router.put("/{user_id}/contacts/{contact_id}", response_model=SosContactRead)
def update_contact(user_id: int, contact_id: int, body: SosContactWrite,
                   db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return SosContactRead.model_validate(sos_service.update_contact(
            db, _target(db, user_id), contact_id, body.model_dump(), actor=admin))
    except SosError as exc:
        _fail(exc)


@router.delete("/{user_id}/contacts/{contact_id}", status_code=204)
def delete_contact(user_id: int, contact_id: int, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    try:
        sos_service.delete_contact(db, _target(db, user_id), contact_id, actor=admin)
    except SosError as exc:
        _fail(exc)
    return Response(status_code=204)
