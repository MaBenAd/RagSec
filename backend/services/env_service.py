import os
from backend.services.logging_service import logger

REQUIRED_ENV_VARS = [
    "GROQ_API_KEY",
    "JWT_SECRET_KEY",
]
PRODUCTION_ONLY_VARS = [
    "DATABASE_URL",
    "QDRANT_URL",
]
MIN_JWT_SECRET_LENGTH = 32


def validate_env():
    """
    Checks if all required environment variables are set.
    Returns False when required values are missing or insecure in production.
    """
    env = os.getenv("ENV", "dev").strip().lower()
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]

    if env == "production":
        missing += [var for var in PRODUCTION_ONLY_VARS if not os.getenv(var)]

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(sorted(set(missing)))}")
        logger.warning("Please check your .env file or environment configuration.")
        return False

    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if len(jwt_secret) < MIN_JWT_SECRET_LENGTH:
        logger.warning(
            f"JWT_SECRET_KEY is too short ({len(jwt_secret)} chars). "
            f"Use at least {MIN_JWT_SECRET_LENGTH} characters for production."
        )
        if env == "production":
            return False

    return True
