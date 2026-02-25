from datetime import datetime, timezone
from ...database.firebase import firebase_config
from .models import FCMTokenRegisterRequest

class FCMService:
    @staticmethod
    def register_token(uid: str, data: FCMTokenRegisterRequest):
        db = firebase_config.get_db()
        
        # Firestore path: users/{uid}/fcm_tokens/{token}
        token_ref = db.collection("users").document(uid).collection("fcm_tokens").document(data.token)
        
        now = datetime.now(timezone.utc)
        
        doc_data = {
            "token": data.token,
            "platform": data.platform,
            "app": data.app,
            "isActive": True,
            "updatedAt": now
        }
        
        if data.deviceId:
            doc_data["deviceId"] = data.deviceId
        if data.appVersion:
            doc_data["appVersion"] = data.appVersion
            
        # Set createdAt if document doesn't exist, otherwise update.
        # merge=True ensures we don't overwrite if it exists, but create if it doesn't.
        # Note: If we want createdAt to never change, we could check if doc exists first, 
        # but merge=True with a full dict is standard for "upsert".
        token_ref.set({
            **doc_data,
            "createdAt": now
        }, merge=True)
        
        return True
