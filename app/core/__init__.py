"""
Core application utilities
"""

from .feature_flags import FeatureFlags, feature_flags, is_enabled_sync

__all__ = [
    "FeatureFlags",
    "feature_flags",
    "is_enabled_sync"
]