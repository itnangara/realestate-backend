"""
Feature Flags system with Redis caching and environment-based defaults

Handles:
- Feature toggles with Redis caching
- Environment-based defaults
- Flags: kyc_enabled, auto_approve_enabled, kyc_required_for_seller, etc.
"""

import redis.asyncio as aioredis
from decouple import config
from typing import Optional
from app.core.logger import get_logger

logger = get_logger(__name__)


class FeatureFlags:
    """Feature flags system with Redis caching"""
    
    def __init__(self):
        """Initialize feature flags with Redis connection"""
        self.redis_url = config("REDIS_URL", default="redis://localhost:6379")
        self.redis_client: Optional[aioredis.Redis] = None
        self.cache_ttl = 300  # 5 minutes cache TTL
        
        # Environment-based defaults
        self.defaults = {
            "kyc_enabled": config("KYC_ENABLED", default="true", cast=bool),
            "auto_approve_enabled": config("AUTO_APPROVE_ENABLED", default="false", cast=bool),
            "kyc_required_for_seller": config("KYC_REQUIRED_FOR_SELLER", default="true", cast=bool),
            "kyc_required_for_agent": config("KYC_REQUIRED_FOR_AGENT", default="true", cast=bool),
            "kyc_required_for_landlord": config("KYC_REQUIRED_FOR_LANDLORD", default="false", cast=bool),
            "kyc_required_for_investor": config("KYC_REQUIRED_FOR_INVESTOR", default="false", cast=bool),
            "role_request_enabled": config("ROLE_REQUEST_ENABLED", default="true", cast=bool),
            "document_upload_enabled": config("DOCUMENT_UPLOAD_ENABLED", default="true", cast=bool),
        }
    
    async def _get_redis_client(self) -> Optional[aioredis.Redis]:
        """Get or create Redis client"""
        if self.redis_client is None:
            try:
                self.redis_client = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf8",
                    decode_responses=True
                )
                # Test connection
                await self.redis_client.ping()
                logger.info("feature_flags_redis_connected", redis_url=self.redis_url)
            except Exception as e:
                logger.warning(
                    "feature_flags_redis_unavailable",
                    error=str(e),
                    redis_url=self.redis_url,
                    message="Using environment defaults only"
                )
                return None
        return self.redis_client
    
    async def is_enabled(self, flag_name: str) -> bool:
        """
        Check if a feature flag is enabled
        
        Args:
            flag_name: Name of the feature flag
        
        Returns:
            True if enabled, False otherwise
        """
        # Check Redis cache first
        redis_client = await self._get_redis_client()
        if redis_client:
            try:
                cached_value = await redis_client.get(f"feature_flag:{flag_name}")
                if cached_value is not None:
                    return cached_value.lower() == "true"
            except Exception as e:
                logger.warning(
                    "feature_flag_redis_error",
                    flag_name=flag_name,
                    error=str(e)
                )
        
        # Check environment variable override
        env_value = config(f"FEATURE_FLAG_{flag_name.upper()}", default=None)
        if env_value is not None:
            value = env_value.lower() == "true"
            # Cache the value
            if redis_client:
                try:
                    await redis_client.setex(
                        f"feature_flag:{flag_name}",
                        self.cache_ttl,
                        "true" if value else "false"
                    )
                except Exception:
                    pass
            return value
        
        # Use default from self.defaults
        value = self.defaults.get(flag_name, False)
        
        # Cache the default value
        if redis_client:
            try:
                await redis_client.setex(
                    f"feature_flag:{flag_name}",
                    self.cache_ttl,
                    "true" if value else "false"
                )
            except Exception:
                pass
        
        return value
    
    async def set_flag(self, flag_name: str, enabled: bool) -> bool:
        """
        Set a feature flag value (admin function)
        
        Args:
            flag_name: Name of the feature flag
            enabled: Whether to enable the flag
        
        Returns:
            True if successful, False otherwise
        """
        redis_client = await self._get_redis_client()
        if not redis_client:
            logger.warning(
                "feature_flag_set_failed",
                flag_name=flag_name,
                reason="Redis not available"
            )
            return False
        
        try:
            await redis_client.setex(
                f"feature_flag:{flag_name}",
                self.cache_ttl,
                "true" if enabled else "false"
            )
            logger.info(
                "feature_flag_set",
                flag_name=flag_name,
                enabled=enabled
            )
            return True
        except Exception as e:
            logger.error(
                "feature_flag_set_error",
                flag_name=flag_name,
                error=str(e)
            )
            return False
    
    async def get_flag(self, flag_name: str) -> Optional[bool]:
        """
        Get feature flag value (returns None if not found)
        
        Args:
            flag_name: Name of the feature flag
        
        Returns:
            True/False if found, None otherwise
        """
        redis_client = await self._get_redis_client()
        if redis_client:
            try:
                cached_value = await redis_client.get(f"feature_flag:{flag_name}")
                if cached_value is not None:
                    return cached_value.lower() == "true"
            except Exception:
                pass
        
        # Check environment variable
        env_value = config(f"FEATURE_FLAG_{flag_name.upper()}", default=None)
        if env_value is not None:
            return env_value.lower() == "true"
        
        # Return default
        return self.defaults.get(flag_name, None)
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None


# Singleton instance
feature_flags = FeatureFlags()


# Synchronous wrapper for use in non-async contexts
def is_enabled_sync(flag_name: str) -> bool:
    """
    Synchronous wrapper for feature flag check
    
    Note: This uses the default value only (no Redis cache).
    For async contexts, use feature_flags.is_enabled() instead.
    
    Args:
        flag_name: Name of the feature flag
    
    Returns:
        True if enabled, False otherwise
    """
    # Check environment variable first
    env_value = config(f"FEATURE_FLAG_{flag_name.upper()}", default=None)
    if env_value is not None:
        return env_value.lower() == "true"
    
    # Use default
    return feature_flags.defaults.get(flag_name, False)

