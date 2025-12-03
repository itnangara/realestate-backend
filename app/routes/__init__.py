"""
Routes package initialization
"""

from . import (
    auth,
    properties,
    users,
    documents,
    webhooks,
    admin,
    admin_users,
    tenant,
    landlord,
    seller,
    role_routes,
    favorites,
    maintenance,
    maintenance_staff,
    lease,
    lease_sse,
)

__all__ = [
    "auth",
    "properties",
    "users",
    "documents",
    "webhooks",
    "admin",
    "admin_users",
    "tenant",
    "landlord",
    "seller",
    "role_routes",
    "favorites",
    "maintenance",
    "maintenance_staff",
    "lease",
    "lease_sse",
]



