from datetime import datetime, timedelta, timezone
from typing import Optional

# Firestore stores instants in UTC; the Firebase console renders them in the
# viewer's local zone. Admin-facing APIs convert to IST so the values match
# what the team sees in the console.
IST = timezone(timedelta(hours=5, minutes=30))


def to_ist(value) -> Optional[datetime]:
    """
    Convert a Firestore timestamp to IST, keeping it timezone-aware so it
    serializes as e.g. 2026-08-17T10:22:25.465000+05:30.

    Accepts both real timestamps and the ISO strings some collections store
    (e.g. "2026-08-17T04:52:25.465Z"). Naive datetimes are assumed to be UTC,
    which is how this project writes them everywhere. Unparseable values return
    None rather than breaking the response.
    """
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(IST)
