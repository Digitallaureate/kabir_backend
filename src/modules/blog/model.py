from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class BlogRequestItem(BaseModel):
    id: str
    chat_id: str
    chat_title: Optional[str] = None
    user_id: str
    user_name: Optional[str] = None
    order_id: Optional[str] = None
    request_id: Optional[str] = None
    service_id: Optional[str] = None
    service_request_id: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BlogRequestListMeta(BaseModel):
    total: int
    page: int
    limit: int
    total_pages: int


class BlogResponse(BaseModel):
    data: List[BlogRequestItem]
    meta: BlogRequestListMeta


class BlogRequestUser(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    photo_url: Optional[str] = None


class BlogRequestChat(BaseModel):
    id: str
    title: Optional[str] = None
    location: Optional[str] = None
    chat_type: Optional[str] = None
    created_at: Optional[datetime] = None


class BlogRequestDetail(BlogRequestItem):
    """One blog request with its related user and chat expanded."""

    user: Optional[BlogRequestUser] = None
    chat: Optional[BlogRequestChat] = None
