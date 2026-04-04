from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "ShopTalk AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    

    # MongoDB Atlas
    MONGODB_URL: Optional[str] = None

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Mock OTP mode for local testing (legacy)
    MOCK_OTP_MODE: bool = True
    # Firebase service account key path (optional) — prefer environment variable in production
    # Set `FIREBASE_SERVICE_ACCOUNT_PATH` in the environment to the full path to the JSON key.
    # Leave as None in development if you want the app to attempt repo-root resolution at runtime.
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None

    # Email Service (SendGrid)
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "aiexpert.azan@gmail.com"
    FROM_EMAIL: str = "aiexpert.azan@gmail.com"

    # JWT & Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    REFRESH_TOKEN_EXPIRATION_DAYS: int = 7
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60


    # WhatsApp Business API
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_WABA_ID: str = ""

    # Admin
    ADMIN_PHONE_NUMBER: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()