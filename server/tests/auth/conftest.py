import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import create_app
from app.config import get_settings
from app.models.calibration_record import CalibrationRecord
from app.models.system_log import SystemLog
from app.models.user import User
from app.services import auth_service
from app.services.password_hashing import hash_password

ADMIN_EMAIL = "admin@pdao.ph"
ADMIN_PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def fresh_throttle(monkeypatch):
    monkeypatch.setattr(auth_service, "throttle", auth_service.LoginThrottle())


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    settings = get_settings().model_copy(update={"profiles_dir": tmp_path})
    monkeypatch.setattr("app.api.routes.assistive.get_settings", lambda: settings)
    return tmp_path


@pytest.fixture
def api(profiles_dir):
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def make_user(test_database):
    def make(full_name="Ana Cruz", role="assistive_user", status="active", email=None,
             password=None):
        with test_database() as session:
            user = User(full_name=full_name, role=role, status=status, email=email,
                        password_hash=hash_password(password) if password else None)
            session.add(user)
            session.commit()
            return user.user_id
    return make


@pytest.fixture
def admin_id(make_user):
    return make_user("PDAO Admin", role="admin", email=ADMIN_EMAIL, password=ADMIN_PASSWORD)


@pytest.fixture
def signed_in_admin(api, admin_id):
    response = api.post("/api/auth/admin/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    return api


def add_calibration(factory, user_id, status="Successful", file_id=None, when=None,
                    accuracy="95.50"):
    with factory() as session:
        row = CalibrationRecord(user_id=user_id, profile_name="Desk", status=status,
                                profile_file_id=file_id, accuracy_score=accuracy)
        if when is not None:
            row.calibration_date = when
        session.add(row)
        session.commit()


def logs(factory, activity_type=None):
    with factory() as session:
        query = select(SystemLog).order_by(SystemLog.log_id)
        if activity_type:
            query = query.where(SystemLog.activity_type == activity_type)
        return session.scalars(query).all()
