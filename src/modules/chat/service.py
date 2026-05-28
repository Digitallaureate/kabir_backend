from .model import (
    Chat,
    GetOrCreateChatThreadRequest,
    GetOrCreateChatThreadResponse,
    ChatCompletionProxyRequest,
    ChatCompletionProxyResponse,
)
from ...config.settings import settings
from ...database.firebase import firebase_config
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from fastapi import HTTPException, status
from datetime import datetime
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

class ChatService:
    @staticmethod
    def getOrCreateChatThread(params: GetOrCreateChatThreadRequest) -> GetOrCreateChatThreadResponse:
        try:
            # Simulate fetching or creating a chat thread
            # In a real implementation, this would interact with Firebase Firestore
            is_existing = False  # Assume it's a new thread for this example
            chat = Chat(
                id="generated_chat_id",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                location=params.location,
                chat_type=params.chat_type,
                chat_name=params.chat_name,
                participants=[]
            )
            return GetOrCreateChatThreadResponse(success=True, data=chat, isExisting=is_existing)
        except Exception as e:
            logger.error(f"Error in getOrCreateChatThread: {e}")
            return GetOrCreateChatThreadResponse(success=False, data=None, isExisting=False)

    @staticmethod
    def _extract_assistant_message(parsed_json: dict) -> str | None:
        choices = parsed_json.get("choices") or []
        if not choices:
            return None

        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")

        if isinstance(content, str):
            return content.strip() or None

        # Some OpenAI responses return content blocks instead of a plain string.
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                    elif isinstance(item.get("text"), dict) and isinstance(item["text"].get("value"), str):
                        text_parts.append(item["text"]["value"])

            combined = "\n".join(part.strip() for part in text_parts if part and part.strip())
            return combined or None

        return None

    @staticmethod
    async def _save_assistant_message(
        request_body: ChatCompletionProxyRequest,
        assistant_message: str,
    ) -> str:
        def sync_save() -> str:
            doc_ref = (
                firebase_config.db.collection("chats")
                .document(request_body.chatId)
                .collection("messages")
                .document()
            )

            message_data = {
                "id": doc_ref.id,
                "role": "assistant",
                "content": assistant_message,
                "created_at": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
                "imageUrl": None,
                "location": request_body.location,
                "threadId": request_body.threadId,
            }

            if request_body.mode == "web_search":
                message_data["user_id"] = "WebG"

            doc_ref.set(message_data)
            return doc_ref.id

        return await asyncio.to_thread(sync_save)

    @staticmethod
    async def create_chat_completion(
        request_body: ChatCompletionProxyRequest,
    ) -> ChatCompletionProxyResponse:
        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY is not configured on the backend",
            )

        endpoint = "https://api.openai.com/v1/chat/completions"
        body_bytes = json.dumps(request_body.payload).encode("utf-8")

        def sync_openai_call() -> dict:
            req = urllib_request.Request(
                endpoint,
                data=body_bytes,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            try:
                with urllib_request.urlopen(req, timeout=90) as response:
                    raw_body = response.read().decode("utf-8")
            except HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                logger.error("OpenAI HTTP error %s: %s", exc.code, error_body)
                raise HTTPException(
                    status_code=exc.code if 400 <= exc.code < 600 else status.HTTP_502_BAD_GATEWAY,
                    detail=error_body,
                ) from exc
            except URLError as exc:
                logger.error("OpenAI network error: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Unable to reach OpenAI",
                ) from exc

            payload = raw_body.split("data: ")[-1] if "data: " in raw_body else raw_body

            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode OpenAI response: %s", raw_body)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response received from OpenAI",
                ) from exc

        parsed_json = await asyncio.to_thread(sync_openai_call)
        assistant_message = ChatService._extract_assistant_message(parsed_json)

        saved_message_id = None
        if assistant_message:
            saved_message_id = await ChatService._save_assistant_message(
                request_body=request_body,
                assistant_message=assistant_message,
            )

        return ChatCompletionProxyResponse(
            openai_response=parsed_json,
            assistant_message=assistant_message,
            saved_message_id=saved_message_id,
        )
