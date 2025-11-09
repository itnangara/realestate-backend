"""
KYC Provider Factory for creating provider instances

Handles provider selection based on environment configuration.
"""

from decouple import config
from typing import Optional
from app.services.kyc_service import KYCProvider, MockKYCProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_kyc_provider() -> KYCProvider:
    """
    Get KYC provider instance based on environment configuration.
    
    Returns:
        KYCProvider instance (MockKYCProvider by default, or configured provider)
        
    Environment variables:
        KYC_PROVIDER: Provider name ("mock", "sumsub", etc.)
        KYC_PROVIDER_API_KEY: Provider API key (if required)
        KYC_PROVIDER_API_SECRET: Provider API secret (if required)
    """
    provider_name = config("KYC_PROVIDER", default="mock").lower()
    
    if provider_name == "mock":
        logger.info("using_mock_kyc_provider")
        return MockKYCProvider()
    elif provider_name == "sumsub":
        # TODO: Implement SumsubKYCProvider when ready
        logger.warning(
            "sumsub_provider_not_implemented",
            message="Sumsub provider not yet implemented, falling back to mock"
        )
        return MockKYCProvider()
    else:
        logger.warning(
            "unknown_kyc_provider",
            provider=provider_name,
            message=f"Unknown provider '{provider_name}', using mock"
        )
        return MockKYCProvider()

