r"""Changes an IrisClick administrator's password. Run from server\:

    ..\.venv\Scripts\python scripts\reset_admin_password.py [admin email]

Without an email it uses ADMIN_EMAIL from server\.env. The new password is
typed twice on screen (hidden, never stored in a file) and must be at least
12 characters. The database keeps only its Argon2 hash. The admin's open
sign-ins are ended, and a "password_changed" row is written to System Logs.
"""

import getpass
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from sqlalchemy import select  # noqa: E402

from app.models import database  # noqa: E402
from app.models.user import ROLE_ADMIN, User  # noqa: E402
from app.services import session_service  # noqa: E402
from app.services.auth_service import normalize_email  # noqa: E402
from app.services.password_hashing import (  # noqa: E402
    MIN_ADMIN_PASSWORD_LENGTH,
    hash_password,
    verify_password,
)
from app.services.system_log_service import log_activity  # noqa: E402


class AdminEmail(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVER_DIR / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    admin_email: str = ""


def reset_admin_password(session_factory, email: str, password: str) -> str:
    """Set a new password for the admin ``email``; returns a message. Raises ValueError."""
    email = normalize_email(email)
    if "@" not in email:
        raise ValueError("Give the administrator's email address.")
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(f"The new password must be at least {MIN_ADMIN_PASSWORD_LENGTH} "
                         "characters.")
    with session_factory() as session:
        admin = session.scalars(select(User).where(User.email == email,
                                                   User.role == ROLE_ADMIN)).first()
        if admin is None:
            raise ValueError(f"No administrator account uses {email}.")
        if verify_password(admin.password_hash, password):
            raise ValueError("The new password is the same as the old one. Choose another.")
        admin.password_hash = hash_password(password)
        ended = session_service.revoke_all_for_user(session, admin.user_id)
        log_activity("password_changed", f"Administrator {admin.full_name} password changed "
                     "by reset script", admin.user_id, session=session)
        session.commit()
    return (f"Password changed for {email}. {ended} open sign-in(s) ended; sign in again "
            "with the new password.")


def ask_password(prompt=getpass.getpass) -> str:
    first = prompt("New admin password (hidden): ")
    if prompt("Type it again: ") != first:
        raise ValueError("The two passwords do not match. Nothing was changed.")
    return first


def main(argv: list[str]) -> int:
    email = argv[0] if argv else AdminEmail().admin_email
    if not email:
        print("Give the admin email: scripts\\reset_admin_password.py admin@example.com",
              file=sys.stderr)
        return 2
    try:
        print(reset_admin_password(database.get_session_factory(), email, ask_password()))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
