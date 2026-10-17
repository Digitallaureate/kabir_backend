from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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


class BlogRequestMessage(BaseModel):
    """One chat message, with any attached media resolved."""

    id: str
    role: Optional[str] = None
    user_id: Optional[str] = None
    content: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None  # "image" | "video"
    created_at: Optional[datetime] = None


class BlogRequestMedia(BaseModel):
    """Flat view of the media in the conversation, caption kept alongside."""

    url: str
    type: str
    caption: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[datetime] = None


class BlogDraft(BaseModel):
    """
    AI-drafted values for the admin blog form. Keys mirror the form fields so
    the panel can map them across one-to-one.

    `author`, `category` and `featured` are deliberately left for the admin —
    the model has no reliable source for them.
    """

    # Blog Content
    title: Optional[str] = None            # max 100
    slug: Optional[str] = None             # derived from title, unique
    excerpt: Optional[str] = None          # max 200
    heroImage: Optional[str] = None        # chosen from the chat's media
    # Editor.js document, JSON-encoded as a string the way the site stores it:
    # '{"time":...,"blocks":[...],"version":"..."}'
    content: Optional[str] = None

    # Media Gallery
    mediaGallery: List[str] = Field(default_factory=list)

    # Publication Settings
    author: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    featured: bool = False
    status: str = "draft"

    # SEO Settings
    seoTitle: Optional[str] = None         # max 60
    metaDescription: Optional[str] = None  # max 160
    keywords: List[str] = Field(default_factory=list)

    # Derived
    readTime: int = 1


class CreateBlogRequest(BaseModel):
    

    uid: str
    blogUrl: str
    chatId: str
    chatName: str
    title: str  
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    heroImage: Optional[str] = None
    content: Optional[str] = None  
    author: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    featured: bool = False
    status: Literal["draft", "published"] = "draft"

    seoTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)

    readTime: Optional[int] = None


class CreateBlogResponse(BaseModel):
    id: str
    slug: str
    title: str
    status: str
    blogUrl: str
    publishDate: Optional[str] = None
    requestId: Optional[str] = None


class BlogRequestDetail(BlogRequestItem):
    """
    One blog request plus the AI-drafted form values.

    The chat, its messages and its media are read on the server to build the
    draft, but are not returned — the admin form only needs the field values.
    """

    draft: Optional[BlogDraft] = None
    draft_error: Optional[str] = None
