"""
Application service for business logic
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
from fastapi import HTTPException, status
from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.core.logger import get_logger

logger = get_logger(__name__)

class ApplicationService:
    """Application service class"""
    
    def __init__(self, db: Session):
        self.db = db

    def _normalize_documents_urls(self, app: Application) -> Application:
        """Ensure documents_urls and references are always Python lists"""
        if isinstance(app.documents_urls, str):
            try:
                app.documents_urls = json.loads(app.documents_urls)
            except json.JSONDecodeError:
                app.documents_urls = []
        elif app.documents_urls is None:
            app.documents_urls = []
        
        # Normalize references field
        if isinstance(app.references, str):
            try:
                app.references = json.loads(app.references)
            except json.JSONDecodeError:
                app.references = []
        elif app.references is None:
            app.references = []
        
        return app

    def get_application_by_id(self, application_id: int) -> Optional[Application]:
        app = self.db.query(Application).filter(Application.id == application_id).first()
        if app:
            app = self._normalize_documents_urls(app)
        return app

    def get_user_applications(self, user_id: int) -> List[Application]:
        apps = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(a) for a in apps]

    def create_application(self, application_data: ApplicationCreate, user_id: int) -> Application:
        # Validate tenant role requirement
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not user.has_role("tenant"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant role required. Please complete tenant onboarding and get approved first."
            )
        
        app = Application(
            property_id=application_data.property_id,
            message=application_data.message,
            move_in_date=application_data.move_in_date,
            lease_duration=application_data.lease_duration,
            annual_income=application_data.annual_income,
            credit_score=application_data.credit_score,
            employment_status=application_data.employment_status,
            employer_name=application_data.employer_name,
            phone=application_data.phone,
            alternate_email=application_data.alternate_email,
            documents_urls=application_data.documents_urls or [],
            references=application_data.references or [],
            background_check_consent=application_data.background_check_consent or False,
            applicant_id=user_id
        )
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)

    def update_application(self, application_id: int, application_data: ApplicationUpdate) -> Optional[Application]:
        app = self.get_application_by_id(application_id)
        if not app:
            return None
        update_data = application_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(app, field, value)
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)

    def delete_application(self, application_id: int) -> bool:
        app = self.get_application_by_id(application_id)
        if not app:
            return False
        app.is_active = False
        self.db.commit()
        return True
    
    def get_property_applications(self, property_id: int) -> List[Application]:
        """Get all applications for a property"""
        apps = self.db.query(Application).filter(
            Application.property_id == property_id,
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(a) for a in apps]
    
    def update_application_status(
        self,
        application_id: int,
        new_status: ApplicationStatus,
        notes: Optional[str] = None
    ) -> Optional[Application]:
        """
        Update application status (for landlord/agent review).
        
        Enterprise-grade: Handles lease activation and auto-withdrawal logic.
        """
        app = self.get_application_by_id(application_id)
        if not app:
            return None
        
        old_status = app.status
        app.status = new_status
        
        # Set lease_signed_at when status becomes SIGNED
        if new_status == ApplicationStatus.SIGNED and not app.lease_signed_at:
            app.lease_signed_at = datetime.utcnow()
            logger.info(
                "lease_signed",
                application_id=application_id,
                applicant_id=app.applicant_id,
                property_id=app.property_id
            )
        
        if notes:
            # Store notes in message field if needed, or add notes field to model
            pass
        
        # Enterprise-grade: Auto-withdraw other applications when lease is signed/activated
        if new_status in [ApplicationStatus.SIGNED, ApplicationStatus.ACTIVE_LEASE]:
            self._auto_withdraw_other_applications(
                tenant_id=app.applicant_id,
                active_application_id=application_id
            )
        
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)
    
    def _auto_withdraw_other_applications(
        self,
        tenant_id: int,
        active_application_id: int
    ) -> int:
        """
        Auto-withdraw all other tenant applications when one becomes SIGNED or ACTIVE_LEASE.
        
        Business Rule: A tenant can have many applications, but only one active lease.
        
        Returns:
            Number of applications withdrawn
        """
        # Find all other applications for this tenant that should be withdrawn
        other_apps = self.db.query(Application).filter(
            Application.applicant_id == tenant_id,
            Application.id != active_application_id,
            Application.is_active == True,
            Application.status.in_([
                ApplicationStatus.PENDING,
                ApplicationStatus.UNDER_REVIEW,
                ApplicationStatus.APPROVED
            ])
        ).all()
        
        withdrawn_count = 0
        for app in other_apps:
            app.status = ApplicationStatus.WITHDRAWN
            withdrawn_count += 1
        
        if withdrawn_count > 0:
            self.db.commit()
            logger.info(
                "applications_auto_withdrawn",
                tenant_id=tenant_id,
                active_application_id=active_application_id,
                withdrawn_count=withdrawn_count
            )
        
        return withdrawn_count
    
    def sign_lease(
        self,
        application_id: int,
        signed_by_user_id: Optional[int] = None
    ) -> Application:
        """
        Sign a lease (move application to SIGNED status).
        
        Enterprise-grade validation:
        - Prevents signing if tenant already has ACTIVE_LEASE
        - Auto-withdraws other pending/approved applications
        - Sets lease_signed_at timestamp
        
        Args:
            application_id: ID of application to sign
            signed_by_user_id: Optional user ID who signed (for audit)
            
        Returns:
            Updated Application with SIGNED status
            
        Raises:
            HTTPException: If application not found or tenant has active lease
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Enterprise-grade: Validate tenant doesn't already have active lease
        existing_active_lease = self.db.query(Application).filter(
            Application.applicant_id == app.applicant_id,
            Application.id != application_id,
            Application.is_active == True,
            Application.status == ApplicationStatus.ACTIVE_LEASE
        ).first()
        
        if existing_active_lease:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Tenant already has an active lease. Cannot sign another lease until the current one ends.",
                    "field": "lease_status",
                    "existing_lease_id": existing_active_lease.id,
                    "existing_lease_property_id": existing_active_lease.property_id
                }
            )
        
        # Validate application is in a signable state
        if app.status not in [ApplicationStatus.APPROVED, ApplicationStatus.SIGNED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot sign lease. Application must be APPROVED. Current status: {app.status.value}",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        # Update to SIGNED status (this triggers auto-withdrawal via update_application_status)
        app.status = ApplicationStatus.SIGNED
        app.lease_signed_at = datetime.utcnow()
        
        # Auto-withdraw other applications
        withdrawn_count = self._auto_withdraw_other_applications(
            tenant_id=app.applicant_id,
            active_application_id=application_id
        )
        
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "lease_signed",
            application_id=application_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id,
            signed_by_user_id=signed_by_user_id,
            withdrawn_applications_count=withdrawn_count
        )
        
        return self._normalize_documents_urls(app)
    
    def activate_lease(
        self,
        application_id: int,
        activated_by_user_id: Optional[int] = None
    ) -> Application:
        """
        Activate a lease (move application from SIGNED to ACTIVE_LEASE status).
        
        This represents move-in confirmation - the lease is now live.
        
        Enterprise-grade validation:
        - Application must be in SIGNED status
        - Prevents activation if tenant already has ACTIVE_LEASE
        - Auto-withdraws other applications
        
        Args:
            application_id: ID of application to activate
            activated_by_user_id: Optional user ID who activated (for audit)
            
        Returns:
            Updated Application with ACTIVE_LEASE status
            
        Raises:
            HTTPException: If application not found or validation fails
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Validate application is SIGNED
        if app.status != ApplicationStatus.SIGNED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot activate lease. Application must be SIGNED. Current status: {app.status.value}",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        # Enterprise-grade: Validate tenant doesn't already have active lease
        existing_active_lease = self.db.query(Application).filter(
            Application.applicant_id == app.applicant_id,
            Application.id != application_id,
            Application.is_active == True,
            Application.status == ApplicationStatus.ACTIVE_LEASE
        ).first()
        
        if existing_active_lease:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Tenant already has an active lease. Cannot activate another lease until the current one ends.",
                    "field": "lease_status",
                    "existing_lease_id": existing_active_lease.id,
                    "existing_lease_property_id": existing_active_lease.property_id
                }
            )
        
        # Update to ACTIVE_LEASE status (this triggers auto-withdrawal via update_application_status)
        app.status = ApplicationStatus.ACTIVE_LEASE
        
        # Auto-withdraw other applications
        withdrawn_count = self._auto_withdraw_other_applications(
            tenant_id=app.applicant_id,
            active_application_id=application_id
        )
        
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "lease_activated",
            application_id=application_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id,
            activated_by_user_id=activated_by_user_id,
            withdrawn_applications_count=withdrawn_count
        )
        
        return self._normalize_documents_urls(app)
