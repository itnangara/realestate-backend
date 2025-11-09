"""
Feature Flags Tests

Tests:
- is_enabled() returns correct value from Redis cache
- is_enabled() returns correct value from environment variable fallback
- is_enabled() returns correct value from defaults
- set_flag() updates Redis correctly
- get_flag() fallback behavior
"""

import pytest
import sys
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import redis.asyncio as aioredis

from app.core.feature_flags import FeatureFlags, feature_flags, is_enabled_sync


@pytest.fixture
def mock_redis_client():
    """Mock Redis client"""
    mock_client = AsyncMock(spec=aioredis.Redis)
    mock_client.ping = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture
def feature_flags_instance(mock_redis_client):
    """FeatureFlags instance with mocked Redis"""
    flags = FeatureFlags()
    flags.redis_client = mock_redis_client
    return flags


@pytest.fixture
def feature_flags_no_redis():
    """FeatureFlags instance without Redis (fallback to defaults)"""
    flags = FeatureFlags()
    flags.redis_client = None
    return flags


class TestIsEnabledRedisCache:
    """Tests for is_enabled() with Redis cache"""
    
    @pytest.mark.asyncio
    async def test_is_enabled_from_redis_cache(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() returns value from Redis cache"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value="true")
        
        result = await feature_flags_instance.is_enabled(flag_name)
        
        assert result is True
        mock_redis_client.get.assert_called_once_with(f"feature_flag:{flag_name}")
    
    @pytest.mark.asyncio
    async def test_is_enabled_from_redis_cache_false(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() returns False from Redis cache"""
        flag_name = "auto_approve_enabled"
        mock_redis_client.get = AsyncMock(return_value="false")
        
        result = await feature_flags_instance.is_enabled(flag_name)
        
        assert result is False
        mock_redis_client.get.assert_called_once_with(f"feature_flag:{flag_name}")
    
    @pytest.mark.asyncio
    async def test_is_enabled_redis_cache_miss(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() falls back when Redis cache miss"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis_client.setex = AsyncMock()
        
        # Mock environment variable using sys.modules
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value=None)  # No env var
            
            result = await feature_flags_instance.is_enabled(flag_name)
            
            # Should use default (True for kyc_enabled)
            assert result is True
            # Should cache the default value
            mock_redis_client.setex.assert_called_once()
        finally:
            feature_flags_module.config = original_config
    
    @pytest.mark.asyncio
    async def test_is_enabled_redis_error_handling(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() handles Redis errors gracefully"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(side_effect=Exception("Redis connection error"))
        
        # Should fall back to default
        result = await feature_flags_instance.is_enabled(flag_name)
        
        # Should still return a value (default)
        assert isinstance(result, bool)


class TestIsEnabledEnvironmentFallback:
    """Tests for is_enabled() with environment variable fallback"""
    
    @pytest.mark.asyncio
    async def test_is_enabled_from_env_var(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() returns value from environment variable"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis_client.setex = AsyncMock()
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            # First call returns None (cache miss), second call returns env var
            feature_flags_module.config = Mock(side_effect=[None, "true"])
            
            result = await feature_flags_instance.is_enabled(flag_name)
            
            assert result is True
            # Should cache the env var value
            mock_redis_client.setex.assert_called_once()
        finally:
            feature_flags_module.config = original_config
    
    @pytest.mark.asyncio
    async def test_is_enabled_from_env_var_false(self, feature_flags_instance, mock_redis_client):
        """Test is_enabled() returns False from environment variable"""
        flag_name = "auto_approve_enabled"
        mock_redis_client.get = AsyncMock(return_value=None)
        mock_redis_client.setex = AsyncMock()
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(side_effect=[None, "false"])
            
            result = await feature_flags_instance.is_enabled(flag_name)
            
            assert result is False
        finally:
            feature_flags_module.config = original_config
    
    @pytest.mark.asyncio
    async def test_is_enabled_env_var_overrides_default(self, feature_flags_instance, mock_redis_client):
        """Test that environment variable overrides default value"""
        flag_name = "auto_approve_enabled"  # Default is False
        mock_redis_client.get = AsyncMock(return_value=None)
        mock_redis_client.setex = AsyncMock()
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            # Config is called with FEATURE_FLAG_AUTO_APPROVE_ENABLED
            def config_side_effect(key: str, default=None, cast=None):
                if key == "FEATURE_FLAG_AUTO_APPROVE_ENABLED":
                    return "true"
                return original_config(key, default=default, cast=cast)
            feature_flags_module.config = Mock(side_effect=config_side_effect)
            
            result = await feature_flags_instance.is_enabled(flag_name)
            
            assert result is True  # Env var overrides default False
        finally:
            feature_flags_module.config = original_config


class TestIsEnabledDefaults:
    """Tests for is_enabled() with default values"""
    
    @pytest.mark.asyncio
    async def test_is_enabled_from_defaults(self, feature_flags_no_redis):
        """Test is_enabled() returns value from defaults when Redis unavailable"""
        # kyc_enabled default is True
        result = await feature_flags_no_redis.is_enabled("kyc_enabled")
        assert result is True
        
        # auto_approve_enabled default is False
        result = await feature_flags_no_redis.is_enabled("auto_approve_enabled")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_enabled_default_for_unknown_flag(self, feature_flags_no_redis):
        """Test is_enabled() returns False for unknown flag"""
        result = await feature_flags_no_redis.is_enabled("unknown_flag")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_enabled_all_default_flags(self, feature_flags_no_redis):
        """Test all default flags return expected values"""
        expected_defaults = {
            "kyc_enabled": True,
            "auto_approve_enabled": False,
            "kyc_required_for_seller": True,
            "kyc_required_for_agent": True,
            "kyc_required_for_landlord": False,
            "kyc_required_for_investor": False,
            "role_request_enabled": True,
            "document_upload_enabled": True,
        }
        
        for flag_name, expected_value in expected_defaults.items():
            result = await feature_flags_no_redis.is_enabled(flag_name)
            assert result == expected_value, f"Flag {flag_name} should be {expected_value}"


class TestSetFlag:
    """Tests for set_flag() method"""
    
    @pytest.mark.asyncio
    async def test_set_flag_updates_redis(self, feature_flags_instance, mock_redis_client):
        """Test set_flag() updates Redis correctly"""
        flag_name = "kyc_enabled"
        enabled = True
        
        mock_redis_client.setex = AsyncMock(return_value=True)
        
        result = await feature_flags_instance.set_flag(flag_name, enabled)
        
        assert result is True
        mock_redis_client.setex.assert_called_once_with(
            f"feature_flag:{flag_name}",
            feature_flags_instance.cache_ttl,
            "true"
        )
    
    @pytest.mark.asyncio
    async def test_set_flag_false(self, feature_flags_instance, mock_redis_client):
        """Test set_flag() with False value"""
        flag_name = "auto_approve_enabled"
        enabled = False
        
        mock_redis_client.setex = AsyncMock(return_value=True)
        
        result = await feature_flags_instance.set_flag(flag_name, enabled)
        
        assert result is True
        mock_redis_client.setex.assert_called_once_with(
            f"feature_flag:{flag_name}",
            feature_flags_instance.cache_ttl,
            "false"
        )
    
    @pytest.mark.asyncio
    async def test_set_flag_redis_unavailable(self, feature_flags_no_redis):
        """Test set_flag() returns False when Redis unavailable"""
        # Ensure redis_client is None and won't connect
        feature_flags_no_redis.redis_client = None
        # Mock _get_redis_client to return None
        original_get_redis = feature_flags_no_redis._get_redis_client
        feature_flags_no_redis._get_redis_client = AsyncMock(return_value=None)
        
        try:
            result = await feature_flags_no_redis.set_flag("kyc_enabled", True)
            assert result is False
        finally:
            feature_flags_no_redis._get_redis_client = original_get_redis
    
    @pytest.mark.asyncio
    async def test_set_flag_redis_error(self, feature_flags_instance, mock_redis_client):
        """Test set_flag() handles Redis errors"""
        flag_name = "kyc_enabled"
        mock_redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))
        
        result = await feature_flags_instance.set_flag(flag_name, True)
        
        assert result is False


class TestGetFlag:
    """Tests for get_flag() method"""
    
    @pytest.mark.asyncio
    async def test_get_flag_from_redis(self, feature_flags_instance, mock_redis_client):
        """Test get_flag() returns value from Redis"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value="true")
        
        result = await feature_flags_instance.get_flag(flag_name)
        
        assert result is True
        mock_redis_client.get.assert_called_once_with(f"feature_flag:{flag_name}")
    
    @pytest.mark.asyncio
    async def test_get_flag_from_env_var(self, feature_flags_instance, mock_redis_client):
        """Test get_flag() falls back to environment variable"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value=None)  # Cache miss
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            # Config is called with FEATURE_FLAG_KYC_ENABLED
            def config_side_effect(key: str, default=None, cast=None):
                if key == "FEATURE_FLAG_KYC_ENABLED":
                    return "false"
                return original_config(key, default=default, cast=cast)
            feature_flags_module.config = Mock(side_effect=config_side_effect)
            
            result = await feature_flags_instance.get_flag(flag_name)
            
            assert result is False
        finally:
            feature_flags_module.config = original_config
    
    @pytest.mark.asyncio
    async def test_get_flag_from_defaults(self, feature_flags_instance, mock_redis_client):
        """Test get_flag() falls back to defaults"""
        flag_name = "kyc_enabled"
        mock_redis_client.get = AsyncMock(return_value=None)  # Cache miss
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value=None)  # No env var
            
            result = await feature_flags_instance.get_flag(flag_name)
            
            # Should return default (True for kyc_enabled)
            assert result is True
        finally:
            feature_flags_module.config = original_config
    
    @pytest.mark.asyncio
    async def test_get_flag_unknown_flag(self, feature_flags_instance, mock_redis_client):
        """Test get_flag() returns None for unknown flag"""
        flag_name = "unknown_flag"
        mock_redis_client.get = AsyncMock(return_value=None)
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value=None)
            
            result = await feature_flags_instance.get_flag(flag_name)
            
            assert result is None
        finally:
            feature_flags_module.config = original_config


class TestIsEnabledSync:
    """Tests for synchronous is_enabled_sync() wrapper"""
    
    def test_is_enabled_sync_from_env_var(self):
        """Test is_enabled_sync() returns value from environment variable"""
        flag_name = "kyc_enabled"
        
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value="false")
            
            result = is_enabled_sync(flag_name)
            
            assert result is False
        finally:
            feature_flags_module.config = original_config
    
    def test_is_enabled_sync_from_defaults(self):
        """Test is_enabled_sync() returns value from defaults"""
        # kyc_enabled default is True
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value=None)  # No env var
            
            result = is_enabled_sync("kyc_enabled")
            
            assert result is True
        finally:
            feature_flags_module.config = original_config
    
    def test_is_enabled_sync_unknown_flag(self):
        """Test is_enabled_sync() returns False for unknown flag"""
        feature_flags_module = sys.modules['app.core.feature_flags']
        original_config = feature_flags_module.config
        
        try:
            feature_flags_module.config = Mock(return_value=None)
            
            result = is_enabled_sync("unknown_flag")
            
            assert result is False
        finally:
            feature_flags_module.config = original_config


class TestFeatureFlagsInitialization:
    """Tests for FeatureFlags initialization"""
    
    @pytest.mark.asyncio
    async def test_feature_flags_redis_connection_success(self):
        """Test FeatureFlags successfully connects to Redis"""
        with patch('redis.asyncio.from_url') as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            # from_url is an async function, so make it return the client directly
            mock_from_url.return_value = mock_client
            
            flags = FeatureFlags()
            # Need to await the from_url call
            async def mock_from_url_async(*args, **kwargs):
                return mock_client
            mock_from_url.side_effect = mock_from_url_async
            
            client = await flags._get_redis_client()
            
            assert client is not None
            mock_from_url.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_feature_flags_redis_connection_failure(self):
        """Test FeatureFlags handles Redis connection failure gracefully"""
        with patch('redis.asyncio.from_url') as mock_from_url:
            mock_from_url.side_effect = Exception("Connection failed")
            
            flags = FeatureFlags()
            client = await flags._get_redis_client()
            
            assert client is None
    
    def test_feature_flags_defaults_loaded(self):
        """Test that FeatureFlags loads defaults correctly"""
        flags = FeatureFlags()
        
        assert "kyc_enabled" in flags.defaults
        assert "auto_approve_enabled" in flags.defaults
        assert flags.defaults["kyc_enabled"] is True
        assert flags.defaults["auto_approve_enabled"] is False

