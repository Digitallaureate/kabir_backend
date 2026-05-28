from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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


class ChatCompletionProxyRequest(BaseModel):
    """
    Backend-owned OpenAI chat request.

    `payload` is the exact JSON body that the Flutter app previously sent
    directly to OpenAI. The backend injects the API key securely.
    """

    chatId: str = Field(..., description="Chat document ID in Firestore")
    threadId: str = Field(..., description="Client thread identifier")
    location: str = Field(..., description="User location for message storage")
    mode: Literal["standard", "web_search"] = Field(
        default="standard",
        description="Controls Firestore metadata for the saved assistant message",
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Raw OpenAI request body previously sent from Flutter",
    )


class ChatCompletionProxyResponse(BaseModel):
    openai_response: Dict[str, Any]
    assistant_message: Optional[str] = None
    saved_message_id: Optional[str] = None
