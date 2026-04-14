from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from .service import services_service
from ...core.schemas import success_response, error_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["services"]
)

@router.get("")
async def list_services(request: Request):
    """Get the listing of all available services"""
    try:
        data = services_service.get_services()
        return success_response(
            request=request, 
            data=data, 
            message="Services retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Endpoint Error (list_services): {e}")
        return JSONResponse(
            status_code=500,
            content=error_response(
                request=request,
                message="Failed to retrieve services",
                error_code=500
            )
        )

@router.get("/{service_id}/form")
async def get_service_form(request: Request, service_id: str):
    """Get the specific form configuration for a service"""
    try:
        form_data = services_service.get_service_form(service_id)
        
        if not form_data:
            return JSONResponse(
                status_code=404,
                content=error_response(
                    request=request,
                    message=f"Form for service '{service_id}' not found",
                    error_code=404
                )
            )
            
        return success_response(
            request=request,
            data=form_data,
            message=f"Form for '{service_id}' retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Endpoint Error (get_service_form): {e}")
        return JSONResponse(
            status_code=500,
            content=error_response(
                request=request,
                message=f"Failed to retrieve form for '{service_id}'",
                error_code=500
            )
        )
