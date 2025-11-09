# Role-Aware Property CRUD Implementation Plan

**Date**: 2025-11-08  
**Status**: Pre-Implementation - Awaiting Approval  
**Purpose**: Enterprise-grade role-aware Property CRUD system implementation

---

## 🔍 Requirements Analysis & Contradictions

### ✅ **What Aligns with Current Models**

1. **Roles**: All required roles exist ✅
   - ADMIN, AGENT, SELLER, LANDLORD, INVESTOR, BUYER, TENANT
   - Location: `app/models/user.py` - `UserRoles` class

2. **Enums**: Property enums exist ✅
   - `PropertyType`: house, apartment, condo, etc.
   - `PropertyStatus`: draft, active, deleted, etc. (includes DELETED)
   - `ListingType`: for_sale, for_rent, for_lease, for_auction
   - All configured with `native_enum=True` and `values_callable`

3. **Soft Delete**: Property model supports soft delete ✅
   - `is_active` flag exists
   - `status` enum has `DELETED` value

### ⚠️ **Contradictions & Decisions Required**

#### 1. **"Portfolio" Listing Type** ❌ **CRITICAL**

**Issue**: Requirements state "Investor: only portfolio" but `ListingType` enum doesn't have `for_portfolio`.

**Current ListingType values**:
- `FOR_SALE = "for_sale"`
- `FOR_RENT = "for_rent"`
- `FOR_LEASE = "for_lease"`
- `FOR_AUCTION = "for_auction"`

**Options**:
- **Option A**: Add `FOR_PORTFOLIO = "for_portfolio"` to `ListingType` enum
  - Requires database migration
  - More explicit, aligns with requirements
- **Option B**: Use existing `FOR_SALE` or `FOR_RENT` for investor properties
  - No migration needed
  - Less explicit, may confuse investors vs sellers/landlords
- **Option C**: Use a different approach (e.g., property flag `is_portfolio`)
  - Requires schema change
  - More flexible but adds complexity

**Recommendation**: **Option A** - Add `FOR_PORTFOLIO` to maintain clarity and align with requirements.

---

#### 2. **Soft Delete Implementation** ⚠️ **NEEDS CLARIFICATION**

**Current Implementation**:
```python
# Current: Uses is_active flag
property.is_active = False
```

**Requirements State**:
- "Soft-delete preferred (status=deleted)"

**Issue**: Property model has BOTH:
- `is_active` (Boolean flag)
- `status` (Enum with DELETED value)

**Options**:
- **Option A**: Use only `status=DELETED` (aligns with requirements)
  - Remove `is_active = False` logic
  - Filter queries: `status != DELETED` instead of `is_active == True`
  - Simpler, single source of truth
- **Option B**: Use both `status=DELETED` AND `is_active=False`
  - More defensive, double-check
  - Redundant but safer
- **Option C**: Keep `is_active` for soft-delete, use `status` for business logic
  - `is_active=False` = soft deleted
  - `status=DELETED` = business state (sold, rented, etc.)
  - More nuanced but potentially confusing

**Recommendation**: **Option A** - Use `status=DELETED` only, as per requirements. This is cleaner and aligns with the requirement. We can keep `is_active` for other purposes (e.g., temporary deactivation) but use `status=DELETED` for soft-delete.

**Query Filtering Strategy**:
- Public/Guests: `status == ACTIVE AND is_active == True`
- Owners: `owner_id == user_id OR status == ACTIVE`
- Admin: No status filter (all properties)

---

## 🏗️ Architecture Design

### 1. **Authorization Dependencies** (New File)

**File**: `app/dependencies/authorization_dependencies.py`

```python
# Proposed structure:
- get_admin_user() -> User  # Admin-only dependency
- get_optional_user() -> Optional[User]  # Optional auth for public endpoints
- require_roles(*roles: str) -> Callable  # Reusable role checker factory
```

**Purpose**: Centralize authorization logic, avoid code duplication.

---

### 2. **Service Layer Enhancements**

**File**: `app/services/property_service.py`

**New Methods**:
```python
# Role-aware query methods
- get_properties_for_role(user: Optional[User], filters: dict) -> List[Property]
- get_all_properties_admin(filters: dict) -> List[Property]
- get_public_properties(filters: dict) -> List[Property]

# CRUD with role checks
- create_property_with_role_check(property_data, user: User) -> Property
- update_property_with_role_check(property_id, property_data, user: User) -> Property
- delete_property_with_role_check(property_id, user: User) -> bool

# Permission helpers
- can_create_listing_type(user: User, listing_type: ListingType) -> bool
- can_update_property(user: User, property: Property) -> bool
- can_delete_property(user: User, property: Property) -> bool
```

**Purpose**: Business logic layer enforces permissions, not just route layer.

---

### 3. **Permission Matrix Implementation**

**File**: `app/services/property_permissions.py` (New)

```python
# Centralized permission logic
LISTING_TYPE_PERMISSIONS = {
    "admin": [ListingType.FOR_SALE, ListingType.FOR_RENT, ListingType.FOR_LEASE, ListingType.FOR_AUCTION, ListingType.FOR_PORTFOLIO],
    "seller": [ListingType.FOR_SALE],
    "agent": [ListingType.FOR_SALE, ListingType.FOR_RENT],
    "landlord": [ListingType.FOR_RENT],
    "investor": [ListingType.FOR_PORTFOLIO],
    "buyer": [],
    "tenant": []
}
```

**Purpose**: Single source of truth for permissions, easy to maintain.

---

## 📋 Implementation Steps

### Phase 1: Foundation (Authorization & Permissions)

#### Step 1.1: Add `FOR_PORTFOLIO` to ListingType Enum
- **File**: `app/models/property.py`
- **Change**: Add `FOR_PORTFOLIO = "for_portfolio"` to `ListingType`
- **Migration**: Create Alembic migration to add `for_portfolio` to PostgreSQL enum
- **Impact**: Database migration required

#### Step 1.2: Create Authorization Dependencies
- **File**: `app/dependencies/authorization_dependencies.py` (New)
- **Content**:
  ```python
  def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
      """Dependency that ensures user is admin"""
      if not current_user.has_role("admin"):
          raise HTTPException(403, "Admin access required")
      return current_user
  
  def get_optional_user(
      token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)),
      db: Session = Depends(get_db)
  ) -> Optional[User]:
      """Optional authentication - returns user if authenticated, None if not"""
      if not token:
          return None
      try:
          auth_service = AuthService(db)
          email = auth_service.verify_token(token)
          user_service = UserService(db)
          return user_service.get_user_by_email(email)
      except:
          return None
  ```

#### Step 1.3: Create Permission Service
- **File**: `app/services/property_permissions.py` (New)
- **Content**: Permission matrix and helper functions
- **Purpose**: Centralized permission logic

---

### Phase 2: Service Layer Enhancements

#### Step 2.1: Update Soft Delete to Use `status=DELETED`
- **File**: `app/services/property_service.py`
- **Change**: 
  ```python
  # OLD:
  property.is_active = False
  
  # NEW:
  property.status = PropertyStatus.DELETED
  property.is_active = False  # Also set for consistency
  ```

#### Step 2.2: Add Role-Aware Query Methods
- **File**: `app/services/property_service.py`
- **Methods**:
  ```python
  def get_properties_for_role(
      self, 
      user: Optional[User],
      filters: PropertySearchFilters,
      skip: int = 0,
      limit: int = 20
  ) -> Tuple[List[Property], int]:
      """
      Role-aware property listing.
      
      - Public/Guest: Only ACTIVE properties
      - Owner roles: ACTIVE + their own properties (any status)
      - Admin: All properties (any status)
      """
      query = self.db.query(Property)
      
      # Role-based filtering
      if not user:
          # Public: Only ACTIVE
          query = query.filter(
              Property.status == PropertyStatus.ACTIVE,
              Property.is_active == True
          )
      elif user.has_role("admin"):
          # Admin: All properties (no status filter)
          pass
      elif user.has_role("seller") or user.has_role("agent") or user.has_role("landlord") or user.has_role("investor"):
          # Owners: ACTIVE + their own (any status)
          query = query.filter(
              or_(
                  and_(
                      Property.status == PropertyStatus.ACTIVE,
                      Property.is_active == True
                  ),
                  Property.owner_id == user.id
              )
          )
      else:
          # Buyer/Tenant: Only ACTIVE
          query = query.filter(
              Property.status == PropertyStatus.ACTIVE,
              Property.is_active == True
          )
      
      # Apply additional filters (price, location, etc.)
      # ... existing filter logic ...
      
      total_count = query.count()
      properties = query.offset(skip).limit(limit).all()
      return properties, total_count
  ```

#### Step 2.3: Add CRUD Permission Checks
- **File**: `app/services/property_service.py`
- **Methods**:
  ```python
  def can_create_listing_type(self, user: User, listing_type: ListingType) -> bool:
      """Check if user can create property with given listing_type"""
      from app.services.property_permissions import LISTING_TYPE_PERMISSIONS
      
      for role in user.roles:
          if listing_type in LISTING_TYPE_PERMISSIONS.get(role, []):
              return True
      return False
  
  def create_property_with_role_check(
      self, 
      property_data: PropertyCreate, 
      user: User
  ) -> Property:
      """Create property with role-based permission check"""
      # Check listing_type permission
      if property_data.listing_type:
          if not self.can_create_listing_type(user, property_data.listing_type):
              raise ValueError(f"User role does not allow creating {property_data.listing_type.value} properties")
      
      # Create property
      return self.create_property(property_data, user.id)
  ```

---

### Phase 3: Route Layer Updates

#### Step 3.1: Update `GET /api/properties/` - Role-Aware
- **File**: `app/routes/properties.py`
- **Changes**:
  - Add optional `current_user: Optional[User] = Depends(get_optional_user)`
  - Call `get_properties_for_role(user, filters)`
  - Return role-filtered results

#### Step 3.2: Add `GET /api/properties/all` - Admin Only
- **File**: `app/routes/properties.py`
- **Endpoint**: Admin-only, returns all properties (including deleted)
- **Dependency**: `get_admin_user`

#### Step 3.3: Update `POST /api/properties/` - Role-Aware Create
- **File**: `app/routes/properties.py`
- **Changes**:
  - Use `create_property_with_role_check()`
  - Validate listing_type permission
  - Return 403 if permission denied

#### Step 3.4: Update `PUT /api/properties/{id}` - Role-Aware Update
- **File**: `app/routes/properties.py`
- **Changes**:
  - Check ownership OR admin role
  - Validate listing_type permission if changing
  - Use `update_property_with_role_check()`

#### Step 3.5: Update `DELETE /api/properties/{id}` - Role-Aware Soft Delete
- **File**: `app/routes/properties.py`
- **Changes**:
  - Check ownership OR admin role
  - Use `status=DELETED` instead of `is_active=False`
  - Log deletion with audit trail

---

### Phase 4: Audit Logging

#### Step 4.1: Add Audit Logging to Service Methods
- **File**: `app/services/property_service.py`
- **Changes**: Add structured logging for all CRUD operations
- **Log Events**:
  - `property_created` - with user_id, listing_type, property_id
  - `property_updated` - with user_id, property_id, changed_fields
  - `property_deleted` - with user_id, property_id, reason
  - `property_access_denied` - with user_id, property_id, reason

---

### Phase 5: Query Parameter Validation

#### Step 5.1: Enhance Enum Conversion
- **File**: `app/routes/properties.py`
- **Changes**: 
  - Convert string query params to enums
  - Normalize empty strings to None
  - Validate enum values (return 422 for invalid)
  - Support multi-value filters (comma-separated)

---

## 🔒 Security Considerations

### 1. **Server-Side Enforcement**
- ✅ All permission checks in service layer
- ✅ Route layer validates but service enforces
- ✅ Database queries filter by role

### 2. **Query-Level Filtering**
- ✅ Filter at SQLAlchemy level, not application level
- ✅ Use `or_()` and `and_()` for complex role logic
- ✅ Never return all properties to non-admin users

### 3. **Audit Trail**
- ✅ Log all CRUD operations with user context
- ✅ Log permission denials
- ✅ Include request_id for correlation

---

## 📊 Database Migration Plan

### Migration 1: Add `for_portfolio` to ListingType Enum

**File**: `alembic/versions/XXXXX_add_portfolio_listing_type.py`

```python
def upgrade():
    # Add for_portfolio to existing listingtype enum
    op.execute("ALTER TYPE listingtype ADD VALUE IF NOT EXISTS 'for_portfolio'")

def downgrade():
    # Note: PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum type
    pass
```

**Note**: PostgreSQL enum alterations are complex. We may need to:
1. Convert column to text
2. Drop old enum
3. Create new enum with all values
4. Convert back

---

## 🧪 Testing Strategy

### Unit Tests
- Permission matrix validation
- Role-based query filtering
- CRUD permission checks
- Enum validation

### Integration Tests
- Endpoint access control
- Role-aware filtering
- Soft delete behavior
- Audit logging

### Security Tests
- Unauthorized access attempts
- Permission bypass attempts
- Enum injection attempts

---

## 📝 Files to Create/Modify

### New Files
1. `app/dependencies/authorization_dependencies.py`
2. `app/services/property_permissions.py`
3. `alembic/versions/XXXXX_add_portfolio_listing_type.py`

### Modified Files
1. `app/models/property.py` - Add FOR_PORTFOLIO
2. `app/services/property_service.py` - Role-aware methods
3. `app/routes/properties.py` - Role-aware endpoints
4. `app/schemas/property.py` - Update if needed

---

## ⚠️ Decisions Required Before Implementation

### Decision 1: Portfolio Listing Type
- [ ] **Approve**: Add `FOR_PORTFOLIO = "for_portfolio"` to `ListingType` enum
- [ ] **Alternative**: Use existing listing types for investors

### Decision 2: Soft Delete Strategy
- [ ] **Approve**: Use `status=DELETED` for soft delete (as per requirements)
- [ ] **Alternative**: Keep using `is_active=False` or use both

### Decision 3: Query Filtering
- [ ] **Approve**: Filter deleted properties: `status != DELETED` in queries
- [ ] **Alternative**: Use `is_active == True` only

---

## ✅ Implementation Checklist

### Pre-Implementation
- [ ] Review and approve contradictions
- [ ] Approve architecture design
- [ ] Approve database migration plan

### Phase 1: Foundation
- [ ] Add FOR_PORTFOLIO to ListingType enum
- [ ] Create database migration
- [ ] Create authorization dependencies
- [ ] Create permission service

### Phase 2: Service Layer
- [ ] Update soft delete to use status=DELETED
- [ ] Add role-aware query methods
- [ ] Add CRUD permission checks
- [ ] Add audit logging

### Phase 3: Route Layer
- [ ] Update GET /api/properties/ (role-aware)
- [ ] Add GET /api/properties/all (admin)
- [ ] Update POST /api/properties/ (role-aware)
- [ ] Update PUT /api/properties/{id} (role-aware)
- [ ] Update DELETE /api/properties/{id} (role-aware)

### Phase 4: Testing
- [ ] Unit tests for permissions
- [ ] Integration tests for endpoints
- [ ] Security tests

### Phase 5: Documentation
- [ ] Update API_ENDPOINTS.md
- [ ] Update README if needed

---

## 🎯 Success Criteria

### Functional
- ✅ All roles can only create allowed listing types
- ✅ Public users see only ACTIVE properties
- ✅ Owners see ACTIVE + their own properties
- ✅ Admins see all properties
- ✅ Soft delete uses status=DELETED
- ✅ All CRUD operations logged

### Non-Functional
- ✅ Performance: Role filtering at database level
- ✅ Security: All checks server-side
- ✅ Maintainability: Centralized permissions
- ✅ Auditability: All operations logged

---

## 📌 Notes

1. **Backward Compatibility**: Existing endpoints will continue to work but with enhanced filtering
2. **Performance**: Role-based queries use database-level filtering (no N+1 queries)
3. **Future Enhancements**: Can add field-level filtering, agent assignments, etc.

---

**Status**: Awaiting Approval  
**Next Steps**: Review contradictions, approve decisions, then proceed with implementation

