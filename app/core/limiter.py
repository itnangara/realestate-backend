"""
Enterprise-grade rate limiting configuration

Handles:
- Rate limiting with Redis backend
- Graceful fallback if initialization fails
- Proper error handling and logging
- Windows Unicode encoding issue prevention
"""

import os
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from decouple import config
from app.core.logger import get_logger

logger = get_logger(__name__)

# Initialize limiter with enterprise-grade error handling
limiter: Optional[Limiter] = None


def init_limiter() -> Optional[Limiter]:
    """
    Initialize rate limiter with enterprise-grade error handling.
    
    Returns:
        Limiter instance or None if initialization fails
    """
    global limiter
    
    if limiter is not None:
        return limiter
    
    try:
        # Get configuration from environment
        default_limits = config("RATE_LIMIT_DEFAULT", default="100/minute", cast=str)
        storage_uri = config("REDIS_URL", default="redis://localhost:6379")
        
        # Prevent slowapi from auto-reading .env file to avoid Unicode encoding issues on Windows
        # slowapi's Limiter tries to read .env files automatically via config_filename parameter
        # We set it to a non-existent file to prevent this, since we use python-decouple for env management
        config_filename = ".env.slowapi_disabled"
        
        # Check if .env exists and log warning if it might cause issues
        if os.path.isfile(".env"):
            try:
                # Try to read first line to check encoding
                with open(".env", "r", encoding="utf-8") as f:
                    f.readline()
            except UnicodeDecodeError:
                logger.warning(
                    "rate_limiter_env_encoding_warning",
                    message=".env file may have encoding issues, but limiter is configured to skip it"
                )
        
        # Initialize limiter
        limiter_instance = Limiter(
            key_func=get_remote_address,
            default_limits=[default_limits],
            storage_uri=storage_uri,
            config_filename=config_filename,  # Prevent auto-reading .env
            auto_check=True,
            swallow_errors=True,  # Don't crash app if rate limiting fails
            in_memory_fallback_enabled=True,  # Fallback to in-memory if Redis unavailable
        )
        
        logger.info(
            "rate_limiter_initialized",
            default_limits=default_limits,
            storage_uri=storage_uri.split("@")[-1] if "@" in storage_uri else storage_uri,  # Hide credentials in logs
            in_memory_fallback=True
        )
        
        limiter = limiter_instance
        return limiter
        
    except Exception as e:
        logger.error(
            "rate_limiter_initialization_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
            message="Rate limiting disabled - application will continue without rate limiting"
        )
        # Return None to indicate failure - application should handle this gracefully
        return None


# Initialize limiter at module load time
limiter = init_limiter()
