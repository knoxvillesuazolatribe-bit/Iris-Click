"""Account tiles show the latest successful calibration's accuracy (Gate 3 note A2)."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.accounts import devices, service
from app.models.account_models import Device
from app.models.calibration_record import CalibrationRecord
from app.models.timestamps import utc_now

PC = "T" * 43
PIN = "482913"


def _add(db, user_id, score, status, when):
    db.add(CalibrationRecord(user_id=user_id, profile_name="test", accuracy_score=score, status=status,
                             calibration_date=when))
    db.commit()


def test_a_tile_has_no_accuracy_before_the_first_calibration(test_database):
    with test_database() as db:
        device = devices.remember_device(db, PC)
        service.sign_up(db, device, consent=True, username="mari_lapu", mobile_number="09178082488",
                        pin=PIN, pin_confirm=PIN)
        assert service.list_tiles(db, device)[0].accuracy is None


def test_a_tile_shows_the_latest_successful_calibration(test_database):
    now = utc_now()
    with test_database() as db:
        device = devices.remember_device(db, PC)
        user_id = service.sign_up(db, device, consent=True, username="mari_lapu", mobile_number="09178082488",
                                  pin=PIN, pin_confirm=PIN).user.user_id
        _add(db, user_id, Decimal("80.50"), "Successful", now - timedelta(days=3))
        _add(db, user_id, Decimal("92.25"), "Successful", now - timedelta(days=1))
        _add(db, user_id, None, "Failed", now)  # a later failure does not hide the last good score
        device = db.scalars(select(Device)).one()
        assert service.list_tiles(db, device)[0].accuracy == 92.25


def test_the_tile_schema_carries_accuracy():
    """The /accounts/tiles response field; None is allowed for a person never calibrated."""
    from app.accounts.schemas import TileRead

    assert TileRead(user_id=1, username="a_b", needs_pin=True).accuracy is None
    assert TileRead(user_id=1, username="a_b", needs_pin=True, accuracy=92.25).accuracy == 92.25


def test_the_tiles_route_leaves_accuracy_out_until_a_calibration():
    from app.api.routes.accounts import router

    route = next(r for r in router.routes if r.path.endswith("/tiles"))
    assert route.response_model_exclude_none is True
