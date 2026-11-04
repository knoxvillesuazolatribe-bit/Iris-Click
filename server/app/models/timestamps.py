from datetime import UTC, datetime


def utc_now() -> datetime:
    """Timezone-aware 'now' for every created/updated/logged column."""
    return datetime.now(UTC)
