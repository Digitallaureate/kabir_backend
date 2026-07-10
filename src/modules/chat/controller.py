from fastapi import APIRouter, Request, Depends, HTTPException, status
from .model import (
    ChatCompletionProxyRequest,
    ChatCompletionProxyResponse,
    GetOrCreateChatRequest,
    GetOrCreateChatResponse,
)
from .service import ChatService
from ...core.schemas import GenericResponse, success_response
from ...database.firebase import verify_header_token
from ...utils.location import store_user_location
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)





@router.post(
    "/get-or-create",
    response_model=GenericResponse[GetOrCreateChatResponse],
    status_code=status.HTTP_200_OK,
)
async def get_or_create_chat(
    request: Request,
    body: GetOrCreateChatRequest,
    uid: str = Depends(verify_header_token),
):
    """
    Return the authenticated user's existing chat (same chat_type, chat_name
    and location, updated within the last 6 months) or create a new one.
    """
    try:
        result = await ChatService.get_or_create_chat(body, user_id=uid)

        # Persist the user's latest location (best-effort, won't break the response).
        await store_user_location(
            user_id=uid,
            latitude=body.latitude,
            longitude=body.longitude,
            location=body.location,
        )

        return success_response(request=request, data=result)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (get_or_create_chat): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get or create chat: {str(e)}",
        )


@router.post(
    "/completions",
    response_model=GenericResponse[ChatCompletionProxyResponse],
    status_code=status.HTTP_200_OK,
)
async def create_chat_completion(request: Request, body: ChatCompletionProxyRequest):
    """
    Secure server-side OpenAI chat-completions proxy.

    The Flutter app sends the same payload it previously sent to OpenAI,
    but without exposing the API key on the client.
    """

    result = await ChatService.create_chat_completion(body)
    return success_response(request=request, data=result)
