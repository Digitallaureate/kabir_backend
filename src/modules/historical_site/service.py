# app/api/services/historical_site_service.py
from typing import List, Optional
from .models import (
    NearbySitesQuery,
    HistoricalSiteWithDistance,
    HistoricalSitesResponse,
)
from ...database.firebase import firebase_config
from ...utils.geo import haversine_km, format_distance
import logging
import os

# Use proper logging instead of print statements
logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_ID = "global-fallback-site"

class HistoricalSiteService:
    @staticmethod
    def find_nearby_sites(params: NearbySitesQuery) -> HistoricalSitesResponse:
        # Validate and parse coords
        try:
            user_lat = float(params.latitude)
            user_lng = float(params.longitude)
        except ValueError:
            raise ValueError("Latitude and longitude must be numbers")

        # Use logging instead of print (only in debug mode)
        if os.getenv("DEBUG", "false").lower() == "true":
            logger.info(f"Searching for sites within {params.radius} km of ({user_lat}, {user_lng})")

        historical_sites_ref = firebase_config.db.collection("historical_sites")

        # is_active == true
        query = historical_sites_ref.where("is_active", "==", True)

        # Optional category filter
        if params.category:
            query = query.where("category", "==", params.category)

        docs = list(query.stream())

        # Default assistant id (global-fallback-site)
        default_doc_ref = historical_sites_ref.document(DEFAULT_DOCUMENT_ID)
        default_doc = default_doc_ref.get()
        default_assistant_id = default_doc.to_dict().get("assistant_id") if default_doc.exists else None

        if not docs:
            return HistoricalSitesResponse(
                sites=[],
                meta={"total": 0, "showing": 0, "radius": params.radius},
                default_assistant_id=default_assistant_id,
            )

        # Compute distances & filter by radius
        results: List[HistoricalSiteWithDistance] = []
        
        for d in docs:
            if d.id == DEFAULT_DOCUMENT_ID:
                continue
                
            data = d.to_dict() or {}
            site_name = data.get("site_name", "Unknown")
            
            # Parse site lat/lng (stored as strings in your schema)
            try:
                site_lat = float(str(data.get("latitude", "")))
                site_lng = float(str(data.get("longitude", "")))
            except ValueError:
                continue  # Skip invalid coordinates

            # Calculate distance
            dist_km = haversine_km(user_lat, user_lng, site_lat, site_lng)
            
            # Filter by radius
            if dist_km <= params.radius:
                results.append(
                    HistoricalSiteWithDistance(
                        id=str(data.get("id", d.id)),
                        created_at=str(data.get("created_at", "")),
                        site_name=site_name,
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
                        distance=format_distance(dist_km)
                    )
                )

        # Optimized sorting
        def get_numeric_distance(site):
            try:
                distance_str = site.distance
                if " km" in distance_str:
                    return float(distance_str.replace(" km", ""))
                elif " m" in distance_str:
                    return float(distance_str.replace(" m", "")) / 1000
                else:
                    return float(distance_str)
            except (ValueError, AttributeError):
                return 999999

        # Sort by nearest
        results.sort(key=get_numeric_distance)

        # Limit
        limited = results[: max(0, params.limit)]

        return HistoricalSitesResponse(
            sites=limited,
            meta={"total": len(results), "showing": len(limited), "radius": params.radius},
        )
