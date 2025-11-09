"""
Enterprise-Grade S3 Service Tests

Comprehensive test suite for S3Service covering:
- Presigned PUT/GET URL generation with validation
- PII bucket/path handling (separate bucket and same-bucket scenarios)
- S3 key generation with uniqueness guarantees
- Error handling and edge cases
- Configuration validation
- ClientError handling
"""

import pytest
import os
from contextlib import contextmanager
from unittest.mock import Mock, patch, MagicMock, call
from typing import Dict, Optional, Iterator, List
from botocore.exceptions import ClientError
import sys

from app.services.s3_service import S3Service


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_boto3_client():
    """
    Mock boto3 S3 client with proper spec validation.
    
    Returns:
        MagicMock configured as boto3 S3 client
    """
    mock_client = MagicMock()
    # Reset mock state between tests
    mock_client.reset_mock()
    return mock_client


@pytest.fixture
def aws_config_default() -> Dict[str, Optional[str]]:
    """
    Default AWS configuration for tests.
    
    Returns:
        Dictionary of AWS config values
    """
    return {
        'AWS_ACCESS_KEY_ID': 'test-access-key-id',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-access-key',
        'AWS_BUCKET_NAME': 'test-bucket',
        'AWS_REGION': 'us-east-1',
        'AWS_S3_PII_BUCKET': None,  # Uses default bucket
        'AWS_S3_PII_PATH': 'kyc-documents/'
    }


@pytest.fixture
def aws_config_pii_separate_bucket() -> Dict[str, Optional[str]]:
    """
    AWS configuration with separate PII bucket.
    
    Returns:
        Dictionary of AWS config values with separate PII bucket
    """
    return {
        'AWS_ACCESS_KEY_ID': 'test-access-key-id',
        'AWS_SECRET_ACCESS_KEY': 'test-secret-access-key',
        'AWS_BUCKET_NAME': 'test-bucket',
        'AWS_REGION': 'us-east-1',
        'AWS_S3_PII_BUCKET': 'pii-bucket',
        'AWS_S3_PII_PATH': 'kyc-documents/'
    }


# ============================================================================
# Enterprise-Grade Helper Functions
# ============================================================================

@contextmanager
def mock_aws_environment(config_dict: Dict[str, Optional[str]]) -> Iterator[None]:
    """
    Enterprise-grade context manager for mocking AWS environment variables.
    
    Properly handles:
    - Setting environment variables
    - Restoring original values after test
    - Handling None values (removes from env)
    - Isolating test environment
    
    Args:
        config_dict: Dictionary of environment variable names and values
        
    Yields:
        None (context manager for environment variable patching)
        
    Example:
        with mock_aws_environment({'AWS_BUCKET_NAME': 'test-bucket'}):
            service = S3Service()
    """
    # Store original values for restoration
    original_values: Dict[str, Optional[str]] = {}
    keys_to_remove: List[str] = []
    
    # Prepare environment variables
    env_vars: Dict[str, str] = {}
    
    for key, value in config_dict.items():
        if value is None:
            # Store original value and mark for removal
            original_values[key] = os.environ.get(key)
            keys_to_remove.append(key)
        else:
            # Store original value and set new value
            original_values[key] = os.environ.get(key)
            env_vars[key] = str(value)
    
    try:
        # Apply environment variable changes
        with patch.dict(os.environ, env_vars, clear=False):
            # Remove keys that should be None
            for key in keys_to_remove:
                os.environ.pop(key, None)
            
            yield
    finally:
        # Restore original environment
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


def build_env_vars_from_config(config_dict: Dict[str, Optional[str]]) -> Dict[str, str]:
    """
    Build environment variables dictionary from config, filtering None values.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        Dictionary of environment variables (None values excluded)
    """
    return {
        key: str(value)
        for key, value in config_dict.items()
        if value is not None
    }


@pytest.fixture
def s3_service_with_creds(mock_boto3_client: MagicMock, aws_config_default: Dict[str, Optional[str]]):
    """
    S3Service instance with mocked credentials and client.
    
    Enterprise-grade fixture that:
    - Properly isolates environment variables
    - Mocks boto3 client
    - Validates service initialization
    - Cleans up after test
    
    Args:
        mock_boto3_client: Mocked boto3 S3 client
        aws_config_default: Default AWS configuration
        
    Yields:
        S3Service instance ready for testing
    """
    # Ensure AWS_S3_PII_BUCKET is not in env if it's None (so default is used)
    config_for_env = aws_config_default.copy()
    if config_for_env.get('AWS_S3_PII_BUCKET') is None:
        # Remove it so config() uses the default (bucket_name)
        config_for_env.pop('AWS_S3_PII_BUCKET', None)
    
    with mock_aws_environment(config_for_env):
        with patch('boto3.client', return_value=mock_boto3_client):
            service = S3Service()
            
            # Enterprise-grade validation
            assert service.s3_client is not None, "S3 client should be initialized with valid credentials"
            assert service.s3_client == mock_boto3_client, "S3 client should be the mocked instance"
            assert service.bucket_name == aws_config_default['AWS_BUCKET_NAME'], "Bucket name should match config"
            # When AWS_S3_PII_BUCKET is not set, pii_bucket should default to bucket_name
            assert service.pii_bucket == service.bucket_name, "PII bucket should default to bucket_name when not set"
            
            yield service
            
            # Cleanup: reset mock state
            mock_boto3_client.reset_mock()


@pytest.fixture
def s3_service_no_creds():
    """
    S3Service instance without credentials (simulates missing AWS config).
    
    Enterprise-grade fixture that:
    - Removes all AWS environment variables
    - Mocks decouple.config to prevent reading from .env files
    - Mocks boto3 to prevent fallback to AWS credentials files
    - Validates service handles missing config gracefully
    - Ensures proper isolation
    
    Yields:
        S3Service instance with s3_client = None
    """
    # Remove all AWS-related environment variables
    aws_keys = [k for k in os.environ.keys() if k.startswith('AWS_')]
    original_values = {key: os.environ.get(key) for key in aws_keys}
    
    try:
        # Remove AWS environment variables
        for key in aws_keys:
            os.environ.pop(key, None)
        
        # Mock boto3.client to return None (simulating no credentials)
        # This prevents boto3 from using AWS credentials files
        with patch('boto3.client', side_effect=Exception("No credentials")):
            # Patch config at the module level where it's imported
            # This prevents reading from .env files and ensures None is returned for AWS keys
            def config_side_effect(key: str, default=None):
                """Return None for AWS keys, otherwise return default"""
                if key.startswith('AWS_'):
                    return None
                return default
            
            # Get the module directly from sys.modules to avoid import issues
            s3_module = sys.modules['app.services.s3_service']
            
            # Store original config function
            original_config = s3_module.config
            
            try:
                # Replace config in the module
                # Since config is called in __init__, this will be used when creating the instance
                s3_module.config = Mock(side_effect=config_side_effect)
                
                service = S3Service()
                
                # Enterprise-grade validation
                assert service.s3_client is None, "S3 client should be None when credentials are missing"
                assert service.aws_access_key_id is None, "Access key should be None"
                assert service.aws_secret_access_key is None, "Secret key should be None"
                
                yield service
            finally:
                # Restore original config function
                s3_module.config = original_config
    finally:
        # Restore original environment variables
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


@pytest.fixture
def s3_service_pii_separate_bucket(
    mock_boto3_client: MagicMock,
    aws_config_pii_separate_bucket: Dict[str, Optional[str]]
):
    """
    S3Service instance configured with separate PII bucket.
    
    Enterprise-grade fixture that:
    - Configures separate PII bucket
    - Validates PII configuration
    - Ensures proper isolation
    
    Args:
        mock_boto3_client: Mocked boto3 S3 client
        aws_config_pii_separate_bucket: PII bucket configuration
        
    Yields:
        S3Service instance with separate PII bucket configuration
    """
    with mock_aws_environment(aws_config_pii_separate_bucket):
        with patch('boto3.client', return_value=mock_boto3_client):
            service = S3Service()
            
            # Enterprise-grade validation
            assert service.s3_client is not None, "S3 client should be initialized"
            assert service.pii_bucket == aws_config_pii_separate_bucket['AWS_S3_PII_BUCKET'], \
                "PII bucket should match configuration"
            assert service.pii_path == aws_config_pii_separate_bucket['AWS_S3_PII_PATH'], \
                "PII path should match configuration"
            
            yield service
            
            mock_boto3_client.reset_mock()


# ============================================================================
# Helper Functions
# ============================================================================

def create_s3_service_with_config(
    mock_boto3_client: MagicMock,
    config_dict: Dict[str, Optional[str]]
) -> S3Service:
    """
    Enterprise-grade helper to create S3Service with custom configuration.
    
    Properly handles:
    - Environment variable setup
    - Boto3 client mocking
    - Service initialization
    - Resource cleanup
    
    Args:
        mock_boto3_client: Mocked boto3 client
        config_dict: Configuration dictionary
        
    Returns:
        S3Service instance
        
    Note:
        This function uses context managers internally, so the service
        should be used within the same context or environment variables
        should be managed externally.
    """
    env_vars = build_env_vars_from_config(config_dict)
    
    with patch.dict(os.environ, env_vars, clear=False):
        with patch('boto3.client', return_value=mock_boto3_client):
            service = S3Service()
            # Ensure mocked client is used
            service.s3_client = mock_boto3_client
            return service


def assert_presigned_url_call(
    mock_client: MagicMock,
    operation: str,
    bucket: str,
    key: str,
    expires_in: int,
    content_type: Optional[str] = None
) -> None:
    """
    Enterprise-grade assertion helper for presigned URL generation calls.
    
    Validates:
    - Operation type (put_object/get_object)
    - Bucket name
    - S3 key
    - Expiration time
    - Content type (for PUT operations)
    
    Args:
        mock_client: Mocked boto3 client
        operation: S3 operation ('put_object' or 'get_object')
        bucket: Expected bucket name
        key: Expected S3 key
        expires_in: Expected expiration time in seconds
        content_type: Expected content type (for PUT operations)
        
    Raises:
        AssertionError: If any validation fails
    """
    # Verify method was called
    mock_client.generate_presigned_url.assert_called_once()
    call_args = mock_client.generate_presigned_url.call_args
    
    # Verify operation
    assert call_args[0][0] == operation, \
        f"Expected operation '{operation}', got '{call_args[0][0]}'"
    
    # Verify parameters
    params = call_args[1]['Params']
    assert params['Bucket'] == bucket, \
        f"Expected bucket '{bucket}', got '{params['Bucket']}'"
    assert params['Key'] == key, \
        f"Expected key '{key}', got '{params['Key']}'"
    
    if content_type:
        assert params.get('ContentType') == content_type, \
            f"Expected content type '{content_type}', got '{params.get('ContentType')}'"
    
    # Verify expiration
    assert call_args[1]['ExpiresIn'] == expires_in, \
        f"Expected expires_in {expires_in}, got {call_args[1]['ExpiresIn']}"


# ============================================================================
# Test Classes
# ============================================================================

class TestPresignedPutURL:
    """Comprehensive tests for presigned PUT URL generation"""
    
    def test_generate_presigned_put_url_success(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test successful presigned PUT URL generation with default expiry"""
        expected_url = "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type="application/pdf"
        )
        
        assert url == expected_url
        assert url is not None
        
        # Verify call parameters
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='put_object',
            bucket='test-bucket',
            key='test-key',
            expires_in=900,  # 15 minutes default
            content_type='application/pdf'
        )
    
    @pytest.mark.parametrize("expires_in,expected_expiry", [
        (300, 300),   # 5 minutes
        (1800, 1800), # 30 minutes
        (3600, 3600), # 1 hour
    ])
    def test_generate_presigned_put_url_custom_expiry(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock,
        expires_in: int,
        expected_expiry: int
    ) -> None:
        """Test presigned PUT URL with various custom expiry times"""
        expected_url = "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type="image/jpeg",
            expires_in=expires_in
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='put_object',
            bucket='test-bucket',
            key='test-key',
            expires_in=expected_expiry,
            content_type='image/jpeg'
        )
    
    @pytest.mark.parametrize("content_type", [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/octet-stream",
    ])
    def test_generate_presigned_put_url_content_types(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock,
        content_type: str
    ) -> None:
        """Test presigned PUT URL with various content types"""
        expected_url = f"https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type=content_type
        )
        
        assert url == expected_url
        call_args = mock_boto3_client.generate_presigned_url.call_args
        assert call_args[1]['Params']['ContentType'] == content_type
    
    def test_generate_presigned_put_url_pii_default_bucket(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test PII flag with default bucket (uses same bucket, different path)"""
        # When AWS_S3_PII_BUCKET is None, service uses bucket_name
        # The fixture already sets AWS_BUCKET_NAME, so this should work
        expected_url = "https://test-bucket.s3.amazonaws.com/kyc-documents/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type="application/pdf",
            is_pii=True
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='put_object',
            bucket='test-bucket',  # Same bucket (pii_bucket defaults to bucket_name)
            key='kyc-documents/test-key',  # Different path
            expires_in=900,
            content_type='application/pdf'
        )
    
    def test_generate_presigned_put_url_pii_separate_bucket(
        self,
        s3_service_pii_separate_bucket: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test PII flag with separate bucket configuration"""
        expected_url = "https://pii-bucket.s3.amazonaws.com/kyc-documents/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_pii_separate_bucket.generate_presigned_put_url(
            s3_key="test-key",
            content_type="application/pdf",
            is_pii=True
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='put_object',
            bucket='pii-bucket',  # Separate bucket
            key='kyc-documents/test-key',
            expires_in=900,
            content_type='application/pdf'
        )
    
    def test_generate_presigned_put_url_no_credentials(
        self,
        s3_service_no_creds: S3Service
    ) -> None:
        """Test presigned PUT URL generation without credentials returns None"""
        url = s3_service_no_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type="application/pdf"
        )
        
        assert url is None
    
    def test_generate_presigned_put_url_missing_bucket_name(
        self,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test presigned PUT URL generation with missing bucket name"""
        config = {
            'AWS_ACCESS_KEY_ID': 'test-key',
            'AWS_SECRET_ACCESS_KEY': 'test-secret',
            'AWS_BUCKET_NAME': None,  # Missing bucket
            'AWS_REGION': 'us-east-1',
        }
        
        # Use context manager to ensure proper isolation
        with mock_aws_environment(config):
            with patch('boto3.client', return_value=mock_boto3_client):
                # Patch config at the module level to prevent reading from .env files
                # and ensure None is returned for missing bucket name
                def config_side_effect(key: str, default=None):
                    """Return None for AWS_BUCKET_NAME, otherwise use mock_aws_environment values"""
                    if key == 'AWS_BUCKET_NAME':
                        return None
                    # For other keys, check if they're in the config dict
                    if key in config and config[key] is not None:
                        return config[key]
                    # Check environment (mock_aws_environment sets these)
                    if key in os.environ:
                        return os.environ[key]
                    return default
                
                # Get the module directly from sys.modules to avoid import issues
                s3_module = sys.modules['app.services.s3_service']
                
                # Store original config function
                original_config = s3_module.config
                
                try:
                    # Replace config in the module
                    # Since config is called in __init__, this will be used when creating the instance
                    s3_module.config = Mock(side_effect=config_side_effect)
                    
                    service = S3Service()
                    service.s3_client = mock_boto3_client
                    
                    url = service.generate_presigned_put_url(
                        s3_key="test-key",
                        content_type="application/pdf"
                    )
                    
                    assert url is None
                    mock_boto3_client.generate_presigned_url.assert_not_called()
                finally:
                    # Restore original config function
                    s3_module.config = original_config
    
    def test_generate_presigned_put_url_client_error(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test presigned PUT URL generation handles ClientError gracefully"""
        mock_boto3_client.generate_presigned_url.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            'put_object'
        )
        
        url = s3_service_with_creds.generate_presigned_put_url(
            s3_key="test-key",
            content_type="application/pdf"
        )
        
        assert url is None
    
    def test_generate_presigned_put_url_generic_exception(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test presigned PUT URL generation raises generic exceptions (not caught)"""
        mock_boto3_client.generate_presigned_url.side_effect = Exception("Unexpected error")
        
        # Service only catches ClientError, not generic exceptions
        with pytest.raises(Exception, match="Unexpected error"):
            s3_service_with_creds.generate_presigned_put_url(
                s3_key="test-key",
                content_type="application/pdf"
            )


class TestPresignedGetURL:
    """Comprehensive tests for presigned GET URL generation"""
    
    def test_generate_presigned_get_url_success(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test successful presigned GET URL generation with default expiry"""
        expected_url = "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_get_url(
            s3_key="test-key"
        )
        
        assert url == expected_url
        assert url is not None
        
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='get_object',
            bucket='test-bucket',
            key='test-key',
            expires_in=3600  # 1 hour default
        )
    
    @pytest.mark.parametrize("expires_in,expected_expiry", [
        (1800, 1800),  # 30 minutes
        (3600, 3600),  # 1 hour
        (7200, 7200),  # 2 hours
    ])
    def test_generate_presigned_get_url_custom_expiry(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock,
        expires_in: int,
        expected_expiry: int
    ) -> None:
        """Test presigned GET URL with various custom expiry times"""
        expected_url = "https://test-bucket.s3.amazonaws.com/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_get_url(
            s3_key="test-key",
            expires_in=expires_in
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='get_object',
            bucket='test-bucket',
            key='test-key',
            expires_in=expected_expiry
        )
    
    def test_generate_presigned_get_url_pii_default_bucket(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test PII flag with default bucket (uses same bucket, different path)"""
        # When AWS_S3_PII_BUCKET is None, service uses bucket_name
        expected_url = "https://test-bucket.s3.amazonaws.com/kyc-documents/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_with_creds.generate_presigned_get_url(
            s3_key="test-key",
            is_pii=True
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='get_object',
            bucket='test-bucket',  # Same bucket (pii_bucket defaults to bucket_name)
            key='kyc-documents/test-key',
            expires_in=3600
        )
    
    def test_generate_presigned_get_url_pii_separate_bucket(
        self,
        s3_service_pii_separate_bucket: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test PII flag with separate bucket configuration"""
        expected_url = "https://pii-bucket.s3.amazonaws.com/kyc-documents/test-key?X-Amz-Algorithm=..."
        mock_boto3_client.generate_presigned_url.return_value = expected_url
        
        url = s3_service_pii_separate_bucket.generate_presigned_get_url(
            s3_key="test-key",
            is_pii=True
        )
        
        assert url == expected_url
        assert_presigned_url_call(
            mock_client=mock_boto3_client,
            operation='get_object',
            bucket='pii-bucket',
            key='kyc-documents/test-key',
            expires_in=3600
        )
    
    def test_generate_presigned_get_url_no_credentials(
        self,
        s3_service_no_creds: S3Service
    ) -> None:
        """Test presigned GET URL generation without credentials returns None"""
        url = s3_service_no_creds.generate_presigned_get_url(
            s3_key="test-key"
        )
        
        assert url is None
    
    def test_generate_presigned_get_url_client_error(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test presigned GET URL generation handles ClientError gracefully"""
        mock_boto3_client.generate_presigned_url.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
            'get_object'
        )
        
        url = s3_service_with_creds.generate_presigned_get_url(
            s3_key="test-key"
        )
        
        assert url is None


class TestS3KeyGeneration:
    """Comprehensive tests for S3 key generation"""
    
    def test_generate_s3_key_with_extension(
        self,
        s3_service_with_creds: S3Service
    ) -> None:
        """Test S3 key generation with user_id, document_type, and file extension"""
        s3_key = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_front",
            file_extension=".pdf"
        )
        
        assert s3_key.startswith("users/123/id_front/")
        assert s3_key.endswith(".pdf")
        assert "id_front_" in s3_key
        # Verify UUID is included (format: id_front_<uuid>.pdf)
        parts = s3_key.split("/")
        filename = parts[-1]
        assert filename.startswith("id_front_")
        assert filename.endswith(".pdf")
    
    def test_generate_s3_key_no_extension(
        self,
        s3_service_with_creds: S3Service
    ) -> None:
        """Test S3 key generation without file extension"""
        s3_key = s3_service_with_creds.generate_s3_key(
            user_id=456,
            document_type="proof_of_address"
        )
        
        assert s3_key.startswith("users/456/proof_of_address/")
        assert "proof_of_address_" in s3_key
        # Verify no extension
        parts = s3_key.split("/")
        filename = parts[-1]
        assert filename.startswith("proof_of_address_")
        assert "." not in filename
    
    def test_generate_s3_key_unique(
        self,
        s3_service_with_creds: S3Service
    ) -> None:
        """Test that generated S3 keys are unique (UUID-based)"""
        key1 = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_front",
            file_extension=".pdf"
        )
        key2 = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_front",
            file_extension=".pdf"
        )
        
        assert key1 != key2  # Should be unique due to UUID
    
    def test_generate_s3_key_different_users(
        self,
        s3_service_with_creds: S3Service
    ) -> None:
        """Test S3 key generation for different users"""
        key1 = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_front",
            file_extension=".pdf"
        )
        key2 = s3_service_with_creds.generate_s3_key(
            user_id=456,
            document_type="id_front",
            file_extension=".pdf"
        )
        
        assert key1.startswith("users/123/")
        assert key2.startswith("users/456/")
        assert key1 != key2
    
    def test_generate_s3_key_different_document_types(
        self,
        s3_service_with_creds: S3Service
    ) -> None:
        """Test S3 key generation for different document types"""
        key1 = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_front",
            file_extension=".pdf"
        )
        key2 = s3_service_with_creds.generate_s3_key(
            user_id=123,
            document_type="id_back",
            file_extension=".pdf"
        )
        
        assert "id_front" in key1
        assert "id_back" in key2
        assert key1 != key2


class TestDeleteObject:
    """Comprehensive tests for S3 object deletion"""
    
    def test_delete_object_success(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test successful object deletion"""
        result = s3_service_with_creds.delete_object(
            s3_key="test-key"
        )
        
        assert result is True
        mock_boto3_client.delete_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='test-key'
        )
    
    def test_delete_object_pii_default_bucket(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test object deletion with PII flag using default bucket"""
        # When AWS_S3_PII_BUCKET is None, service uses bucket_name
        result = s3_service_with_creds.delete_object(
            s3_key="test-key",
            is_pii=True
        )
        
        assert result is True
        mock_boto3_client.delete_object.assert_called_once_with(
            Bucket='test-bucket',  # Same bucket (pii_bucket defaults to bucket_name)
            Key='kyc-documents/test-key'
        )
    
    def test_delete_object_pii_separate_bucket(
        self,
        s3_service_pii_separate_bucket: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test object deletion with PII flag using separate bucket"""
        result = s3_service_pii_separate_bucket.delete_object(
            s3_key="test-key",
            is_pii=True
        )
        
        assert result is True
        mock_boto3_client.delete_object.assert_called_once_with(
            Bucket='pii-bucket',
            Key='kyc-documents/test-key'
        )
    
    def test_delete_object_no_credentials(
        self,
        s3_service_no_creds: S3Service
    ) -> None:
        """Test object deletion without credentials returns False"""
        result = s3_service_no_creds.delete_object(
            s3_key="test-key"
        )
        
        assert result is False
    
    def test_delete_object_client_error(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test object deletion handles ClientError gracefully"""
        mock_boto3_client.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
            'delete_object'
        )
        
        result = s3_service_with_creds.delete_object(
            s3_key="test-key"
        )
        
        assert result is False
    
    def test_delete_object_access_denied(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test object deletion handles AccessDenied error"""
        mock_boto3_client.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            'delete_object'
        )
        
        result = s3_service_with_creds.delete_object(
            s3_key="test-key"
        )
        
        assert result is False
    
    def test_delete_object_generic_exception(
        self,
        s3_service_with_creds: S3Service,
        mock_boto3_client: MagicMock
    ) -> None:
        """Test object deletion raises generic exceptions (not caught)"""
        mock_boto3_client.delete_object.side_effect = Exception("Unexpected error")
        
        # Service only catches ClientError, not generic exceptions
        with pytest.raises(Exception, match="Unexpected error"):
            s3_service_with_creds.delete_object(
                s3_key="test-key"
            )
