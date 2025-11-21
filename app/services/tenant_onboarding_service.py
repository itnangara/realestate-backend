"""
Tenant onboarding service for managing tenant onboarding workflow
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status
from app.models.user import User
from app.models.tenant_profile import TenantProfile
from app.models.role_request import RoleRequest, RoleRequestStatus
from app.schemas.tenant import TenantOnboardingData, TenantOnboardingStatus
from app.services.tenant_service import TenantService
from app.services.document_service import DocumentService
from app.core.logger import get_logger

logger = get_logger(__name__)


class TenantOnboardingService:
    """Service for tenant onboarding operations"""
    
    def __init__(self, db: Session):
        self.db = db
        self.tenant_service = TenantService(db)
        self.document_service = DocumentService(db)
    
    def get_onboarding_status(self, user_id: int) -> TenantOnboardingStatus:
        """Get current onboarding status for a user"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        has_tenant_role = user.has_role("tenant")
        profile = self.tenant_service.get_tenant_profile(user_id)
        has_profile = profile is not None
        
        # Check for pending tenant role request
        # Enterprise-grade: Database-agnostic array filtering
        # Fetch all role requests for user and filter in Python (works for both PostgreSQL and SQLite)
        all_requests = self.db.query(RoleRequest).filter(
            RoleRequest.user_id == user_id
        ).all()
        
        pending_request = next(
            (req for req in all_requests 
             if req.status == RoleRequestStatus.PENDING and "tenant" in (req.requested_roles or [])),
            None
        )
        
        in_review_request = next(
            (req for req in all_requests 
             if req.status == RoleRequestStatus.IN_REVIEW and "tenant" in (req.requested_roles or [])),
            None
        )
        
        # Determine completed and pending steps
        completed_steps = []
        pending_steps = []
        
        if has_profile:
            completed_steps.append("profile_created")
        else:
            pending_steps.append("profile_creation")
        
        if pending_request or in_review_request:
            completed_steps.append("role_requested")
            if in_review_request:
                pending_steps.append("role_approval")
        elif has_tenant_role:
            completed_steps.append("role_approved")
        else:
            pending_steps.append("role_request")
        
        # Check for required documents
        from app.models.document import DocumentType
        user_documents = self.document_service.list_user_documents(user_id)
        has_id = any(doc.type in [DocumentType.ID_FRONT, DocumentType.ID_BACK] for doc in user_documents)
        has_income_proof = any(doc.type in [DocumentType.PROOF_OF_INCOME, DocumentType.EMPLOYER_LETTER] for doc in user_documents)
        
        if has_id:
            completed_steps.append("identity_documents")
        else:
            pending_steps.append("identity_documents")
        
        if has_income_proof:
            completed_steps.append("income_documents")
        else:
            pending_steps.append("income_documents")
        
        is_complete = (
            has_tenant_role and
            has_profile and
            len(pending_steps) == 0
        )
        
        # Convert profile to response schema if it exists
        from app.schemas.tenant import TenantProfileResponse
        profile_response = None
        if profile:
            profile_response = TenantProfileResponse.model_validate(profile)
        
        return TenantOnboardingStatus(
            is_complete=is_complete,
            has_tenant_role=has_tenant_role,
            has_profile=has_profile,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            profile=profile_response
        )
    
    def submit_onboarding_data(
        self,
        user_id: int,
        onboarding_data: TenantOnboardingData
    ) -> TenantProfile:
        """
        Submit tenant onboarding data and create/update profile.
        
        Includes enterprise-grade business logic validation with user-friendly errors.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Enterprise-grade business logic validation
        validation_errors = []
        
        # Validate required documents (if document_ids provided)
        if onboarding_data.document_ids:
            from app.models.document import DocumentType
            user_documents = self.document_service.list_user_documents(user_id)
            uploaded_doc_types = {doc.type for doc in user_documents}
            
            # Check for required identity documents
            has_id_front = DocumentType.ID_FRONT in uploaded_doc_types
            has_id_back = DocumentType.ID_BACK in uploaded_doc_types
            if not (has_id_front and has_id_back):
                missing = []
                if not has_id_front:
                    missing.append("ID/Passport Front")
                if not has_id_back:
                    missing.append("ID/Passport Back")
                validation_errors.append({
                    "field": "identity_documents",
                    "message": f"Missing required identity documents: {', '.join(missing)}. Please upload both front and back of your ID.",
                    "type": "missing_document"
                })
            
            # Check for required income proof
            has_income = any(doc.type in [DocumentType.PROOF_OF_INCOME, DocumentType.EMPLOYER_LETTER] 
                           for doc in user_documents)
            if not has_income:
                validation_errors.append({
                    "field": "income_documents",
                    "message": "Proof of income document is required. Please upload pay stubs, bank statements, or an employer letter.",
                    "type": "missing_document"
                })
        
        # Validate income data consistency
        if onboarding_data.annual_income and onboarding_data.monthly_income:
            calculated_annual = onboarding_data.monthly_income * 12
            # Allow 5% tolerance for rounding differences
            if abs(calculated_annual - onboarding_data.annual_income) > (calculated_annual * 0.05):
                validation_errors.append({
                    "field": "income_consistency",
                    "message": "Annual income and monthly income don't match. Please ensure annual income equals monthly income × 12.",
                    "type": "data_inconsistency"
                })
        
        # Validate credit score range
        if onboarding_data.credit_score is not None:
            if onboarding_data.credit_score < 300 or onboarding_data.credit_score > 850:
                validation_errors.append({
                    "field": "credit_score",
                    "message": "Credit score must be between 300 and 850.",
                    "type": "invalid_range"
                })
        
        # Validate rent budget is reasonable (if provided)
        if onboarding_data.max_rent_budget is not None and onboarding_data.max_rent_budget <= 0:
            validation_errors.append({
                "field": "max_rent_budget",
                "message": "Maximum rent budget must be greater than 0.",
                "type": "invalid_value"
            })
        
        # If validation errors exist, raise structured HTTPException
        if validation_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "ValidationError",
                    "message": validation_errors[0]["message"] if len(validation_errors) == 1 
                              else f"{validation_errors[0]['message']} and {len(validation_errors) - 1} other error(s)",
                    "fields": [e["field"] for e in validation_errors],
                    "errors": validation_errors,
                    "summary": "; ".join([e["message"] for e in validation_errors])
                }
            )
        
        # Extract profile data (exclude document_ids)
        profile_dict = onboarding_data.model_dump(exclude={"document_ids"})
        
        # Create or update tenant profile
        from app.schemas.tenant import TenantProfileCreate
        profile_data = TenantProfileCreate(**profile_dict)
        profile = self.tenant_service.create_or_update_tenant_profile(
            user_id=user_id,
            profile_data=profile_data
        )
        
        logger.info(
            "tenant_onboarding_data_submitted",
            user_id=user_id,
            profile_id=profile.id,
            has_documents=len(onboarding_data.document_ids or []) > 0
        )
        
        return profile
    
    def get_required_documents(self) -> List[dict]:
        """Get list of required documents for tenant onboarding"""
        return [
            {
                "type": "id_front",
                "name": "ID/Passport Front",
                "required": True,
                "description": "Front side of government-issued ID or passport"
            },
            {
                "type": "id_back",
                "name": "ID/Passport Back",
                "required": True,
                "description": "Back side of government-issued ID or passport"
            },
            {
                "type": "proof_of_income",
                "name": "Proof of Income",
                "required": True,
                "description": "Pay stubs, bank statements, or tax returns showing income"
            },
            {
                "type": "employer_letter",
                "name": "Employer Verification Letter",
                "required": False,
                "description": "Letter from employer verifying employment and income"
            },
            {
                "type": "proof_of_address",
                "name": "Proof of Address",
                "required": False,
                "description": "Utility bill or other document showing current address"
            }
        ]

