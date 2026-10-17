from ..config.settings import settings
from fastapi import HTTPException, status
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
import json
import logging

logger = logging.getLogger(__name__)

CHAT_COMPLETIONS_ENDPOINT = "https://api.openai.com/v1/chat/completions"


def call_chat_completions(payload: dict, timeout: int = 90) -> dict:
    """
    Send a chat-completions payload to OpenAI and return the parsed JSON.

    Blocking call — run it inside `asyncio.to_thread` from async code.
    """
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured on the backend",
        )

    req = urllib_request.Request(
        CHAT_COMPLETIONS_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("OpenAI HTTP error %s: %s", exc.code, error_body)
        raise HTTPException(
            status_code=(
                exc.code if 400 <= exc.code < 600 else status.HTTP_502_BAD_GATEWAY
            ),
            detail=error_body,
        ) from exc
    except URLError as exc:
        logger.error("OpenAI network error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to reach OpenAI",
        ) from exc

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError as exc:
        logger.error("Failed to decode OpenAI response: %s", raw_body)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response received from OpenAI",
        ) from exc


def extract_message_content(parsed_json: dict) -> str | None:
    """Pull the assistant's text out of a chat-completions response."""
    choices = parsed_json.get("choices") or []
    if not choices:
        return None

    content = ((choices[0] or {}).get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip() or None

    if isinstance(content, list):
        parts = [
            item["text"]
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ]
        return "\n".join(p.strip() for p in parts if p.strip()) or None

    return None
