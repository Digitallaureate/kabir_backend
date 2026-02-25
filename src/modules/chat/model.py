from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class EnumChatType(str, Enum):
    GLOBAL = "global"
    JOURNEY = "journey"
    TIPS = "tips"
    TRIVIA = "trivia"

class EnumChatMessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"

class ChatMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# -------- Request schema (permissive for migration) --------
class GetOrCreateChatThreadRequest(BaseModel):
    """
    Permissive request model so you can reuse the same frontend payload.
    Only these are required: chat_name, chat_type, location, latitude, longitude.
    Others are accepted but ignored by this endpoint.
    """
    chat_name: str
    chat_type: EnumChatType
    location: str
    latitude: str
    longitude: str

    # Optional / tolerated inputs (present in your current logs)
    chat_id: Optional[str] = None
    assistant_id: Optional[str] = None
    thread_id: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None


# -------- Chat document (matches your Firestore/Node response) --------
class Chat(BaseModel):
    id: str
    created_at: str
    updated_at: str
    location: str
    chat_type: EnumChatType
    chat_name: str
    participants: List[str] = Field(default_factory=list)


# -------- Response wrapper (mirrors Node) --------
class GetOrCreateChatThreadResponse(BaseModel):
    success: bool
    data: Chat
    isExisting: bool
