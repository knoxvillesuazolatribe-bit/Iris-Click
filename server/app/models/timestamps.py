from datetime import UTC, datetime


def utc_now() -> datetime:
    """Timezone-aware 'now' for every created/updated/logged column."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands timestamps back without a timezone; they were written in UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
