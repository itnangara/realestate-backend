# Application Endpoint Testing - RCA Framework

## Test File
`test_application_endpoints_rca.py` - Comprehensive test suite following RCA Framework principles

## Running Tests

### Run all application endpoint tests:
```bash
pytest tests/applications/test_application_endpoints_rca.py -v
```

### Run specific test class:
```bash
pytest tests/applications/test_application_endpoints_rca.py::TestTenantEndpoints -v
pytest tests/applications/test_application_endpoints_rca.py::TestLandlordEndpoints -v
pytest tests/applications/test_application_endpoints_rca.py::TestBusinessRules -v
pytest tests/applications/test_application_endpoints_rca.py::TestCompleteStatusFlow -v
```

### Run with output:
```bash
pytest tests/applications/test_application_endpoints_rca.py -v -s
```

## Test Coverage

### ✅ Tenant Endpoints
- `POST /api/tenant/applications` - Create application (starts in DRAFT)
- `GET /api/tenant/applications` - List tenant's applications (only own)
- `GET /api/tenant/applications/{id}` - Get application by ID
- `PATCH /api/tenant/applications/{id}` - Update application (status transitions)
- `POST /api/tenant/applications/{id}/documents` - Attach documents

### ✅ Landlord Endpoints
- `GET /api/landlord/applications` - List landlord's applications (only own properties)
- `GET /api/landlord/applications/{id}` - Get application by ID
- `GET /api/landlord/properties/{property_id}/applications` - Get property applications
- `POST /api/landlord/applications/{id}/approve` - Approve application
- `POST /api/landlord/applications/{id}/reject` - Reject application
- `POST /api/landlord/applications/{id}/request-info` - Request more information
- `POST /api/landlord/applications/{id}/sign` - Sign lease
- `POST /api/landlord/applications/{id}/activate` - Activate lease

### ✅ Admin Endpoints
- `GET /api/admin/applications` - List all applications
- `GET /api/admin/applications/{id}` - Get application by ID

### ✅ Status Transitions
- DRAFT → SUBMITTED → REVIEWED (automatic)
- NEEDS_INFO → SUBMITTED → REVIEWED (automatic)
- REVIEWED → APPROVED (landlord)
- REVIEWED → REJECTED (landlord)
- REVIEWED → NEEDS_INFO (landlord)
- APPROVED → SIGNED (landlord/tenant)
- SIGNED → ACTIVE_LEASE (landlord/tenant)

### ✅ Business Rules
- Cannot apply if tenant has active lease
- Cannot apply twice to same property (unless rejected/withdrawn)
- Property must be active and available
- Auto-withdraw other applications when lease is signed/activated
- Cannot edit application after SUBMITTED (unless NEEDS_INFO)
- Can only attach own documents
- Can only attach to own applications

### ✅ Authorization
- Tenant sees only their own applications
- Landlord sees only applications for their properties
- Admin sees all applications
- Proper 403 errors for unauthorized access

## RCA Framework Application

### Step 1: Observe & Document
Each test documents:
- Expected behavior
- Status codes
- Response structure
- Error messages

### Step 2: Instrument
Tests include print statements showing:
- Status transitions
- Application counts
- Authorization checks
- Business rule validations

### Step 3: Analyze
Tests verify:
- Status transitions are enforced
- Business rules are validated
- Authorization is correct
- Error handling works

### Step 4: Verify
All tests assert:
- Correct status codes
- Correct response data
- Correct business logic
- Correct authorization

## Expected Test Results

All tests should pass with output like:
```
✅ Application created with status: draft
✅ Status transition: DRAFT → SUBMITTED → REVIEWED (final: reviewed)
✅ Tenant sees only 1 application(s) (their own)
✅ Landlord sees only 1 application(s) (for their properties)
✅ Complete lifecycle verified: DRAFT → SUBMITTED → REVIEWED → APPROVED → SIGNED → ACTIVE_LEASE
```

