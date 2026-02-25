from fastapi import APIRouter, Request, Depends, HTTPException, status
from ...database.firebase import verify_header_token
from .models import FCMTokenRegisterRequest, FCMTokenRegisterResponse
from .service import FCMService
from ...core.schemas import GenericResponse, success_response

router = APIRouter(
    prefix="/fcm",
    tags=["FCM"]
)

@router.post("/save-fcm-token", response_model=GenericResponse[FCMTokenRegisterResponse])
async def save_fcm_token(
    request: Request,
    body: FCMTokenRegisterRequest,
    uid: str = Depends(verify_header_token)
):
    """
    Registers or updates an FCM token for the authenticated user.
    """
    try:
        success = FCMService.register_token(uid, body)
        data = FCMTokenRegisterResponse(success=success, uid=uid)
        return success_response(request=request, data=data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save FCM token: {str(e)}"
        )
