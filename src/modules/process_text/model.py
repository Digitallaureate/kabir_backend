from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from datetime import datetime

class IntentType(str, Enum):
    """Available intent types for content processing"""
    SEARCH_IMAGE = "search_image" 
    SEARCH_AUDIO = "search_audio"
    SEARCH_VIDEO = "search_video"
    NONE = "none"

class ProcessTextRequest(BaseModel):
    """Input model for process-text API - matches your Firebase function parameters"""
    content: str = Field(..., min_length=1, max_length=5000, description="User input content/query")
    chapterId: str = Field(..., description="Chapter ID for Pinecone filtering")
    chatId: str = Field(..., description="Chat ID for Firestore message storage")
    lat: float = Field(..., description="User latitude")
    long: float = Field(..., description="User longitude") 
    location: str = Field(..., description="User location name")
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "Show me images of the Taj Mahal",
                "chapterId": "chapter_123",
                "chatId": "chat_456", 
                "lat": 27.1751,
                "long": 78.0421,
                "location": "Agra, India"
            }
        }

class IntentDetectionResult(BaseModel):
    """Result from OpenAI intent detection"""
    detected_intent: IntentType = Field(..., description="Detected intent from OpenAI")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    reasoning: Optional[str] = Field(None, description="AI reasoning for intent")
    processing_time_ms: int = Field(..., description="Time taken for intent detection")
    semantic_query: Optional[str] = None

class PineconeSearchResult(BaseModel):
    """Result from Pinecone semantic search"""
    score: float = Field(..., description="Similarity score from Pinecone")
    content: str = Field(..., description="Content/description from search result")
    metadata: Dict[str, Any] = Field(default={}, description="Additional metadata from Pinecone")

class FirestoreMessage(BaseModel):
    """Firestore message structure"""
    id: str = Field(..., description="Message document ID")
    content: str = Field(..., description="Message content")
    created_at: str = Field(..., description="ISO formatted timestamp")
    location: str = Field(..., description="Location name")
    role: str = Field(default="assistant", description="Message role")
    user_id: str = Field(..., description="User/assistant ID")
    image_url: Optional[str] = Field(None, description="URL if applicable")

class ImageSearchResult(BaseModel):
    """Result from image search via Pinecone"""
    message: str = Field(..., description="Status message")
    firestore_message: FirestoreMessage = Field(..., description="Message saved to Firestore")
    search_metadata: PineconeSearchResult = Field(..., description="Pinecone search details")

class AudioSearchResult(BaseModel):
    """Result from audio search via Pinecone"""
    message: str = Field(..., description="Status message")
    firestore_message: FirestoreMessage = Field(..., description="Message saved to Firestore")
    search_metadata: PineconeSearchResult = Field(..., description="Pinecone search details")

class VideoSearchResult(BaseModel):
    """Result from video search via Pinecone"""
    message: str = Field(..., description="Status message")
    firestore_message: FirestoreMessage = Field(..., description="Message saved to Firestore")
    search_metadata: PineconeSearchResult = Field(..., description="Pinecone search details")




# Union type for all possible results
FunctionResult = Union[
    ImageSearchResult,
    AudioSearchResult,
    VideoSearchResult
]

class ProcessTextResponse(BaseModel):
    """Complete response for process-text API"""
    success: bool = Field(..., description="Request success status")
    intent: IntentDetectionResult = Field(..., description="Intent detection details")
    result: FunctionResult = Field(..., description="Function execution result")
    total_processing_time_ms: int = Field(..., description="Total processing time")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = Field(default=False, description="Always false for errors")
    error_type: str = Field(..., description="Type of error")
    error_message: str = Field(..., description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")