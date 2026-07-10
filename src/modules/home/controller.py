from fastapi import APIRouter, Depends, HTTPException, Request, status
import logging

from ...database.firebase import verify_header_token
from ...core.schemas import GenericResponse, success_response
from .model import HomeFeedRequest, HomeFeedResponse
from .service import HomeFeedService
from ...utils.location import store_user_location

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/home",
    tags=["Home"]
)


@router.post(
    "/feed",
    response_model=GenericResponse[HomeFeedResponse],
    status_code=status.HTTP_200_OK,
)
async def get_home_feed(
    request: Request,
    body: HomeFeedRequest,
    uid: str = Depends(verify_header_token),
):
    """
    Return the home feed in the project's standard response format.
    """
    try:
        result = HomeFeedService.get_home_feed(body, user_id=uid)

        await store_user_location(
            user_id=uid,
            latitude=body.latitude,
            longitude=body.longitude,
            location=body.location,
        )

        return success_response(request=request, data=result)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (get_home_feed): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build home feed: {str(e)}"
        )
