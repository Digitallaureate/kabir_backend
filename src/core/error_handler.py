import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .exceptions import AppError
from .schemas import error_response

logger = logging.getLogger(__name__)

def setup_error_handlers(app):
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        logger.warning(f"{exc.status_code} {exc.detail} {request.url.path}")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                request=request,
                message=exc.detail,
                error_code=exc.status_code
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        logger.warning(f"422 {exc.errors()} {request.url.path}")
        return JSONResponse(
            status_code=422,
            content=error_response(
                request=request,
                message="Invalid request body or parameters",
                error_code=422
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        logger.warning(f"{exc.status_code} {exc.detail} {request.url.path}")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                request=request,
                message=exc.detail,
                error_code=exc.status_code
            ),
        )

    @app.exception_handler(Exception)
    async def handle_generic_error(request: Request, exc: Exception):
        logger.exception(f"500 {request.url.path}: {exc}")
        return JSONResponse(
            status_code=500,
            content=error_response(
                request=request,
                message="Internal server error",
                error_code=500
            ),
        )
