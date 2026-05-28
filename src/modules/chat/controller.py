from fastapi import APIRouter, Request, status
from .model import (
    ChatCompletionProxyRequest,
    ChatCompletionProxyResponse,
)
from .service import ChatService
from ...core.schemas import GenericResponse, success_response

router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
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
