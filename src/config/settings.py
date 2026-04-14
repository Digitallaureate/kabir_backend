from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "EcoStory Backend API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    
    # Cache Settings
    CACHE_TTL_SECONDS: int = 300
    
    # Firebase Settings
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = "firebase-service-account.json"
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    
    # Security Settings
    DEBUG_SKIP_VERIFY: bool = False
    INTERNAL_API_KEY: str = ""
    
    # OpenAI Settings
    OPENAI_API_KEY: Optional[str] = None
    
    # Pinecone Settings
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENV: Optional[str] = None
    PINECONE_CONTROLLER_HOST: Optional[str] = None
    PINECONE_CONTROLLER_URL: Optional[str] = None
    
    # Pinecone Index Settings
    KABIR_INDEX_NAME: str = "kabir"
    KABIR_INDEX_HOST: Optional[str] = None
    
    PINECONE_INDEX_NAME: str = "images-index"
    PINECONE_INDEX_HOST: Optional[str] = None
    
    PINECONE_INDEX_NAME2: str = "viedo-index"
    PINECONE_INDEX_HOST2: Optional[str] = None
    
    PINECONE_INDEX_NAME3: str = "audio-index"
    PINECONE_INDEX_HOST3: Optional[str] = None

    # Load from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
