"""Backend configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Base configuration."""

    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # Groq (Whisper transcription + Llama classification — free tier)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Firebase
    FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")  # legacy; unused — kept for now

    # Firebase Admin SDK service account (base64-encoded JSON) — Step 22 FCM push
    FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    # Tavily API
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = ENVIRONMENT == "development"


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


def get_config():
    """Get configuration based on ENVIRONMENT."""
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        return ProductionConfig()
    return DevelopmentConfig()


# Validate required env vars
def validate_config():
    """Validate that all required environment variables are set."""
    required = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
