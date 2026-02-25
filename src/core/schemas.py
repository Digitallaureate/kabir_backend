from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class ResponseMetadata(BaseModel):
    """Metadata for API response"""
    request_id: str
    success: bool

class GenericResponse(BaseModel, Generic[T]):
    """Standard API response wrapper with msg/metadata structure"""
    msg: Optional[T] = None
    metadata: ResponseMetadata

    class Config:
        from_attributes = True

def success_response(request, data: Any = None, **kwargs) -> dict:
    """Helper to create a success response dict"""
    request_id = getattr(request.state, "request_id", "unknown")
    return {
        "msg": data,
        "metadata": {
            "request_id": request_id,
            "success": True
        }
    }

def error_response(request, message: str, error_code: int = 400, **kwargs) -> dict:
    """Helper to create an error response dict"""
    request_id = getattr(request.state, "request_id", "unknown")
    return {
        "msg": message,
        "metadata": {
            "request_id": request_id,
            "success": False
        }
    }
