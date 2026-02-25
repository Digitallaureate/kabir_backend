import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate a unique request ID
        request_id = str(uuid.uuid4())
        
        # Store it in request state so it can be accessed in controllers and schemas
        request.state.request_id = request_id
        
        # Process the request
        response = await call_next(request)
        
        # Optionally add it to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
