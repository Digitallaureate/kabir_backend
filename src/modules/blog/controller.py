from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from .model import (
    BlogRequestDetail,
    BlogResponse,
    CreateBlogRequest,
    CreateBlogResponse,
)
from .service import BlogAlreadyExists, BlogService
from ...core.schemas import GenericResponse, success_response
from ...core.security import verify_internal_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/blog",
    tags=["Blog"],
)


@router.get(
    "/requests",
    response_model=GenericResponse[BlogResponse],
    status_code=status.HTTP_200_OK,
)
async def get_blog_requests(
    request: Request,
    status_filter: str | None = Query(
        default=None, alias="status", description="Optional status filter"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    _caller: str = Depends(verify_internal_api_key),
):

    try:
        result = await BlogService.get_blog_requests(
            status=status_filter,
            page=page,
            limit=limit,
        )
        return success_response(request=request, data=result)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (get_blog_requests): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch blog requests: {str(e)}",
        )


@router.get(
    "/requests/{request_id}",
    response_model=GenericResponse[BlogRequestDetail],
    status_code=status.HTTP_200_OK,
)
async def get_blog_request_detail(
    request: Request,
    request_id: str,
    message_limit: int = Query(
        30, ge=1, le=100, description="How many of the latest chat messages to include"
    ),
    _caller: str = Depends(verify_internal_api_key),
):
    """
    Return one blog request with its chat details and the tail of the
    conversation (oldest first) so a blog can be written from it.
    """
    try:
        result = await BlogService.get_blog_request_detail(
            request_id, message_limit=message_limit
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Blog request not found",
            )
        return success_response(request=request, data=result)
    except HTTPException:
        # Already an HTTP error (e.g. the 404 above) — keep its status code.
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (get_blog_request_detail): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch blog request detail: {str(e)}",
        )


@router.post(
    "/requests/{request_id}/blog",
    response_model=GenericResponse[CreateBlogResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_blog(
    request: Request,
    request_id: str,
    body: CreateBlogRequest,
    _caller: str = Depends(verify_internal_api_key),
):
    """
    Save the reviewed blog into the blogs collection.

    `status: "draft"` saves a draft, `status: "published"` publishes it and
    stamps publishDate. Either way the originating request is moved forward.
    """
    try:
        result = await BlogService.create_blog(request_id, body)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Blog request not found",
            )
        return success_response(request=request, data=result)
    except HTTPException:
        raise
    except BlogAlreadyExists as exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exists))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Endpoint Error (create_blog): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create blog: {str(e)}",
        )
