from datetime import datetime
from ..database.firebase import firebase_config
import asyncio
import logging
import uuid

logger = logging.getLogger(__name__)


async def store_user_location(
    user_id: str,
    latitude: str,
    longitude: str,
    location: str,
) -> bool:
    """
    Append the user's current location to the `user_locations` collection.

    Mirrors the previous `storeUserLocationFn`: each call creates a NEW
    document keyed by a generated UUID (used as both the doc id and the `id`
    field). Reusable across endpoints — call it from the independent location
    API, on a chat message, and on chat-thread creation.

    Best-effort: failures are logged and swallowed so callers (e.g. the chat
    endpoint) are never broken by a location-write error.

    Returns True on success, False otherwise.
    """

    def sync_store() -> None:
        db = firebase_config.get_db()
        location_id = str(uuid.uuid4())
        db.collection("user_locations").document(location_id).set(
            {
                "id": location_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "user_id": user_id,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "location": location,
            }
        )

    try:
        await asyncio.to_thread(sync_store)
        return True
    except Exception as e:
        logger.warning(f"Failed to store user location for {user_id}: {e}")
        return False
