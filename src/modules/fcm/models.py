from pydantic import BaseModel
from typing import Optional

class FCMTokenRegisterRequest(BaseModel):
    token: str
    platform: str  # "android" | "ios"
    app: Optional[str] = "ecostory"
    deviceId: Optional[str] = None
    appVersion: Optional[str] = None

class FCMTokenRegisterResponse(BaseModel):
    success: bool
    uid: str
