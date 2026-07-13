from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class EnumChatType(str, Enum):
    GLOBAL = "global"
    JOURNEY = "journey"

class EnumChatMessageType(str, Enum):
    TEXT = "text"
    VOICE = "voice"

class ChatMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# -------- Request schema (permissive for migration) --------
class GetOrCreateChatRequest(BaseModel):
    chat_name: str
    chat_type: EnumChatType
    location: str
    latitude: float
    longitude: float



class Chat(BaseModel):
    id: str
    created_at: str
    updated_at: str
    location: str
    chat_type: EnumChatType
    chat_name: str
    participants: List[str] = Field(default_factory=list)
    isHumanInteraction: bool



class GetOrCreateChatResponse(BaseModel):
    data: Chat
    isExisting: bool


class ChatCompletionProxyRequest(BaseModel):
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

class ChatMessageRequest(BaseModel):
    chatId: str
    content: str
    location: str
    latitude: float
    longitude: float
    image_url: Optional[str] = None
    message_type: EnumChatMessageType = EnumChatMessageType.TEXT

class ChatMessageResponse(BaseModel):
    user_message_id: str
    assistant_message: Optional[str] = None
    assistant_message_id: Optional[str] = None



    