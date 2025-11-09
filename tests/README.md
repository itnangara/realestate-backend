## 1. Quick Test
pytest tests/ --tb=no -q

## 2. Detailed Test with Verbose Output
pytest tests/ -v -s

## 3. (most recommended) Test with Short Error Traceback
pytest tests/ --tb=short -v -s

# 4
## Test only applications
pytest tests/applications/ -v
pytest tests/applications/ -v -s

## Test only properties  
pytest tests/properties/ -v
pytest tests/properties/ -v -s

## Test only auth
pytest tests/auth/ -v

# 5. Test with Coverage Report
pytest tests/ --cov=app --cov-report=html

# 6. Test in Parallel (Faster)
pytest tests/ -n auto

# 7. For CI/CD Pipeline:
pytest tests

# 8. For Debugging Failed Tests:
pytest tests/ -v --tb=long

# To view more traceback details (add temp below code, remove from tests once testing is done)
print("Isaac Temp:",response.json())
print("Isaac Temp:",response.status_code)

### Onboarding Process Tests
# Run all Phase 2 tests
pytest tests/services/test_s3_service.py tests/services/test_audit_service.py tests/core/test_feature_flags.py -v

# Run specific test file
pytest tests/services/test_s3_service.py -v

# Run with coverage
pytest tests/services/ tests/core/ --cov=app.services --cov=app.core -v
