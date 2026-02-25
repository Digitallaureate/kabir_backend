import firebase_admin
from firebase_admin import credentials, firestore, auth
from fastapi import HTTPException
import os
import logging
from pathlib import Path
import jwt

logger = logging.getLogger(__name__)

class FirebaseConfig:
    def __init__(self):
        self.db = None
        self.app = None
        self._initialize()
    
    def _initialize(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
                
                if service_account_path:
                    if not os.path.isabs(service_account_path):
                        project_root = Path(__file__).parent.parent.parent
                        service_account_path = project_root / service_account_path
                    
                    if os.path.exists(service_account_path):
                        cred = credentials.Certificate(str(service_account_path))
                        self.app = firebase_admin.initialize_app(cred)
                        logger.info(f"✅ Firebase initialized with service account: {service_account_path}")
                    else:
                        raise Exception(f"Service account file not found: {service_account_path}")
                else:
                    raise Exception("FIREBASE_SERVICE_ACCOUNT_PATH not set in environment variables")
            else:
                self.app = firebase_admin.get_app()
                logger.info("✅ Using existing Firebase app")
            
            self.db = firestore.client()
            logger.info(f"✅ Firestore initialized for project: {self.app.project_id}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase: {e}")
            raise Exception(f"Firebase initialization failed: {str(e)}")
    
    def get_db(self):
        if not self.db:
            raise Exception("Firestore not initialized")
        return self.db

firebase_config = FirebaseConfig()

async def verify_header_token(request) -> str:
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = authorization.split("Bearer ", 1)[1].strip()
    # Clean whitespace just in case
    token = "".join(token.split())
    
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # 🛠️ DEVELOPMENT BYPASS for copy-paste signature corruption
    # To enable: Add DEBUG_SKIP_VERIFY=true to your .env
    if os.getenv("DEBUG_SKIP_VERIFY") == "true":
        try:
            # Decode without verification to extract UID
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # Still protect against simple project mismatch
            if payload.get("aud") != firebase_config.app.project_id:
                logger.error(f"🚨 Bypass Mismatch: {payload.get('aud')} vs {firebase_config.app.project_id}")
                raise HTTPException(status_code=401, detail="Project ID mismatch")
            
            uid = payload.get("sub") or payload.get("user_id")
            logger.warning(f"⚠️ Auth Bypass active for user: {uid}")
            return uid
        except Exception as e:
            logger.error(f"❌ Bypass failed: {str(e)}")
            raise HTTPException(status_code=401, detail="Malformed token")

    try:
        decoded = auth.verify_id_token(token, app=firebase_config.app)
        return decoded.get("uid")
    except Exception as e:
        logger.error(f"❌ SDK Verification Failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token signature")