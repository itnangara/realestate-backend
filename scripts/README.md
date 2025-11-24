# API Documentation Validation Scripts

## validate_api_docs.py

Enterprise-grade automated validation of API documentation against actual code implementation.

### What It Detects

1. **Type Mismatches**: 
   - UUID strings vs integers (e.g., `document_ids: [1, 2]` should be `["uuid-1", "uuid-2"]`)
   - Wrong field types in JSON examples

2. **Enum Value Mismatches**:
   - Documented enum values that don't exist in code
   - Outdated enum values in examples

3. **Missing Fields**:
   - Required fields missing from response examples
   - Fields that should be documented but aren't

### Usage

```bash
python scripts/validate_api_docs.py
```

### Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/validate-docs.yml
- name: Validate API Documentation
  run: python scripts/validate_api_docs.py
```

### Exit Codes

- `0`: No errors found
- `1`: Errors found (documentation needs fixing)

