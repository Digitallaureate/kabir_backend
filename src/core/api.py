from fastapi import FastAPI, APIRouter, HTTPException, Request
from ..database.firebase import firebase_config
from src.modules.historical_site.controller import router as historical_site_router
from src.modules.process_text.controller import router as process_text_router

# Create the main router for this module
router = APIRouter()

from .schemas import success_response

@router.get("/health")
async def health_check(request: Request):
    """Health check endpoint"""
    data = {
        "status": "healthy",
        "firebase_connected": firebase_config.db is not None
    }
    return success_response(request=request, data=data)

# Get all collections endpoint - FIXED
@router.get("/collections")
async def get_collections(request: Request):
    """Get all collections available in Firestore"""
    try:
        db = firebase_config.db
        collections = db.collections()
        
        collection_list = []
        for collection in collections:
            collection_info = {
                "name": collection.id,
                # Removed the problematic 'path' attribute
            }
            
            # Get document count (optional - can be slow for large collections)
            try:
                docs = list(collection.limit(1).stream())
                collection_info["has_documents"] = len(docs) > 0
                
                # Get first few document IDs as sample
                if len(docs) > 0:
                    collection_info["sample_document_id"] = docs[0].id
                
            except Exception as e:
                collection_info["has_documents"] = "unknown"
                collection_info["error"] = str(e)
            
            collection_list.append(collection_info)
        
        # Sort collections by name for better readability
        collection_list.sort(key=lambda x: x["name"])
        
        data = {
            "collections": collection_list,
            "total_collections": len(collection_list)
        }
        return success_response(request=request, data=data, message="Collections retrieved successfully")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting collections: {str(e)}")


from src.modules.fcm.controller import router as fcm_router


def register_routes(app: FastAPI):
    # Register the router from this module
    app.include_router(router, prefix="/api", tags=["api"])
    app.include_router(historical_site_router)
    app.include_router(process_text_router)
    app.include_router(fcm_router, prefix="/api")