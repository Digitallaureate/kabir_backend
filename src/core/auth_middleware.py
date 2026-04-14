from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request, HTTPException
import logging
from ..config.settings import settings

logger = logging.getLogger(__name__)

# Paths that do NOT require authentication
ALLOWED_PATHS = {
    "/",               # root
    "/api/health",     # health
    "/docs", 
    "/redoc", 
    "/openapi.json",
    "/favicon.ico",
}

# ✅ Paths that accept internal service-to-service calls via X-Internal-Key
# (Cloud Functions cannot generate Firebase user tokens — they use a shared secret instead)
INTERNAL_SERVICE_PATHS = {
    "/process-text/",
    "/process-text",
}

class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # 1. Allow whitelisted paths
        if (
            path in ALLOWED_PATHS
            or path.startswith("/docs")
            or path.startswith("/openapi")
            or path.startswith("/static")
        ):
            return await call_next(request)

        # 2. ✅ Allow internal service-to-service calls via shared secret key
        if path in INTERNAL_SERVICE_PATHS:
            internal_key = request.headers.get("X-Internal-Key", "")
            expected_key = settings.INTERNAL_API_KEY
            if expected_key and internal_key == expected_key:
                request.state.user = "cloud-function-internal"
                logger.info(f"✅ Internal service call allowed for path: {path}")
                return await call_next(request)
            # If key missing/wrong, fall through to normal Firebase auth below

        # 3. Verify Firebase Token for all other paths
        try:
            from ..database.firebase import verify_header_token
            
            # This function now handles the Dev Bypass internally
            user_id = await verify_header_token(request)
            
            # Expose user to handlers via request.state
            request.state.user = user_id
            return await call_next(request)
            
        except HTTPException as exc:
            from .schemas import error_response
            return JSONResponse(
                status_code=exc.status_code,
                content=error_response(request, message=exc.detail, error_code=exc.status_code)
            )
        except Exception as e:
            from .schemas import error_response
            logger.error(f"Middleware Auth Error: {str(e)}")
            return JSONResponse(
                status_code=401,
                content=error_response(request, message="Authentication failed", error_code=401)
            )
