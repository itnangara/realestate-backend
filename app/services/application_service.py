"""
Application service for business logic
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
import json
import math
from fastapi import HTTPException, status
from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.models.property import Property, PropertyStatus
from app.models.document import Document
from app.models.user_property import UserProperty, RelationshipType
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
        app = self.db.query(Application).options(
            # Chain 1: Property -> Landlord info
            joinedload(Application.property)
                .joinedload(Property.user_properties)
                .joinedload(UserProperty.user),
            
            # Chain 2: Applicant -> Tenant Profile info
            joinedload(Application.applicant)
                .joinedload(User.tenant_profile)
        ).filter(Application.id == application_id).first()

        if app:
            # All normalization logic
            app = self._normalize_documents_urls(app)
            
        return app

    def get_user_applications(self, user_id: int) -> List[Application]:
        """
        Get all applications for a user (tenant).
        
        **Note:** This method is kept for backward compatibility.
        For filtered/paginated results, use get_filtered_applications().
        """
        apps = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(app) for app in apps]
    
    def get_filtered_applications(
        self,
        user_id: Optional[int] = None,
        landlord_id: Optional[int] = None,
        status: Optional[ApplicationStatus] = None,
        property_id: Optional[int] = None,
        applicant_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[Application], int, Dict[str, int]]:
        """
        Enterprise-grade filtered applications retrieval with full status padding.
        """
        # 1. Base Query & Eager Loading
        query = self.db.query(Application).options(
            joinedload(Application.property).joinedload(Property.user_properties).joinedload(UserProperty.user),
            joinedload(Application.applicant).joinedload(User.tenant_profile)
        ).filter(Application.is_active == True)

        # 2. Scope Filtering
        if user_id:
            query = query.filter(Application.applicant_id == user_id)
            
        if landlord_id:
            landlord_property_ids = [
                up.property_id for up in self.db.query(UserProperty.property_id)
                .filter(
                    UserProperty.user_id == landlord_id,
                    UserProperty.relationship_type == RelationshipType.LANDLORD
                ).all()
            ]
            if landlord_property_ids:
                query = query.filter(Application.property_id.in_(landlord_property_ids))
            else:
                query = query.filter(Application.id == -1)

        # 3. Dynamic Filters (AND logic)
        if status:
            query = query.filter(Application.status == status)
        if property_id:
            query = query.filter(Application.property_id == property_id)
        if applicant_id:
            query = query.filter(Application.applicant_id == applicant_id)
        if date_from:
            query = query.filter(Application.created_at >= date_from)
        if date_to:
            query = query.filter(Application.created_at <= date_to)
            
        # 4. Numeric Search
        if search and search.strip().isdigit():
            search_num = int(search.strip())
            search_conditions = [
                Application.id == search_num,
                Application.property_id == search_num
            ]
            if landlord_id is not None:
                search_conditions.append(Application.applicant_id == search_num)
            query = query.filter(or_(*search_conditions))

        # 5. Calculate Metrics (Before Pagination)
        total = query.count()
        
        # This ensures the frontend chips always have a number to display.
        status_counts: Dict[str, int] = {s.value: 0 for s in ApplicationStatus}
        status_counts["all"] = int(total)

        # Query only the counts for the filtered set
        db_counts = query.with_entities(
            Application.status, 
            func.count(Application.id)
        ).group_by(Application.status).all()

        for st, c in db_counts:
            key = st.value if hasattr(st, "value") else str(st)
            status_counts[str(key)] = int(c)

        # 6. Pagination & Execution
        offset = (page - 1) * limit
        items = query.order_by(Application.created_at.desc()).offset(offset).limit(limit).all()
        
        normalized_items = [self._normalize_documents_urls(app) for app in items]
        
        return normalized_items, total, status_counts
        
    def get_tenant_leases(self, user_id: int) -> List[Application]:
        """
        Get tenant's leases (applications with SIGNED or ACTIVE_LEASE status).
        
        Enterprise-grade: Returns only active leases for the authenticated tenant.        """

        leases = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True,
            Application.status.in_([
                ApplicationStatus.SIGNED,
                ApplicationStatus.ACTIVE_LEASE
            ])
        ).order_by(Application.lease_signed_at.desc().nulls_last()).all()
        return [self._normalize_documents_urls(lease) for lease in leases]

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
        return [self._normalize_documents_urls(app) for app in apps]
    
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
                ApplicationStatus.DRAFT,
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.REVIEWED,
                ApplicationStatus.NEEDS_INFO,
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
        if app.status != ApplicationStatus.APPROVED:
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
    
    # ------------------- New Enterprise-Grade Methods ------------------- #
    
    def create_tenant_application(self, application_data: ApplicationCreate, user_id: int) -> Application:
        """
        Create a tenant application with enterprise-grade validation.
        
        **Business Rules:**
        - Tenant role required
        - Cannot apply if already has active lease
        - Cannot apply twice to same property unless previous is rejected/withdrawn
        - Property must be active and available
        
        **Status:** Application starts in DRAFT status
        """
        # Validate tenant role
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
        
        # Enterprise-grade: Check for active lease
        existing_active_lease = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.is_active == True,
            Application.status == ApplicationStatus.ACTIVE_LEASE
        ).first()
        
        if existing_active_lease:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Cannot apply for a new property while you have an active lease.",
                    "field": "lease_status",
                    "existing_lease_id": existing_active_lease.id
                }
            )
        
        # Enterprise-grade: Check for duplicate application
        existing_app = self.db.query(Application).filter(
            Application.applicant_id == user_id,
            Application.property_id == application_data.property_id,
            Application.is_active == True,
            Application.status.notin_([ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN])
        ).first()
        
        if existing_app:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"You already have an active application for this property (status: {existing_app.status.value}).",
                    "field": "duplicate_application",
                    "existing_application_id": existing_app.id
                }
            )
        
        # Validate property is active and available
        property = self.db.query(Property).filter(Property.id == application_data.property_id).first()
        if not property:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        
        if not property.is_active or property.status != PropertyStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Property is not available for applications.",
                    "field": "property_status"
                }
            )
        
        # Create application in DRAFT status
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
            applicant_id=user_id,
            status=ApplicationStatus.DRAFT  # Start in DRAFT
        )
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "application_created",
            application_id=app.id,
            applicant_id=user_id,
            property_id=application_data.property_id,
            status="draft"
        )
        
        return self._normalize_documents_urls(app)
    
    def update_tenant_application(self, application_id: int, application_data: ApplicationUpdate, user_id: int) -> Application:
        """
        Update tenant application with status transition enforcement.
        
        **Status Transitions:**
        - DRAFT → SUBMITTED: When tenant submits
        - NEEDS_INFO → SUBMITTED: When tenant resubmits after providing info
        
        **Business Rules:**
        - Can only update own applications
        - Cannot edit after SUBMITTED unless status is NEEDS_INFO
        - Status transitions are validated
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        if app.applicant_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        
        # Handle status transition if status is being updated
        if application_data.status and application_data.status != app.status:
            new_status = application_data.status
            
            # Validate status transition
            if app.status == ApplicationStatus.DRAFT:
                if new_status == ApplicationStatus.SUBMITTED:
                    # DRAFT → SUBMITTED: Tenant submits application
                    # REVIEWED status will be set later by background job or reviewer action
                    app.status = ApplicationStatus.SUBMITTED
                    logger.info(
                        "application_submitted",
                        application_id=application_id,
                        applicant_id=user_id,
                        transition="draft → submitted"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "ValidationError",
                            "message": f"Invalid status transition from {app.status.value} to {new_status.value}. From DRAFT, you can only transition to SUBMITTED.",
                            "field": "status"
                        }
                    )
            elif app.status == ApplicationStatus.NEEDS_INFO:
                if new_status == ApplicationStatus.SUBMITTED:
                    # NEEDS_INFO → SUBMITTED: Tenant resubmits after providing requested info
                    # REVIEWED status will be set later by background job or reviewer action
                    app.status = ApplicationStatus.SUBMITTED
                    logger.info(
                        "application_resubmitted",
                        application_id=application_id,
                        applicant_id=user_id,
                        transition="needs_info → submitted"
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "error": "ValidationError",
                            "message": f"Invalid status transition from {app.status.value} to {new_status.value}. From NEEDS_INFO, you can only transition to SUBMITTED.",
                            "field": "status"
                        }
                    )
            else:
                # Cannot change status from other states
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": f"Cannot change status from {app.status.value}. Only DRAFT and NEEDS_INFO applications can be edited.",
                        "field": "status"
                    }
                )
        elif application_data.status is None:
            # No status change, just update other fields
            # But check if application is editable
            if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_INFO]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": f"Cannot edit application in {app.status.value} status. Only DRAFT and NEEDS_INFO applications can be edited.",
                        "field": "application_status"
                    }
                )
        
        # Update other fields
        update_data = application_data.model_dump(exclude_unset=True, exclude={"status"})
        for field, value in update_data.items():
            setattr(app, field, value)
        
        self.db.commit()
        self.db.refresh(app)
        return self._normalize_documents_urls(app)
    
    def attach_documents_to_application(
        self,
        application_id: int,
        document_ids: List[str],
        user_id: int
    ) -> Application:
        """
        Attach documents to an application.
        
        **Enterprise-grade validation:**
        - Documents must belong to the tenant
        - Application must belong to the tenant
        - Application must be in DRAFT or NEEDS_INFO status
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        if app.applicant_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        
        if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_INFO]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot attach documents to application in {app.status.value} status. Only DRAFT and NEEDS_INFO applications can be edited.",
                    "field": "application_status"
                }
            )
        
        # Validate all documents belong to the user
        from uuid import UUID
        validated_doc_ids = []
        for doc_id_str in document_ids:
            try:
                doc_uuid = UUID(doc_id_str)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": f"Invalid document ID format: {doc_id_str}",
                        "field": "document_ids"
                    }
                )
            
            document = self.db.query(Document).filter(
                Document.file_id == doc_uuid,
                Document.user_id == user_id
            ).first()
            
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "error": "ValidationError",
                        "message": f"Document {doc_id_str} not found or does not belong to you.",
                        "field": "document_ids"
                    }
                )
            
            validated_doc_ids.append(doc_id_str)
        
        # Update documents_urls (store document IDs, not URLs)
        current_docs = app.documents_urls or []
        # Merge and deduplicate
        all_docs = list(set(current_docs + validated_doc_ids))
        app.documents_urls = all_docs
        
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "documents_attached_to_application",
            application_id=application_id,
            user_id=user_id,
            document_count=len(validated_doc_ids)
        )
        
        return self._normalize_documents_urls(app)
    
    def get_landlord_applications(self, landlord_id: int) -> List[Application]:
        """
        Get all applications for properties owned by the landlord.
        
        **Enterprise-grade filtering:**
        - Only returns applications for properties where landlord has LANDLORD relationship (via user_properties)
        """
        # Get all properties owned by landlord using unified ownership
        from app.utils.property_ownership import get_property_owners
        
        # Get all properties and filter by ownership
        all_properties = self.db.query(Property).filter(Property.is_active == True).all()
        property_ids = [
            p.id for p in all_properties
            if landlord_id in get_property_owners(self.db, p.id)
        ]
        
        if not property_ids:
            return []
        
        apps = self.db.query(Application).filter(
            Application.property_id.in_(property_ids),
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(app) for app in apps]
    
    def get_all_applications(self) -> List[Application]:
        """Get all applications (admin only)"""
        apps = self.db.query(Application).filter(
            Application.is_active == True
        ).all()
        return [self._normalize_documents_urls(app) for app in apps]
    
    def withdraw_application(self, application_id: int, user_id: int) -> Application:
        """
        Withdraw a tenant application.
        
        Enterprise-grade validation:
        - Tenant can only withdraw own applications
        - Can withdraw from: DRAFT, SUBMITTED, REVIEWED, NEEDS_INFO
        - Cannot withdraw: APPROVED, SIGNED, ACTIVE_LEASE, REJECTED, WITHDRAWN
        
        Args:
            application_id: ID of application to withdraw
            user_id: ID of tenant withdrawing the application
            
        Returns:
            Updated Application with WITHDRAWN status
            
        Raises:
            HTTPException: If application not found, unauthorized, or invalid status
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Enterprise-grade: Verify ownership
        if app.applicant_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - can only withdraw own applications"
            )
        
        # Enterprise-grade: Validate withdrawable status
        withdrawable_statuses = [
            ApplicationStatus.DRAFT,
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.REVIEWED,
            ApplicationStatus.NEEDS_INFO
        ]
        
        if app.status not in withdrawable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot withdraw application in {app.status.value} status. Only DRAFT, SUBMITTED, REVIEWED, or NEEDS_INFO applications can be withdrawn.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        # Withdraw application
        previous_status = app.status.value
        app.status = ApplicationStatus.WITHDRAWN
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "application_withdrawn",
            application_id=application_id,
            user_id=user_id,
            previous_status=previous_status
        )
        
        return self._normalize_documents_urls(app)
    
    def review_application(self, application_id: int, landlord_id: int) -> Application:
        """
        Review an application (mark as reviewed by landlord).
        
        **Status transition:** SUBMITTED → REVIEWED
        
        **Business Rules:**
        - Application must be in SUBMITTED status
        - Only landlord/agent can review
        - Property must be owned by the landlord
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Validate status - only SUBMITTED can be reviewed
        if app.status != ApplicationStatus.SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot review application in {app.status.value} status. Application must be in SUBMITTED status.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        # Update status: SUBMITTED → REVIEWED
        # Note: Property ownership is verified in the route handler
        app.status = ApplicationStatus.REVIEWED
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "application_reviewed",
            application_id=application_id,
            landlord_id=landlord_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id,
            transition="submitted → reviewed"
        )
        
        return self._normalize_documents_urls(app)
    
    def approve_application(self, application_id: int, landlord_id: int) -> Application:
        """
        Approve an application.
        
        **Status transition:** REVIEWED → APPROVED
        
        **Business Rules:**
        - Application must be in REVIEWED status (must be reviewed first)
        - System checks: tenant has no active lease, property is available
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Validate status - only REVIEWED can be approved
        if app.status != ApplicationStatus.REVIEWED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot approve application in {app.status.value} status. Application must be in REVIEWED status. Please review the application first.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        # Enterprise-grade: Check tenant doesn't have active lease
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
                    "message": "Tenant already has an active lease. Cannot approve another application.",
                    "field": "lease_status",
                    "existing_lease_id": existing_active_lease.id
                }
            )
        
        # Validate property is still available
        property = self.db.query(Property).filter(Property.id == app.property_id).first()
        if not property or not property.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Property is no longer available.",
                    "field": "property_status"
                }
            )
        
        # Update status
        app.status = ApplicationStatus.APPROVED
        self.db.commit()
        self.db.refresh(app)
        
        # Enterprise-grade: Auto-create lease draft when application is approved
        # This implements the unified workflow - lease draft is automatically created
        from app.models.lease import Lease, LeaseStatus
        from app.schemas.lease import LeaseCreate
        from decimal import Decimal
        
        # Check if lease already exists for this application
        existing_lease = self.db.query(Lease).filter(
            Lease.application_id == application_id
        ).first()
        
        if not existing_lease:
            # Auto-create lease draft with default values
            # Landlord can edit these later before sending
            property = self.db.query(Property).filter(Property.id == app.property_id).first()
            if property:
                # Calculate default lease dates (30 days from now, 12 months duration)
                from datetime import timedelta
                start_date = datetime.now(timezone.utc) + timedelta(days=30)
                end_date = start_date + timedelta(days=365)
                
                # Default rent from property rent_price if available
                # If no rent_price, skip auto-creation (landlord must create manually with proper rent)
                if not property.rent_price:
                    logger.warning(
                        "lease_auto_creation_skipped_no_rent_price",
                        application_id=application_id,
                        property_id=app.property_id,
                        reason="Property has no rent_price set"
                    )
                    return self._normalize_documents_urls(app)
                
                default_rent = Decimal(str(property.rent_price))
                default_deposit = default_rent  # Security deposit = 1 month rent (industry standard)
                
                lease = Lease(
                    application_id=application_id,
                    landlord_id=landlord_id,
                    tenant_id=app.applicant_id,
                    property_id=app.property_id,
                    rent=default_rent,
                    deposit=default_deposit,
                    start_date=start_date,
                    end_date=end_date,
                    terms=None,  # Landlord can add terms later
                    clauses=[],
                    status=LeaseStatus.DRAFT
                )
                
                self.db.add(lease)
                self.db.commit()
                self.db.refresh(lease)
                
                logger.info(
                    "lease_auto_created_on_approval",
                    lease_id=lease.id,
                    application_id=application_id,
                    landlord_id=landlord_id,
                    tenant_id=app.applicant_id,
                    property_id=app.property_id
                )
        
        logger.info(
            "application_approved",
            application_id=application_id,
            landlord_id=landlord_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id
        )
        
        return self._normalize_documents_urls(app)
    
    def reject_application(self, application_id: int, landlord_id: int) -> Application:
        """
        Reject an application.
        
        **Status transition:** REVIEWED → REJECTED
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Validate status - only REVIEWED can be rejected
        if app.status != ApplicationStatus.REVIEWED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot reject application in {app.status.value} status. Application must be in REVIEWED status. Please review the application first.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        app.status = ApplicationStatus.REJECTED
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "application_rejected",
            application_id=application_id,
            landlord_id=landlord_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id
        )
        
        return self._normalize_documents_urls(app)
    
    def request_more_info(self, application_id: int, landlord_id: int) -> Application:
        """
        Request more information from applicant.
        
        **Status transition:** REVIEWED → NEEDS_INFO
        - Tenant can then resubmit (NEEDS_INFO → SUBMITTED → REVIEWED)
        """
        app = self.get_application_by_id(application_id)
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Validate status - only REVIEWED can request more info
        if app.status != ApplicationStatus.REVIEWED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot request info for application in {app.status.value} status. Application must be in REVIEWED status. Please review the application first.",
                    "field": "application_status",
                    "current_status": app.status.value
                }
            )
        
        app.status = ApplicationStatus.NEEDS_INFO
        self.db.commit()
        self.db.refresh(app)
        
        logger.info(
            "application_needs_info",
            application_id=application_id,
            landlord_id=landlord_id,
            applicant_id=app.applicant_id,
            property_id=app.property_id
        )
        
        return self._normalize_documents_urls(app)