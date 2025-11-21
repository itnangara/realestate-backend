"""
Enterprise-grade property permissions service.

Centralized permission logic for role-based property CRUD operations.
"""

from typing import List, Optional
from app.models.user import User
from app.models.property import Property, ListingType, PropertyStatus


# Permission matrix: which roles can create which listing types
LISTING_TYPE_CREATE_PERMISSIONS = {
    "admin": [
        ListingType.FOR_SALE,
        ListingType.FOR_RENT,
        ListingType.FOR_LEASE,
        ListingType.FOR_AUCTION,
        ListingType.FOR_PORTFOLIO
    ],
    "seller": [ListingType.FOR_SALE],
    "agent": [ListingType.FOR_SALE, ListingType.FOR_RENT],
    "landlord": [ListingType.FOR_RENT],
    "investor": [ListingType.FOR_PORTFOLIO],
    "buyer": [],
    "tenant": []
}

# Public-visible listing types (for public/guest/buyer/tenant)
# Enterprise-grade: Explicitly defines which listing types are public-facing
# FOR_PORTFOLIO is explicitly EXCLUDED - it is private (investor-only) and NEVER visible to public
# FOR_AUCTION is also excluded - not part of public browsing
PUBLIC_LISTING_TYPES = [
    ListingType.FOR_SALE,
    ListingType.FOR_RENT,
    ListingType.FOR_LEASE
    # FOR_PORTFOLIO is NOT included - it is private (investor-only)
    # FOR_AUCTION is NOT included - not part of public browsing
]


class PropertyPermissionService:
    """Enterprise-grade permission service for property operations"""
    
    @staticmethod
    def can_create_listing_type(user: User, listing_type: ListingType) -> bool:
        """
        Check if user can create a property with the given listing type.
        
        Args:
            user: The user attempting to create
            listing_type: The listing type to create
            
        Returns:
            True if user has permission, False otherwise
        """
        for role in user.roles:
            if listing_type in LISTING_TYPE_CREATE_PERMISSIONS.get(role, []):
                return True
        return False
    
    @staticmethod
    def can_read_property(user: Optional[User], property: Property) -> bool:
        """
        Check if user can read/view a property.
        
        Rules:
        - Public/Guest: Only ACTIVE + public listing types
        - Buyer/Tenant: Same as public
        - Owners: ACTIVE + their own properties (any status)
        - Admin: All properties
        
        Args:
            user: The user (None for public/guest)
            property: The property to check
            
        Returns:
            True if user can read, False otherwise
        """
        # Admin can read everything
        if user and user.has_role("admin"):
            return True
        
        # Soft-deleted properties are not visible (except to admin)
        if property.status == PropertyStatus.DELETED:
            return False
        
        # Public access check: ACTIVE + public listing types
        # Enterprise-grade: BOTH conditions must be satisfied simultaneously:
        # 1. status = ACTIVE (property is publicly listed)
        # 2. listing_type IN [FOR_SALE, FOR_RENT, FOR_LEASE] (only public-facing types)
        # FOR_PORTFOLIO is explicitly excluded - never visible to public
        is_public_listing = (
            property.status == PropertyStatus.ACTIVE
            and property.is_active
            and property.listing_type in PUBLIC_LISTING_TYPES
        )
        
        # Public/Guest/Buyer/Tenant: Can view public listings
        # Includes authenticated users with no roles (treat as public)
        if not user or not user.roles or user.has_role("buyer") or user.has_role("tenant"):
            return is_public_listing
        
        # Owner roles: Can view their own properties (any status) OR public listings
        owner_roles = ["seller", "agent", "landlord", "investor"]
        if any(user.has_role(role) for role in owner_roles):
            # Own property: can see any status (except DELETED, which is filtered above)
            if property.owner_id == user.id:
                return True
            # Not own property: can view public listings
            return is_public_listing
        
        # Fallback: Any authenticated user can view public listings
        # This ensures users with unrecognized roles can still browse public marketplace
        return is_public_listing
    
    @staticmethod
    def can_update_property(user: User, property: Property) -> bool:
        """
        Check if user can update a property.
        
        Enterprise-grade ownership check: Always verifies ownership before allowing update.
        
        Rules:
        - Admin: Can update any property (bypasses ownership check)
        - Owners: Can update ONLY their own properties (explicit ownership check: property.owner_id == user.id)
        
        Args:
            user: The user attempting to update
            property: The property to update
            
        Returns:
            True if user can update, False otherwise
        """
        # Admin can update anything (bypasses ownership check)
        if user.has_role("admin"):
            return True
        
        # Enterprise-grade: Explicit ownership check for owner roles
        # Owners can update ONLY their own properties
        owner_roles = ["seller", "agent", "landlord", "investor"]
        if any(user.has_role(role) for role in owner_roles):
            # Explicit ownership verification: property must belong to user
            return property.owner_id == user.id
        
        return False
    
    @staticmethod
    def can_delete_property(user: User, property: Property) -> bool:
        """
        Check if user can delete a property.
        
        Enterprise-grade ownership check: Always verifies ownership before allowing delete.
        
        Rules:
        - Admin: Can delete any property (bypasses ownership check)
        - Owners: Can delete ONLY their own properties (explicit ownership check: property.owner_id == user.id)
        
        Args:
            user: The user attempting to delete
            property: The property to delete
            
        Returns:
            True if user can delete, False otherwise
        """
        # Enterprise-grade: Explicit ownership check (same as update)
        # Admin can delete anything (bypasses ownership check)
        if user.has_role("admin"):
            return True
        
        # Explicit ownership verification: property must belong to user
        owner_roles = ["seller", "agent", "landlord", "investor"]
        if any(user.has_role(role) for role in owner_roles):
            # Explicit ownership check: property.owner_id == user.id
            return property.owner_id == user.id
        
        return False
    
    @staticmethod
    def get_visible_listing_types(user: Optional[User]) -> List[ListingType]:
        """
        Get list of listing types visible to the user.
        
        Args:
            user: The user (None for public/guest)
            
        Returns:
            List of visible listing types
        """
        if not user:
            return PUBLIC_LISTING_TYPES
        
        if user.has_role("admin"):
            return list(ListingType)  # All types
        
        # Buyer/Tenant: Only public types
        if user.has_role("buyer") or user.has_role("tenant"):
            return PUBLIC_LISTING_TYPES
        
        # Owner roles: Public types + their own portfolio type
        owner_roles = ["seller", "agent", "landlord", "investor"]
        if any(user.has_role(role) for role in owner_roles):
            visible = list(PUBLIC_LISTING_TYPES)
            # Add their specific portfolio type if they have it
            if user.has_role("investor"):
                visible.append(ListingType.FOR_PORTFOLIO)
            return visible
        
        return PUBLIC_LISTING_TYPES
    
    @staticmethod
    def get_owner_listing_types(user: User, role_context: Optional[str] = None) -> List[ListingType]:
        """
        Get listing types that an owner role can create/own.
        
        Used for "My Listings" filtering to show only properties
        the user's role is allowed to own.
        
        Args:
            user: The authenticated user with owner role
            role_context: Optional role context (seller, agent, landlord, investor)
                         If provided, filters by this specific role only.
                         Must be one of the user's roles.
            
        Returns:
            List of ListingType enums the user's role(s) can own
        """
        owner_roles = ["seller", "agent", "landlord", "investor"]
        allowed_types = []
        
        # Role-context-aware filtering: if role_context provided, use only that role
        if role_context:
            # Validate role_context is one of user's roles
            if role_context not in user.roles:
                # Invalid role context - return empty list (user doesn't have this role)
                return []
            
            # Validate role_context is an owner role
            if role_context in owner_roles and role_context in LISTING_TYPE_CREATE_PERMISSIONS:
                allowed_types.extend(LISTING_TYPE_CREATE_PERMISSIONS[role_context])
        else:
            # Backward compatible: union of all user's owner roles
            for role in user.roles:
                if role in owner_roles and role in LISTING_TYPE_CREATE_PERMISSIONS:
                    allowed_types.extend(LISTING_TYPE_CREATE_PERMISSIONS[role])
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(allowed_types))

