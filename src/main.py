from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(
        title="EcoStory Backend API",
        description="Backend API for EcoStory application",
        version="1.0.0"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 🆔 Request ID Middleware
    from .core.request_id_middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)


    # 🔐 Register Firebase Auth Middleware
    from .core.auth_middleware import FirebaseAuthMiddleware
    app.add_middleware(FirebaseAuthMiddleware)
    
    # 🚀 IMPORT AND REGISTER YOUR ROUTES HERE
    from .core.api import register_routes
    register_routes(app)
    
    return app

app = create_app()

# Add a root endpoint
@app.get("/")
async def root():
    return {
        "message": "EcoStory Backend API", 
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.on_event("startup")
async def startup_event():
    try:
        # Test Firebase connection
        from .database.firebase import firebase_config
        db = firebase_config.get_db()
        logger.info("✅ Firebase connection established successfully")
        
        # Log registered routes
        logger.info("✅ All routes registered successfully")
        
    except Exception as e:
        logger.error(f"❌ Firebase connection failed: {e}")
        # You might want to raise this to prevent app startup if Firebase is critical
        # raise e

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )