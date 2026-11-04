"""Minimal user management so the name tiles have users (full module: Phase 8)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DatabaseSafeRoute, get_db, require_admin
from app.models.user import ROLE_ASSISTIVE_USER, User
from app.schemas.auth import AdminUserRead, AssistiveCreateRequest
from app.services.system_log_service import log_activity

router = APIRouter(prefix="/admin/users", tags=["admin"], route_class=DatabaseSafeRoute)


@router.get("", response_model=list[AdminUserRead])
def list_users(db: Session = Depends(get_db),
               _admin: User = Depends(require_admin)) -> list[AdminUserRead]:
    users = db.scalars(select(User).order_by(User.role, User.full_name, User.user_id)).all()
    return [AdminUserRead.model_validate(user) for user in users]


@router.post("", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
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
