from fastapi import APIRouter, HTTPException, status, Request
from .model import (
    ProcessTextRequest, 
    ProcessTextResponse, 
    ErrorResponse,
    IntentType
)
from .service import ProcessTextService
import time
from ...core.schemas import GenericResponse, success_response

router = APIRouter(
    prefix="/process-text",
    tags=["Text Processing"]
)

@router.post("/", response_model=GenericResponse[ProcessTextResponse], status_code=status.HTTP_200_OK)
async def process_text(request: Request, body: ProcessTextRequest):
    """
    Process user text input with Pinecone search and Firestore integration:
    1. Takes user content with chapter/chat context
    2. Detects intent using OpenAI  
    3. Routes to appropriate Pinecone search function
    4. Saves result message to Firestore
    5. Returns complete response
    """
    start_time = time.time()
    
    try:
        # Validate required parameters
        if not all([body.content, body.chapterId, body.chatId, 
                   body.lat, body.long, body.location]):
            raise ValueError("Missing required parameters: content, chapterId, chatId, lat, long, location")
        
        # Process through service
        result = await ProcessTextService.process_user_content(body)
        
        # Add total processing time
        total_time = int((time.time() - start_time) * 1000)
        result.total_processing_time_ms = total_time
        
        return success_response(request=request, data=result)
        
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process text: {str(e)}"
        )

# @router.get("/intents", response_model=List[str], status_code=status.HTTP_200_OK)
# async def get_available_intents():
#     """Get list of available intent types"""
#     return [intent.value for intent in IntentType]

# @router.get("/health", status_code=status.HTTP_200_OK)
# async def health_check():
#     """Health check for process-text service"""
#     return {"status": "healthy", "service": "process-text"}