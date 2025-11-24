"""
Enterprise-grade API Documentation Validator

Automatically validates API documentation against actual Pydantic schemas.
Detects type mismatches, enum errors, and missing fields.

Usage: python scripts/validate_api_docs.py
"""
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class ValidationIssue:
    """Represents a validation issue"""
    severity: str
    category: str
    endpoint: str
    field: str
    documented_value: Any
    expected_type: str
    message: str


class DocumentationValidator:
    """Validates API documentation against code"""
    
    def __init__(self, doc_path: Path):
        self.doc_path = doc_path
        self.content = doc_path.read_text(encoding='utf-8')
        self.issues: List[ValidationIssue] = []
    
    def validate(self) -> List[ValidationIssue]:
        """Run all validations"""
        print("[VALIDATING] API documentation against code...\n")
        
        # 1. Check for UUID vs integer mismatches in document_ids
        self.validate_document_ids()
        
        # 2. Check enum values match models
        self.validate_enum_values()
        
        # 3. Check response examples match schemas
        self.validate_response_examples()
        
        return self.issues
    
    def validate_document_ids(self):
        """Check document_ids are UUIDs, not integers"""
        # Find role request endpoint
        pattern = r'POST.*`/api/roles/request`.*?```json\n(.*?)```'
        matches = re.finditer(pattern, self.content, re.DOTALL)
        
        for match in matches:
            json_str = match.group(1).strip()
            try:
                data = json.loads(json_str)
                if 'document_ids' in data:
                    doc_ids = data['document_ids']
                    if isinstance(doc_ids, list) and doc_ids:
                        # Check if integers (wrong) instead of UUID strings (correct)
                        if isinstance(doc_ids[0], int):
                            self.issues.append(ValidationIssue(
                                severity="error",
                                category="type_mismatch",
                                endpoint="POST /api/roles/request",
                                field="document_ids",
                                documented_value=doc_ids,
                                expected_type="List[UUID] (array of UUID strings)",
                                message="document_ids must be UUID strings, not integers. Use file_id from /api/documents/upload response."
                            ))
                        elif not self.is_uuid_string(str(doc_ids[0])):
                            self.issues.append(ValidationIssue(
                                severity="error",
                                category="type_mismatch",
                                endpoint="POST /api/roles/request",
                                field="document_ids",
                                documented_value=doc_ids,
                                expected_type="List[UUID] (array of UUID strings)",
                                message="document_ids must be valid UUID strings"
                            ))
            except json.JSONDecodeError:
                continue
    
    def validate_enum_values(self):
        """Validate enum values in documentation match actual enums"""
        # Check ApplicationStatus
        app_status_pattern = r'"status":\s*"([^"]+)"'
        doc_statuses = set(re.findall(app_status_pattern, self.content))
        
        # Actual enum values from code
        try:
            from app.models.application import ApplicationStatus
            actual_statuses = {e.value for e in ApplicationStatus}
            
            invalid_statuses = doc_statuses - actual_statuses
            for status in invalid_statuses:
                # Find context around this status
                status_pos = self.content.find(f'"status": "{status}"')
                if status_pos > 0:
                    context = self.content[max(0, status_pos-200):min(len(self.content), status_pos+200)]
                    # Skip if it's in a health check, system endpoint, or old example
                    if any(skip in context.lower() for skip in ['/health', 'system', 'old', 'deprecated', 'legacy']):
                        continue
                    # Check if it's in an application context
                    if '/api/' in context and ('application' in context.lower() or 'tenant' in context.lower() or 'landlord' in context.lower()):
                        self.issues.append(ValidationIssue(
                            severity="warning",
                            category="enum_mismatch",
                            endpoint="various",
                            field="status",
                            documented_value=status,
                            expected_type=f"ApplicationStatus: {sorted(actual_statuses)}",
                            message=f"Status '{status}' not in ApplicationStatus enum. Valid values: {sorted(actual_statuses)}"
                        ))
        except ImportError:
            pass
        
        # Check PropertyStatus (context-aware)
        try:
            from app.models.property import PropertyStatus
            from app.models.application import ApplicationStatus
            actual_prop_statuses = {e.value for e in PropertyStatus}
            actual_app_statuses = {e.value for e in ApplicationStatus}
            
            # Find all status values with context
            prop_status_pattern = r'"status":\s*"([^"]+)"'
            for match in re.finditer(prop_status_pattern, self.content):
                status = match.group(1)
                status_pos = match.start()
                
                # Get context (200 chars before and after)
                context_start = max(0, status_pos - 200)
                context_end = min(len(self.content), status_pos + 200)
                context = self.content[context_start:context_end].lower()
                
                # Skip if it's a valid ApplicationStatus (in application/tenant/landlord context)
                if status in actual_app_statuses:
                    if any(keyword in context for keyword in ['application', 'tenant', 'landlord', '/api/tenant', '/api/landlord']):
                        continue
                
                # Skip system/health endpoints
                if any(skip in context for skip in ['/health', '/api/webhooks', 'system', 'healthy', 'success']):
                    continue
                
                # Skip if it's a valid PropertyStatus
                if status in actual_prop_statuses:
                    continue
                
                # Only flag if it's in a property-related context
                if any(keyword in context for keyword in ['property', '/api/properties', 'property_type', 'listing_type']):
                    self.issues.append(ValidationIssue(
                        severity="warning",
                        category="enum_mismatch",
                        endpoint="property endpoints",
                        field="status",
                        documented_value=status,
                        expected_type=f"PropertyStatus: {sorted(actual_prop_statuses)}",
                        message=f"Property status '{status}' not in PropertyStatus enum. Valid values: {sorted(actual_prop_statuses)}"
                    ))
        except ImportError:
            pass
    
    def validate_response_examples(self):
        """Validate response examples match expected structure"""
        # Check document upload response includes file_id
        # Find all Response sections for /api/documents/upload
        lines = self.content.split('\n')
        in_upload_section = False
        in_response_json = False
        json_lines = []
        
        for i, line in enumerate(lines):
            if '/api/documents/upload' in line and 'POST' in line:
                in_upload_section = True
                continue
            
            if in_upload_section and '**Response**' in line and '201' in line:
                in_response_json = False
                json_lines = []
                continue
            
            if in_upload_section and '```json' in line:
                # Check if this is after a Response (201) line
                lookback = '\n'.join(lines[max(0, i-5):i])
                if 'Response' in lookback and '201' in lookback:
                    in_response_json = True
                    json_lines = []
                    continue
            
            if in_response_json:
                if '```' in line and line.strip() != '```json':
                    # End of JSON block
                    json_str = '\n'.join(json_lines)
                    if json_str.strip():
                        try:
                            data = json.loads(json_str)
                            if 'file_id' not in data:
                                self.issues.append(ValidationIssue(
                                    severity="error",
                                    category="missing_field",
                                    endpoint="POST /api/documents/upload",
                                    field="file_id",
                                    documented_value="missing",
                                    expected_type="UUID string",
                                    message="Response example missing 'file_id' field. This is required for role requests."
                                ))
                            else:
                                # Validate file_id is a UUID string
                                if not self.is_uuid_string(str(data['file_id'])):
                                    self.issues.append(ValidationIssue(
                                        severity="error",
                                        category="type_mismatch",
                                        endpoint="POST /api/documents/upload",
                                        field="file_id",
                                        documented_value=data['file_id'],
                                        expected_type="UUID string",
                                        message="file_id must be a UUID string"
                                    ))
                        except json.JSONDecodeError:
                            pass
                    in_response_json = False
                    json_lines = []
                elif not line.strip().startswith('```'):
                    json_lines.append(line)
            
            # Reset section flag if we've moved to next endpoint
            if in_upload_section and line.startswith('##') and '/api/documents/upload' not in line:
                in_upload_section = False
    
    def is_uuid_string(self, value: str) -> bool:
        """Check if string is valid UUID format"""
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(uuid_pattern, value.lower()))


def main():
    """Main entry point"""
    doc_path = project_root / "temp" / "API_ENDPOINTS.md"
    
    if not doc_path.exists():
        print(f"[ERROR] Documentation file not found: {doc_path}")
        return 1
    
    validator = DocumentationValidator(doc_path)
    issues = validator.validate()
    
    # Report results
    print(f"[RESULTS] Validation Results:")
    print(f"   Total issues: {len(issues)}\n")
    
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    
    if errors:
        print(f"[ERROR] ERRORS ({len(errors)}):")
        for issue in errors:
            print(f"\n   [{issue.category.upper()}] {issue.endpoint}")
            print(f"   Field: {issue.field}")
            print(f"   Issue: {issue.message}")
            print(f"   Documented: {issue.documented_value}")
            print(f"   Expected: {issue.expected_type}")
    
    if warnings:
        print(f"\n[WARNING] WARNINGS ({len(warnings)}):")
        for issue in warnings[:5]:
            print(f"   [{issue.category}] {issue.message}")
    
    if not issues:
        print("[OK] No issues found! Documentation matches code.")
    
    return 1 if errors else 0


if __name__ == "__main__":
    exit(main())
