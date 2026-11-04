r"""Creates the first IrisClick administrator from server\.env. Run from server\:

    .venv\Scripts\python scripts\create_admin.py

Reads ADMIN_EMAIL, ADMIN_PASSWORD (at least 12 characters) and ADMIN_FULL_NAME.
If an account with that email already exists, nothing is changed. Afterwards,
delete ADMIN_PASSWORD from server\.env: the database keeps only its hash.
Needs the database tables (alembic upgrade head) first.
"""

import sys
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from sqlalchemy import select  # noqa: E402

from app.models import database  # noqa: E402
from app.models.user import ROLE_ADMIN, User  # noqa: E402
from app.services.auth_service import normalize_email  # noqa: E402
from app.services.password_hashing import (  # noqa: E402
    MIN_ADMIN_PASSWORD_LENGTH,
    hash_password,
)
from app.services.system_log_service import log_activity  # noqa: E402


class AdminSeed(BaseSettings):
    model_config = SettingsConfigDict(env_file=SERVER_DIR / ".env", env_file_encoding="utf-8",
                                      extra="ignore")

    admin_email: str = ""
    admin_password: SecretStr = SecretStr("")
    admin_full_name: str = "PDAO Administrator"


def create_admin(session_factory, email: str, password: str, full_name: str) -> str:
    """Create the admin; returns a message. Raises ValueError for bad input."""
    email = normalize_email(email)
    full_name = full_name.strip()
    if "@" not in email:
        raise ValueError("Set ADMIN_EMAIL in server\\.env to a valid email address.")
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(f"Set ADMIN_PASSWORD in server\\.env (at least "
                         f"{MIN_ADMIN_PASSWORD_LENGTH} characters).")
    if not full_name:
        raise ValueError("Set ADMIN_FULL_NAME in server\\.env.")
    with session_factory() as session:
        if session.scalars(select(User).where(User.email == email)).first() is not None:
            return f"An account for {email} already exists; nothing was changed."
        admin = User(full_name=full_name, email=email, password_hash=hash_password(password),
                     role=ROLE_ADMIN)
        session.add(admin)
        session.flush()
        log_activity("user_created", f"Administrator {full_name} created by setup script",
                     admin.user_id, session=session)
        session.commit()
    return (f"Administrator {email} created. Now delete ADMIN_PASSWORD from server\\.env "
            "(the database keeps only its hash).")


def main() -> int:
    seed = AdminSeed()
    try:
        print(create_admin(database.get_session_factory(), seed.admin_email,
                           seed.admin_password.get_secret_value(), seed.admin_full_name))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
