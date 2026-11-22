import numpy as np
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(7)


@pytest.fixture(autouse=True)
def _restore_pc_app_checks(monkeypatch):
    """The online copy (app/cloud/main.py assume_pc_apps) trusts the PC's program list by
    replacing two module functions; restore them after every test so PC tests see the real ones."""
    from app.services import user_apps_service
    monkeypatch.setattr(user_apps_service, "_scanned", user_apps_service._scanned)
    monkeypatch.setattr(user_apps_service, "file_exists", user_apps_service.file_exists)


@pytest.fixture(autouse=True)
def _setup_codes_on(monkeypatch):
    """PDAO setup codes are off by default (SETUP_CODES); the existing tests cover them switched on.
    tests/accounts/test_setup_codes_off.py checks the default, off."""
    monkeypatch.setenv("SETUP_CODES", "on")
