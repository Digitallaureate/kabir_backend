# app/api/services/historical_site_service.py
from typing import List, Optional, Tuple
from .models import (
    NearbySitesQuery,
    HistoricalSiteWithDistance,
    HistoricalSitesResponse,
)
from ...database.firebase import firebase_config
from ...utils.geo import haversine_km, format_distance
from ...config.settings import settings
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_ID = "global-fallback-site"

# ---------------------------------------------------------------------------
# In-memory site cache
# Firestore reads are the bottleneck. Historical sites change rarely, so we
# cache the raw documents for CACHE_TTL_SECONDS and serve every request from
# memory. First warm-up call populates the cache; subsequent calls are ~0 ms.
# ---------------------------------------------------------------------------
# Raw dicts already have lat/lng coerced to float (invalid coords dropped).
# Default-document row is excluded from the list.
# ---------------------------------------------------------------------------

_site_cache: List[dict] = []          # list of raw dicts (pre-parsed)
_default_assistant_id: Optional[str] = None
_cache_expires_at: float = 0.0        # epoch seconds


def _fetch_all_sites() -> Tuple[List[dict], Optional[str]]:
    """
    Fetches ALL active sites + the default doc from Firestore IN PARALLEL.
    Returns (list_of_raw_dicts, default_assistant_id).
    Raw dicts already have lat/lng coerced to float (invalid coords dropped).
    Default-document row is excluded from the list.
    """
    historical_sites_ref = firebase_config.db.collection("historical_sites")

    def fetch_sites():
        return list(
            historical_sites_ref.where("is_active", "==", True).stream()
        )

    def fetch_default():
        doc = historical_sites_ref.document(DEFAULT_DOCUMENT_ID).get()
        return doc.to_dict().get("assistant_id") if doc.exists else None

    # Fire both reads concurrently so we only pay ONE network round-trip time
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_sites   = pool.submit(fetch_sites)
        future_default = pool.submit(fetch_default)
        docs           = future_sites.result()
        default_aid    = future_default.result()

    parsed: List[dict] = []
    for d in docs:
        if d.id == DEFAULT_DOCUMENT_ID:
            continue
        data = d.to_dict() or {}
        try:
            site_lat = float(str(data.get("latitude", "")))
            site_lng = float(str(data.get("longitude", "")))
        except (ValueError, TypeError):
            continue  # skip invalid coords once, at cache-fill time
        data["_lat"] = site_lat
        data["_lng"] = site_lng
        data["_id"]  = str(data.get("id", d.id))
        parsed.append(data)

    return parsed, default_aid


def _get_cached_sites() -> Tuple[List[dict], Optional[str]]:
    """Return sites from cache, refreshing if stale."""
    global _site_cache, _default_assistant_id, _cache_expires_at

    now = time.monotonic()
    if now < _cache_expires_at and _site_cache is not None:
        return _site_cache, _default_assistant_id

    # Cache miss — fetch from Firestore
    logger.info("Cache miss: refreshing historical_sites from Firestore")
    _site_cache, _default_assistant_id = _fetch_all_sites()
    _cache_expires_at = now + settings.CACHE_TTL_SECONDS
    return _site_cache, _default_assistant_id


class HistoricalSiteService:

    @staticmethod
    def invalidate_cache() -> None:
        """Call this whenever a site is created/updated/deleted."""
        global _cache_expires_at
        _cache_expires_at = 0.0
        logger.info("Historical-sites cache invalidated")

    @staticmethod
    def find_nearby_sites(params: NearbySitesQuery) -> HistoricalSitesResponse:
        # Validate and parse coords
        try:
            user_lat = float(params.latitude)
            user_lng = float(params.longitude)
        except (ValueError, TypeError):
            raise ValueError("Latitude and longitude must be numbers")

        if settings.DEBUG:
            logger.info(
                f"Searching for sites within {params.radius} km of ({user_lat}, {user_lng})"
            )

        # ---- serve from cache (single Firestore round-trip at most) --------
        all_sites, default_assistant_id = _get_cached_sites()

        if not all_sites:
            return HistoricalSitesResponse(
                sites=[],
                meta={"total": 0, "showing": 0, "radius": params.radius},
                default_assistant_id=default_assistant_id,
            )

        # ---- filter in memory (no network, pure CPU) ------------------------
        results: List[Tuple[float, HistoricalSiteWithDistance]] = []

        category_filter = params.category  # local var avoids repeated attr lookup

        for data in all_sites:
            # Category filter (if requested)
            if category_filter and data.get("category") != category_filter:
                continue

            dist_km = haversine_km(user_lat, user_lng, data["_lat"], data["_lng"])

            if dist_km <= params.radius:
                results.append((
                    dist_km,
                    HistoricalSiteWithDistance(
                        id=data["_id"],
                        created_at=str(data.get("created_at", "")),
                        site_name=str(data.get("site_name", "Unknown")),
                        site_description=str(data.get("site_description", "")),
                        site_type=str(data.get("site_type", "")),
                        is_active=bool(data.get("is_active", True)),
                        location=str(data.get("location", "")),
                        latitude=str(data.get("latitude", "")),
                        longitude=str(data.get("longitude", "")),
                        services=data.get("services"),
                        assistant_id=str(data.get("assistant_id", "")),
                        prompt=data.get("prompt"),
                        category=data.get("category"),
                        difficulty_level=data.get("difficulty_level"),
                        distance=format_distance(dist_km),
                    ),
                ))

        # Sort by raw float distance — no string re-parsing needed
        results.sort(key=lambda t: t[0])

        limited = [site for _, site in results[: max(0, params.limit)]]

        return HistoricalSitesResponse(
            sites=limited,
            meta={"total": len(results), "showing": len(limited), "radius": params.radius},
            default_assistant_id=default_assistant_id,
        )
