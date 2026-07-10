from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
from typing import List, Optional, Tuple

from firebase_admin import firestore

from ...database.firebase import firebase_config
from ...utils.geo import format_distance, haversine_km
from .model import (
    HomeFeedRequest,
    HomeFeedResponse,
    NearbyEvent,
    NearbyHiddenGem,
    NearbyHistoricalSite,
    NearbyRestaurant,
)

logger = logging.getLogger(__name__)


class HomeFeedService:
    @staticmethod
    def get_home_feed(body: HomeFeedRequest, user_id: str) -> HomeFeedResponse:
        """
        Build the home feed response.

        Build the home feed from active records and persist a snapshot.
        """
        if firebase_config.db is None:
            raise ValueError("Firestore is not initialized")

        user_lat = body.latitude
        user_lng = body.longitude

        monument, hidden_gems, events, restaurants = HomeFeedService._fetch_sections(
            user_lat=user_lat,
            user_lng=user_lng,
        )

        response = HomeFeedResponse(
            user_id=user_id,
            location=body.location,
            latitude=body.latitude,
            longitude=body.longitude,
            nearby_monument=monument,
            nearby_hidden_gems=hidden_gems,
            nearby_events=events,
            nearby_restaurants=restaurants,
        )

        HomeFeedService._save_home_feed_snapshot(
            body=body,
            response=response,
            user_id=user_id,
        )
        return response

    @staticmethod
    def _fetch_sections(
        user_lat: float,
        user_lng: float,
    ) -> Tuple[
        Optional[NearbyHistoricalSite],
        List[NearbyHiddenGem],
        List[NearbyEvent],
        List[NearbyRestaurant],
    ]:
        db = firebase_config.db

        def fetch_historical_sites():
            return list(db.collection("historical_sites").where("is_active", "==", True).stream())

        def fetch_trivia():
            return list(db.collection("trivia").where("is_active", "==", True).stream())

        def fetch_tips():
            return list(db.collection("tips").where("is_active", "==", True).stream())

        with ThreadPoolExecutor(max_workers=3) as pool:
            historical_future = pool.submit(fetch_historical_sites)
            trivia_future = pool.submit(fetch_trivia)
            tips_future = pool.submit(fetch_tips)

            historical_docs = historical_future.result()
            trivia_docs = trivia_future.result()
            tips_docs = tips_future.result()

        monument = HomeFeedService._get_nearest_monument(
            docs=historical_docs,
            user_lat=user_lat,
            user_lng=user_lng,
        )
        hidden_gems = HomeFeedService._get_nearest_hidden_gems(
            docs=trivia_docs,
            user_lat=user_lat,
            user_lng=user_lng,
        )
        events = HomeFeedService._get_nearest_events(
            docs=tips_docs,
            user_lat=user_lat,
            user_lng=user_lng,
        )
        restaurants = HomeFeedService._get_nearest_restaurants(
            docs=tips_docs,
            user_lat=user_lat,
            user_lng=user_lng,
        )

        return monument, hidden_gems, events, restaurants

    @staticmethod
    def _get_nearest_monument(
        docs,
        user_lat: float,
        user_lng: float,
    ) -> Optional[NearbyHistoricalSite]:
        candidates: List[Tuple[float, NearbyHistoricalSite]] = []

        for doc in docs:
            data = doc.to_dict() or {}
            coords = HomeFeedService._parse_coordinates(data)
            if coords is None:
                continue

            item_lat, item_lng = coords
            distance_km = haversine_km(user_lat, user_lng, item_lat, item_lng)

            candidates.append((
                distance_km,
                NearbyHistoricalSite(
                    id=str(data.get("id", doc.id)),
                    created_at=str(data.get("created_at", "")),
                    site_name=str(data.get("site_name", "Unknown")),
                    site_description=str(data.get("site_description", "")),
                    site_type=str(data.get("site_type", "")),
                    is_active=bool(data.get("is_active", True)),
                    location=str(data.get("location", "")),
                    latitude=str(data.get("latitude", "")),
                    longitude=str(data.get("longitude", "")),
                    services=data.get("services"),
                    prompt=str(data.get("prompt", "")),
                    distance=format_distance(distance_km),
                ),
            ))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    @staticmethod
    def _get_nearest_hidden_gems(
        docs,
        user_lat: float,
        user_lng: float,
    ) -> List[NearbyHiddenGem]:
        candidates: List[Tuple[float, NearbyHiddenGem]] = []

        for doc in docs:
            data = doc.to_dict() or {}
            coords = HomeFeedService._parse_coordinates(data)
            if coords is None:
                continue

            item_lat, item_lng = coords
            distance_km = haversine_km(user_lat, user_lng, item_lat, item_lng)

            candidates.append((
                distance_km,
                NearbyHiddenGem(
                    id=str(data.get("id", doc.id)),
                    title=str(data.get("title", "Untitled")),
                    category=str(data.get("category", "")),
                    content=str(data.get("content", "")),
                    location=str(data.get("location", "")),
                    tags=data.get("tags"),
                    distance=format_distance(distance_km),
                ),
            ))

        candidates.sort(key=lambda item: item[0])
        return [item for _, item in candidates[:3]]

    @staticmethod
    def _get_nearest_events(
        docs,
        user_lat: float,
        user_lng: float,
    ) -> List[NearbyEvent]:
        return HomeFeedService._get_tips_by_difficulty(
            docs=docs,
            difficulty_level="easy",
            item_builder=NearbyEvent,
            user_lat=user_lat,
            user_lng=user_lng,
        )

    @staticmethod
    def _get_nearest_restaurants(
        docs,
        user_lat: float,
        user_lng: float,
    ) -> List[NearbyRestaurant]:
        return HomeFeedService._get_tips_by_difficulty(
            docs=docs,
            difficulty_level="medium",
            item_builder=NearbyRestaurant,
            user_lat=user_lat,
            user_lng=user_lng,
        )

    @staticmethod
    def _get_tips_by_difficulty(
        docs,
        difficulty_level: str,
        item_builder,
        user_lat: float,
        user_lng: float,
    ):
        candidates = []

        for doc in docs:
            data = doc.to_dict() or {}
            if str(data.get("difficulty_level", "")).strip().lower() != difficulty_level:
                continue

            coords = HomeFeedService._parse_coordinates(data)
            if coords is None:
                continue

            item_lat, item_lng = coords
            distance_km = haversine_km(user_lat, user_lng, item_lat, item_lng)

            candidates.append((
                distance_km,
                item_builder(
                    id=str(data.get("id", doc.id)),
                    title=str(data.get("title", "Untitled")),
                    category=str(data.get("category", "")),
                    content=str(data.get("content", "")),
                    location=str(data.get("location", "")),
                    tags=data.get("tags"),
                    distance=format_distance(distance_km),
                ),
            ))

        candidates.sort(key=lambda item: item[0])
        return [item for _, item in candidates[:3]]

    @staticmethod
    def _parse_coordinates(data: dict) -> Optional[Tuple[float, float]]:
        try:
            return (
                float(str(data.get("latitude", "")).strip()),
                float(str(data.get("longitude", "")).strip()),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _save_home_feed_snapshot(
        body: HomeFeedRequest,
        response: HomeFeedResponse,
        user_id: str,
    ) -> None:
        db = firebase_config.db
        if db is None:
            return

        snapshot = {
            "user_id": user_id,
            "location": body.location,
            "feed_latitude": body.latitude,
            "feed_longitude": body.longitude,
            "nearby_monument": (
                HomeFeedService._serialize_model(response.nearby_monument)
                if response.nearby_monument is not None
                else None
            ),
            "nearby_hidden_gems": [
                HomeFeedService._serialize_model(item) for item in response.nearby_hidden_gems
            ],
            "nearby_events": [
                HomeFeedService._serialize_model(item) for item in response.nearby_events
            ],
            "nearby_restaurants": [
                HomeFeedService._serialize_model(item) for item in response.nearby_restaurants
            ],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        try:
            db.collection("home_feed_snapshots").add(snapshot)
        except Exception as exc:
            logger.warning("Failed to save home feed snapshot: %s", exc)

    @staticmethod
    def _serialize_model(model) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()
