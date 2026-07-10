from pydantic import BaseModel, Field
from typing import List, Optional


class HomeFeedRequest(BaseModel):
    location: str
    latitude: float
    longitude: float


class NearbyHistoricalSite(BaseModel):
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
    prompt: str
    distance: Optional[str] = None


class FeedCardBase(BaseModel):
    id: str
    title: str
    category: str
    content: str
    location: str
    tags: Optional[List[str]] = None
    distance: Optional[str] = None


class NearbyHiddenGem(FeedCardBase):
    pass


class NearbyEvent(FeedCardBase):
    pass


class NearbyRestaurant(FeedCardBase):
    pass


class HomeFeedResponse(BaseModel):
    user_id: str
    location: str
    latitude: float
    longitude: float
    nearby_monument: Optional[NearbyHistoricalSite] = None
    nearby_hidden_gems: List[NearbyHiddenGem] = Field(default_factory=list, max_length=3)
    nearby_events: List[NearbyEvent] = Field(default_factory=list, max_length=3)
    nearby_restaurants: List[NearbyRestaurant] = Field(default_factory=list, max_length=3)

