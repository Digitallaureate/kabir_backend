from fastapi import APIRouter, Query, HTTPException, status, Request
from .models import (
    HistoricalSitesResponse,
    NearbySitesQuery,
)
from .service import HistoricalSiteService
from ...core.schemas import GenericResponse, success_response

router = APIRouter(
    prefix="/historical-site",
    tags=["Historical Site"]
)

@router.get("/nearby", response_model=GenericResponse[HistoricalSitesResponse], status_code=status.HTTP_200_OK)
async def get_nearby_historical_sites(
    request: Request,
    latitude: str = Query(..., description="Latitude as string"),
    longitude: str = Query(..., description="Longitude as string"),
    radius: float = Query(10.0, description="Radius in km"),
    limit: int = Query(2, description="Max number of sites"),
    category: str | None = Query(None, description="Optional category filter"),
):
    """
    Returns historical sites within the specified radius.
    Skips Firebase verification for now.
    """
    try:
        params = NearbySitesQuery(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            limit=limit,
            category=category,
        )
        data = HistoricalSiteService.find_nearby_sites(params)
        return success_response(request=request, data=data)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve nearby historical sites: {str(e)}"
        )
