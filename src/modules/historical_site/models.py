from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class HistoricalSite(BaseModel):
    id: str
    created_at: str
    site_name: str
    site_description: str
    site_type: str
    is_active: bool
    location: str
    latitude: str
    longitude: str
    services: Optional[List[str]] = None
    assistant_id: str
    prompt: Optional[str] = None
    category: Optional[str] = None
    difficulty_level: Optional[str] = None

class HistoricalSiteWithDistance(HistoricalSite):
    distance: Optional[str] = None

class NearbySitesQuery(BaseModel):
    latitude: str
    longitude: str
    radius: float = Field(10.0, description="Search radius in km")
    limit: int = Field(2, description="Max results")
    category: Optional[str] = None
    # difficulty_level is in your interface; include if you’ll filter later
    difficulty_level: Optional[str] = None

class HistoricalSitesResponse(BaseModel):
    sites: List[HistoricalSiteWithDistance]
    meta: Dict[str, Any]