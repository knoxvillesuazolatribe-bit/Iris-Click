from app.config import get_settings


def _settings(**overrides):
    return get_settings().model_copy(update=overrides)


def test_postgres_url_escapes_password_and_requires_ssl():
    settings = _settings(db_host="db.example.com", db_user="postgres.ref",
                         db_password=type(get_settings().db_password)("p@ss:w/rd%"))

    url = settings.database_url

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:w/rd%"
    assert url.query["sslmode"] == "require"
    assert "p@ss" not in str(url)


def test_empty_host_falls_back_to_sqlite():
    settings = _settings(db_host="")

    assert not settings.uses_postgres
    assert settings.database_url.drivername == "sqlite"
