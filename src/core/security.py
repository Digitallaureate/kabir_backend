from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from ..config.settings import settings
import hmac
import logging

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"

internal_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def verify_internal_api_key(
    request: Request,
    api_key: str | None = Security(internal_api_key_header),
) -> str:
    """
    Authenticate a server-to-server caller (admin panel, internal jobs) with
    the shared INTERNAL_API_KEY instead of a Firebase user token.

    Use this on routes that are also listed in the auth middleware's
    INTERNAL_SERVICE_PATHS, otherwise the middleware rejects the request
    before it reaches the route.
    """
    # Local development: same bypass verify_header_token honours, so internal
    # routes can be hit from Swagger/Postman without setting a header.
    if settings.DEBUG_SKIP_VERIFY:
        logger.warning("⚠️ Internal API key bypass active (DEBUG_SKIP_VERIFY)")
        return "local-debug-service"

    if not settings.INTERNAL_API_KEY:
        logger.error("INTERNAL_API_KEY is not configured on the backend")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal API key is not configured",
        )

    key = api_key or request.headers.get(API_KEY_HEADER)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {API_KEY_HEADER} header",
        )

    # compare_digest keeps the check constant-time so the key can't be guessed
    # one character at a time by timing the response.
    if not hmac.compare_digest(key.strip(), settings.INTERNAL_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return "internal-service"
