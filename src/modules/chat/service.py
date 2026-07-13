from .model import (
    Chat,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMessageRole,
    GetOrCreateChatRequest,
    GetOrCreateChatResponse,
    ChatCompletionProxyRequest,
    ChatCompletionProxyResponse,
)
from ...config.settings import settings
from ...database.firebase import firebase_config
from firebase_admin import firestore
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from fastapi import HTTPException, status
from datetime import datetime, timedelta
import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)


class ChatService:
    @staticmethod
    async def get_or_create_chat(
        params: GetOrCreateChatRequest, user_id: str
    ) -> GetOrCreateChatResponse:
        """
        Return the user's existing chat or create a new one.

        A chat matches when it has the same chat_type, chat_name and location,
        the user is in `participants`, and it was updated within the last 6
        months. If no such chat exists, a new one is created with the user as a
        participant.
        """

        def sync_get_or_create() -> GetOrCreateChatResponse:
            db = firebase_config.db

            # --- 1. Timestamps -------------------------------------------------
            now = datetime.utcnow().isoformat() + "Z"
            six_months_ago = (datetime.utcnow() - timedelta(days=182)).isoformat() + "Z"

            # --- 2. Look for an existing, recent chat for this user ------------
            query = (
                db.collection("chats")
                .where("chat_type", "==", params.chat_type.value)
                .where("chat_name", "==", params.chat_name)
                .where("location", "==", params.location)
                .where("participants", "array_contains", user_id)
                .where("updated_at", ">=", six_months_ago)
                .limit(1)
            )

            existing = next(iter(query.stream()), None)
            if existing is not None:
                data = existing.to_dict() or {}
                data.setdefault("id", existing.id)
                data.setdefault("isHumanInteraction", False)
                return GetOrCreateChatResponse(data=Chat(**data), isExisting=True)

            # --- 3. None found -> create a new chat ---------------------------
            # Use a UUID id to match existing chats (created by the old backend).
            chat_id = str(uuid.uuid4())
            chat_data = {
                "id": chat_id,
                "created_at": now,
                "updated_at": now,
                "location": params.location,
                "chat_type": params.chat_type.value,
                "chat_name": params.chat_name,
                "participants": [user_id],
                "isHumanInteraction": False,
            }
            db.collection("chats").document(chat_id).set(chat_data)

            return GetOrCreateChatResponse(data=Chat(**chat_data), isExisting=False)

        return await asyncio.to_thread(sync_get_or_create)

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
                    elif isinstance(item.get("text"), dict) and isinstance(
                        item["text"].get("value"), str
                    ):
                        text_parts.append(item["text"]["value"])

            combined = "\n".join(
                part.strip() for part in text_parts if part and part.strip()
            )
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
                "created_at": datetime.utcnow().isoformat(timespec="milliseconds")
                + "Z",
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
        api_key = settings.OPENAI_API_KEY.strip()

        def sync_openai_call() -> dict:
            req = urllib_request.Request(
                endpoint,
                data=body_bytes,
                headers={
                    "Authorization": f"Bearer {api_key}",
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
                    status_code=(
                        exc.code
                        if 400 <= exc.code < 600
                        else status.HTTP_502_BAD_GATEWAY
                    ),
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

    @staticmethod
    async def _call_openai(payload: dict) -> dict:
        """Send a chat-completions payload to OpenAI and return the parsed JSON."""
        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY is not configured on the backend",
            )

        endpoint = "https://api.openai.com/v1/chat/completions"
        body_bytes = json.dumps(payload).encode("utf-8")
        api_key = settings.OPENAI_API_KEY.strip()

        def sync_call() -> dict:
            req = urllib_request.Request(
                endpoint,
                data=body_bytes,
                headers={
                    "Authorization": f"Bearer {api_key}",
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
                    status_code=(
                        exc.code
                        if 400 <= exc.code < 600
                        else status.HTTP_502_BAD_GATEWAY
                    ),
                    detail=error_body,
                ) from exc
            except URLError as exc:
                logger.error("OpenAI network error: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Unable to reach OpenAI",
                ) from exc

            body = raw_body.split("data: ")[-1] if "data: " in raw_body else raw_body
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                logger.error("Failed to decode OpenAI response: %s", raw_body)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response received from OpenAI",
                ) from exc

        return await asyncio.to_thread(sync_call)

    @staticmethod
    async def _verify_chat_participant(chat_id: str, user_id: str) -> dict:
        """
        Ensure the chat exists and the user is one of its participants.

        Raises 404 if the chat is missing and 403 if the user is not a
        participant. Returns the chat document data on success.
        """

        def sync_verify() -> dict:
            doc = firebase_config.db.collection("chats").document(chat_id).get()
            if not doc.exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chat not found",
                )

            data = doc.to_dict() or {}
            if user_id not in (data.get("participants") or []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User is not a participant in this chat",
                )
            return data

        return await asyncio.to_thread(sync_verify)

    @staticmethod
    async def _save_message(
        chat_id: str,
        role: str,
        user_id: str,
        content: str,
        location: str,
        image_url: str | None = None,
        message_type: str | None = None,
    ) -> str:
        """
        Write one message to chats/{chat_id}/messages and bump the chat's
        updated_at, in a single thread hop. Used for both user and assistant
        messages. `message_type` is only stored when provided (assistant
        replies don't carry one).
        """

        def sync_save() -> str:
            now = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

            chat_ref = firebase_config.db.collection("chats").document(chat_id)
            doc_ref = chat_ref.collection("messages").document()

            message_data = {
                "id": doc_ref.id,
                "role": role,
                "user_id": user_id,
                "content": content,
                "created_at": now,
                "image_url": image_url,
                "location": location,
            }
            if message_type is not None:
                message_data["message_type"] = message_type

            doc_ref.set(message_data)
            chat_ref.update({"updated_at": now})
            return doc_ref.id

        return await asyncio.to_thread(sync_save)

    @staticmethod
    async def send_chat_image_message(
        params: ChatMessageRequest, user_id: str
    ) -> ChatMessageResponse:
        logger.info(
            "send_chat_image_message start: chat_id=%s user_id=%s message_type=%s "
            "has_image=%s content_len=%d",
            params.chatId,
            user_id,
            getattr(params.message_type, "value", params.message_type),
            bool(params.image_url),
            len(params.content or ""),
        )

        if not params.image_url:
            logger.warning(
                "send_chat_image_message rejected: missing image_url (chat_id=%s user_id=%s)",
                params.chatId,
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image URL is required for image messages.",
            )

        # --- 0. Authorize: chat must exist and user must be a participant --
        await ChatService._verify_chat_participant(params.chatId, user_id)
        logger.info("Participant verified: chat_id=%s user_id=%s", params.chatId, user_id)

        # --- 1. Save the user's image message and bump the chat -----------
        user_message_id = await ChatService._save_message(
            chat_id=params.chatId,
            role=ChatMessageRole.USER.value,
            user_id=user_id,
            content=params.content,
            location=params.location,
            image_url=params.image_url,
            message_type=params.message_type.value,
        )
        logger.info("User image message saved: message_id=%s", user_message_id)

        # --- 2. Ask OpenAI to review the image ----------------------------
        # Speed levers: "detail": "low" makes OpenAI process a downscaled copy
        # of the image (much faster), and max_tokens caps how long the reply
        # can get (generation time scales with output length).

        location_context = await ChatService.get_location_context(params.chatId)
        nearby_sites = ChatService._format_nearby_sites(
            (location_context or {}).get("nearby_sites")
        )
        logger.info(
            "Location context loaded: chat_id=%s found=%s nearby_sites=%r",
            params.chatId,
            location_context is not None,
            nearby_sites,
        )

        prompt = params.content or "What do you think about this image?"
        vision_payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"The user is currently located at {params.location}, "
                        f"closest monuments are {nearby_sites}."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": params.image_url},
                        },
                    ],
                },
            ],
            "max_tokens": 300,
            "temperature": 0.8,
            "top_p": 0.9,
        }
        # DEBUG so the full payload only prints when LOG level is DEBUG.
        logger.info("Vision payload for chat_id=%s: %s", params.chatId, vision_payload)
        logger.info(
            "Calling OpenAI: model=%s chat_id=%s prompt=%r",
            settings.OPENAI_MODEL,
            params.chatId,
            prompt,
        )

        openai_response = await ChatService._call_openai(vision_payload)
        assistant_message = ChatService._extract_assistant_message(openai_response)
        generation_id = openai_response.get("id")
        logger.info(
            "OpenAI responded: generation_id=%s got_message=%s reply_len=%d",
            generation_id,
            assistant_message is not None,
            len(assistant_message or ""),
        )

        # --- 3. Save the assistant reply (only if we got one) -------------
        assistant_message_id = None
        if assistant_message:
            assistant_message_id = await ChatService._save_message(
                chat_id=params.chatId,
                role=ChatMessageRole.ASSISTANT.value,
                user_id=f"img_{generation_id}",
                content=assistant_message,
                location=params.location,
                image_url=None,
            )
            logger.info("Assistant message saved: message_id=%s", assistant_message_id)
        else:
            logger.warning(
                "No assistant message extracted from OpenAI response "
                "(chat_id=%s generation_id=%s)",
                params.chatId,
                generation_id,
            )

        # --- 4. Respond ---------------------------------------------------
        logger.info(
            "send_chat_image_message done: chat_id=%s user_message_id=%s "
            "assistant_message_id=%s",
            params.chatId,
            user_message_id,
            assistant_message_id,
        )
        return ChatMessageResponse(
            user_message_id=user_message_id,
            assistant_message=assistant_message,
            assistant_message_id=assistant_message_id,
        )
    
    @staticmethod
    def _format_nearby_sites(sites: list | None) -> str:
        """
        Format the `nearby_sites` list from a locationContext document into a
        short human-readable string, e.g.
        "Akbar's Tomb (Agra, UP) with 164.1 km, ...".
        """
        if not sites:
            return "unknown"

        parts: list[str] = []
        for site in sites:
            name = site.get("site_name") or "Unknown"
            distance_km = site.get("distance_km")
            dist = f"{distance_km:.1f} km" if distance_km is not None else "N/A"
            parts.append(f"{name} with {dist}")

        return ", ".join(parts)

    @staticmethod
    async def get_location_context(chat_id: str) -> dict | None:
        def sync_get_context() -> dict | None:
            query = (
                firebase_config.db.collection("locationContext")
                .where("chatId", "==", chat_id)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            doc = next(iter(query.stream()), None)
            return doc.to_dict() if doc else None

        return await asyncio.to_thread(sync_get_context)



