"""
Lease service for managing rental leases
Enterprise-grade business logic with proper validation and audit logging
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException, status
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from decimal import Decimal
import asyncio

from app.models.lease import Lease, LeaseSignature, LeaseStatus
from app.models.application import Application, ApplicationStatus
from app.models.property import Property
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.lease import LeaseCreate, LeaseUpdate, LeaseSignRequest
from app.core.logger import get_logger
from app.core.event_bus import event_bus

logger = get_logger(__name__)


class LeaseService:
    """Lease service for managing rental leases"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_lease(self, lease_data: LeaseCreate, landlord_id: int) -> Lease:
        """
        Create a lease draft - supports both application-driven and manual creation.
        
        **Enterprise-grade unified workflow:**
        - Application-driven: Requires application_id (must be APPROVED)
        - Manual: Requires property_id + tenant_id (application_id = None)
        
        **Business Rules:**
        - Application-driven: Application must be APPROVED, property must belong to landlord
        - Manual: Property must belong to landlord, tenant must exist
        - Cannot create duplicate lease for same application (if application_id provided)
        - Only landlord or property manager may create
        
        **Status:** Lease always starts in DRAFT status regardless of origin
        """
        property_id = None
        tenant_id = None
        application_id = lease_data.application_id
        
        # Determine lease origin and validate
        if application_id:
            # Application-driven lease
            app = self.db.query(Application).filter(Application.id == application_id).first()
            if not app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found"
                )
            
            # Validate application status
            if app.status != ApplicationStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": f"Cannot create lease for application in {app.status.value} status. Application must be APPROVED.",
                        "field": "application_status",
                        "current_status": app.status.value
                    }
                )
            
            property_id = app.property_id
            tenant_id = app.applicant_id
            
            # Check if lease already exists for this application
            existing_lease = self.db.query(Lease).filter(
                Lease.application_id == application_id
            ).first()
            
            if existing_lease:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": "Lease already exists for this application",
                        "field": "application_id",
                        "existing_lease_id": existing_lease.id
                    }
                )
        else:
            # Manual lease creation
            if not lease_data.property_id or not lease_data.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": "Either application_id or both property_id and tenant_id must be provided",
                        "field": "lease_creation"
                    }
                )
            
            property_id = lease_data.property_id
            tenant_id = lease_data.tenant_id
            
            # Verify tenant exists
            tenant = self.db.query(User).filter(User.id == tenant_id).first()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tenant not found"
                )
        
        # Verify property ownership (for both cases)
        property = self.db.query(Property).filter(Property.id == property_id).first()
        if not property:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        
        if property.owner_id != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - you don't own this property"
            )
        
        # Create lease (unified workflow - same logic for both origins)
        lease = Lease(
            application_id=application_id,  # None for manual leases
            landlord_id=landlord_id,
            tenant_id=tenant_id,
            property_id=property_id,
            rent=lease_data.rent,
            deposit=lease_data.deposit,
            start_date=lease_data.start_date,
            end_date=lease_data.end_date,
            terms=lease_data.terms,
            clauses=lease_data.clauses or [],
            status=LeaseStatus.DRAFT  # Always DRAFT regardless of origin
        )
        
        self.db.add(lease)
        self.db.commit()
        self.db.refresh(lease)
        
        # Audit log
        self._log_audit(
            action="lease_created",
            target_type="lease",
            target_id=lease.id,
            actor_id=landlord_id,
            meta={
                "application_id": application_id,
                "property_id": property_id,
                "tenant_id": tenant_id,
                "rent": float(lease_data.rent),
                "deposit": float(lease_data.deposit) if lease_data.deposit else None,
                "origin": "application" if application_id else "manual"
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease.id, {
            "type": "LEASE_STATUS_CHANGED",
            "lease_id": lease.id,
            "status": lease.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_created",
            lease_id=lease.id,
            application_id=application_id,
            landlord_id=landlord_id,
            tenant_id=tenant_id,
            property_id=property_id,
            origin="application" if application_id else "manual"
        )
        
        return lease
    
    def get_lease_by_id(self, lease_id: int) -> Optional[Lease]:
        """Get lease by ID"""
        return self.db.query(Lease).filter(Lease.id == lease_id).first()
    
    def get_lease_by_application_id(self, application_id: int) -> Optional[Lease]:
        """Get lease by application ID"""
        return self.db.query(Lease).filter(Lease.application_id == application_id).first()
    
    async def send_lease(self, lease_id: int, landlord_id: int, message: Optional[str] = None) -> Lease:
        """
        Send lease to tenant for signing.
        
        **Status transition:** DRAFT → SENT
        **Application status:** Stays APPROVED (tracked via lease status)
        """
        lease = self.get_lease_by_id(lease_id)
        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found"
            )
        
        # Validate status
        if lease.status != LeaseStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot send lease in {lease.status.value} status. Lease must be in DRAFT status.",
                    "field": "lease_status",
                    "current_status": lease.status.value
                }
            )
        
        # Verify landlord owns the property
        property = self.db.query(Property).filter(Property.id == lease.property_id).first()
        if not property or property.owner_id != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - you don't own this property"
            )
        
        # Update lease status
        lease.status = LeaseStatus.SENT
        lease.sent_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(lease)
        
        # Audit log
        self._log_audit(
            action="lease_sent",
            target_type="lease",
            target_id=lease_id,
            actor_id=landlord_id,
            meta={
                "message": message,
                "tenant_id": lease.tenant_id
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease_id, {
            "type": "LEASE_STATUS_CHANGED",
            "lease_id": lease_id,
            "status": lease.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_sent",
            lease_id=lease_id,
            landlord_id=landlord_id,
            tenant_id=lease.tenant_id
        )
        
        return lease
    
    async def sign_lease(self, lease_id: int, tenant_id: int, sign_data: LeaseSignRequest, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Lease:
        """
        Tenant signs the lease.
        
        **Enterprise-grade status enforcement:**
        - Only allowed when lease.status = SENT (strict enforcement)
        
        **Status transition:** SENT → SIGNED
        **Application status:** No change (stays APPROVED until activation)
        """
        lease = self.get_lease_by_id(lease_id)
        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found"
            )
        
        # Validate tenant
        if lease.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - this lease does not belong to you"
            )
        
        # Strict status enforcement: only SENT allowed
        if lease.status != LeaseStatus.SENT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot sign lease in {lease.status.value} status. Lease must be in SENT status (landlord must send first).",
                    "field": "lease_status",
                    "current_status": lease.status.value
                }
            )
        
        # Check if already signed (idempotency)
        existing_signature = self.db.query(LeaseSignature).filter(
            and_(
                LeaseSignature.lease_id == lease_id,
                LeaseSignature.user_id == tenant_id
            )
        ).first()
        
        if existing_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "You have already signed this lease",
                    "field": "signature"
                }
            )
        
        # Create signature
        signature = LeaseSignature(
            lease_id=lease_id,
            user_id=tenant_id,
            role="tenant",
            signature_text=sign_data.signature,
            signed_at=sign_data.signed_at or datetime.now(timezone.utc),
            method="manual",
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(signature)
        
        # Update lease status
        lease.status = LeaseStatus.SIGNED
        lease.signed_at = signature.signed_at
        self.db.commit()
        self.db.refresh(lease)
        
        # Note: Application status stays APPROVED until lease is activated
        # This follows the unified workflow - application only updates on ACTIVE or TERMINATED
        
        # Audit log
        self._log_audit(
            action="lease_signed",
            target_type="lease",
            target_id=lease_id,
            actor_id=tenant_id,
            meta={
                "role": "tenant",
                "method": "manual"
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease_id, {
            "type": "LEASE_STATUS_CHANGED",
            "lease_id": lease_id,
            "status": lease.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_signed_by_tenant",
            lease_id=lease_id,
            tenant_id=tenant_id
        )
        
        return lease
    
    async def counter_sign_lease(self, lease_id: int, landlord_id: int, sign_data: LeaseSignRequest, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Lease:
        """
        Landlord counter-signs the lease after tenant has signed.
        
        **Status transition:** SIGNED → COUNTER_SIGNED
        """
        lease = self.get_lease_by_id(lease_id)
        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found"
            )
        
        # Validate landlord
        if lease.landlord_id != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - you don't own this property"
            )
        
        # Validate status - must be SIGNED (tenant must sign first)
        if lease.status != LeaseStatus.SIGNED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot counter-sign lease in {lease.status.value} status. Lease must be SIGNED (tenant must sign first).",
                    "field": "lease_status",
                    "current_status": lease.status.value
                }
            )
        
        # Check if tenant has signed
        tenant_signature = self.db.query(LeaseSignature).filter(
            and_(
                LeaseSignature.lease_id == lease_id,
                LeaseSignature.role == "tenant"
            )
        ).first()
        
        if not tenant_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Tenant must sign the lease before landlord can counter-sign",
                    "field": "lease_status"
                }
            )
        
        # Check if already counter-signed (idempotency)
        existing_signature = self.db.query(LeaseSignature).filter(
            and_(
                LeaseSignature.lease_id == lease_id,
                LeaseSignature.user_id == landlord_id
            )
        ).first()
        
        if existing_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "You have already signed this lease",
                    "field": "signature"
                }
            )
        
        # Create signature
        signature = LeaseSignature(
            lease_id=lease_id,
            user_id=landlord_id,
            role="landlord",
            signature_text=sign_data.signature,
            signed_at=sign_data.signed_at or datetime.now(timezone.utc),
            method="manual",
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(signature)
        
        # Update lease status
        lease.status = LeaseStatus.COUNTER_SIGNED
        self.db.commit()
        self.db.refresh(lease)
        
        # Audit log
        self._log_audit(
            action="lease_counter_signed",
            target_type="lease",
            target_id=lease_id,
            actor_id=landlord_id,
            meta={
                "role": "landlord",
                "method": "manual"
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease_id, {
            "type": "LEASE_STATUS_CHANGED",
            "lease_id": lease_id,
            "status": lease.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_counter_signed",
            lease_id=lease_id,
            landlord_id=landlord_id
        )
        
        return lease
    
    async def activate_lease(self, lease_id: int, landlord_id: int) -> Lease:
        """
        Activate lease (move to active status).
        
        **Enterprise-grade status enforcement:**
        - Only allowed when lease.status = COUNTER_SIGNED (strict enforcement)
        - Requires: tenant_signed = True, landlord_signed = True, current_date >= start_date
        
        **Status transition:** COUNTER_SIGNED → ACTIVE
        **Application status:** ACTIVE_LEASE (if application_id exists)
        """
        lease = self.get_lease_by_id(lease_id)
        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found"
            )
        
        # Validate landlord
        property = self.db.query(Property).filter(Property.id == lease.property_id).first()
        if not property or property.owner_id != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - you don't own this property"
            )
        
        # Strict status enforcement: only COUNTER_SIGNED allowed
        if lease.status != LeaseStatus.COUNTER_SIGNED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot activate lease in {lease.status.value} status. Lease must be COUNTER_SIGNED (both parties must sign).",
                    "field": "lease_status",
                    "current_status": lease.status.value
                }
            )
        
        # Check tenant has signed
        tenant_signature = self.db.query(LeaseSignature).filter(
            and_(
                LeaseSignature.lease_id == lease_id,
                LeaseSignature.role == "tenant"
            )
        ).first()
        
        if not tenant_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Tenant must sign the lease before activation",
                    "field": "lease_status"
                }
            )
        
        # Check landlord has signed
        landlord_signature = self.db.query(LeaseSignature).filter(
            and_(
                LeaseSignature.lease_id == lease_id,
                LeaseSignature.role == "landlord"
            )
        ).first()
        
        if not landlord_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": "Landlord must counter-sign the lease before activation",
                    "field": "lease_status"
                }
            )
        
        # Check start_date requirement
        today = datetime.now(timezone.utc).date()
        if lease.start_date:
            start_date = lease.start_date.date() if isinstance(lease.start_date, datetime) else lease.start_date
            if today < start_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "ValidationError",
                        "message": f"Cannot activate lease before start date. Start date is {start_date}, today is {today}.",
                        "field": "start_date",
                        "start_date": str(start_date),
                        "current_date": str(today)
                    }
                )
        
        # Update lease status
        lease.status = LeaseStatus.ACTIVE
        lease.activated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(lease)
        
        # Update application status to ACTIVE_LEASE (only if application_id exists)
        if lease.application_id:
            app = self.db.query(Application).filter(Application.id == lease.application_id).first()
            if app:
                app.status = ApplicationStatus.ACTIVE_LEASE
                self.db.commit()
            
            # Withdraw other applications for the same tenant and property
            self.db.query(Application).filter(
                and_(
                    Application.applicant_id == lease.tenant_id,
                    Application.property_id == lease.property_id,
                    Application.id != lease.application_id,
                    Application.status.in_([
                        ApplicationStatus.DRAFT,
                        ApplicationStatus.SUBMITTED,
                        ApplicationStatus.REVIEWED,
                        ApplicationStatus.APPROVED
                    ])
                )
            ).update({"status": ApplicationStatus.WITHDRAWN}, synchronize_session=False)
            self.db.commit()
        
        # Make property unavailable
        property.is_active = False
        self.db.commit()
        
        # Audit log
        self._log_audit(
            action="lease_activated",
            target_type="lease",
            target_id=lease_id,
            actor_id=landlord_id,
            meta={
                "property_id": lease.property_id,
                "tenant_id": lease.tenant_id,
                "application_id": lease.application_id
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease_id, {
            "type": "LEASE_ACTIVATED",
            "lease_id": lease_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_activated",
            lease_id=lease_id,
            landlord_id=landlord_id,
            tenant_id=lease.tenant_id,
            property_id=lease.property_id,
            application_id=lease.application_id
        )
        
        return lease
    
    async def terminate_lease(self, lease_id: int, user_id: int, reason: Optional[str] = None) -> Lease:
        """
        Terminate lease (move to terminated status).
        
        **Enterprise-grade status enforcement:**
        - Only allowed when lease.status = ACTIVE
        - Can be called by landlord or tenant (with proper authorization)
        
        **Status transition:** ACTIVE → TERMINATED
        **Application status:** CLOSED (if application_id exists)
        """
        lease = self.get_lease_by_id(lease_id)
        if not lease:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lease not found"
            )
        
        # Validate user authorization (landlord or tenant)
        is_landlord = lease.landlord_id == user_id
        is_tenant = lease.tenant_id == user_id
        
        if not (is_landlord or is_tenant):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions - only landlord or tenant can terminate this lease"
            )
        
        # Strict status enforcement: only ACTIVE allowed
        if lease.status != LeaseStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "ValidationError",
                    "message": f"Cannot terminate lease in {lease.status.value} status. Lease must be ACTIVE.",
                    "field": "lease_status",
                    "current_status": lease.status.value
                }
            )
        
        # Update lease status
        lease.status = LeaseStatus.TERMINATED
        self.db.commit()
        self.db.refresh(lease)
        
        # Update application status to CLOSED (only if application_id exists)
        if lease.application_id:
            app = self.db.query(Application).filter(Application.id == lease.application_id).first()
            if app:
                app.status = ApplicationStatus.CLOSED
                self.db.commit()
        
        # Make property available again
        property = self.db.query(Property).filter(Property.id == lease.property_id).first()
        if property:
            property.is_active = True
            self.db.commit()
        
        # Audit log
        self._log_audit(
            action="lease_terminated",
            target_type="lease",
            target_id=lease_id,
            actor_id=user_id,
            meta={
                "property_id": lease.property_id,
                "tenant_id": lease.tenant_id,
                "application_id": lease.application_id,
                "reason": reason,
                "terminated_by": "landlord" if is_landlord else "tenant"
            }
        )
        
        # Publish real-time event (fire-and-forget)
        self._publish_event_async(lease_id, {
            "type": "LEASE_TERMINATED",
            "lease_id": lease_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(
            "lease_terminated",
            lease_id=lease_id,
            terminated_by=user_id,
            property_id=lease.property_id,
            tenant_id=lease.tenant_id,
            application_id=lease.application_id,
            reason=reason
        )
        
        return lease
    
    def get_landlord_leases(self, landlord_id: int, status: Optional[LeaseStatus] = None) -> List[Lease]:
        """Get all leases for a landlord"""
        query = self.db.query(Lease).filter(Lease.landlord_id == landlord_id)
        
        if status:
            query = query.filter(Lease.status == status)
        
        return query.order_by(Lease.created_at.desc()).all()
    
    def get_tenant_leases(self, tenant_id: int, status: Optional[LeaseStatus] = None) -> List[Lease]:
        """Get all leases for a tenant"""
        query = self.db.query(Lease).filter(Lease.tenant_id == tenant_id)
        
        if status:
            query = query.filter(Lease.status == status)
        
        return query.order_by(Lease.created_at.desc()).all()
    
    def get_property_leases(self, property_id: int) -> List[Lease]:
        """Get all leases for a property"""
        return self.db.query(Lease).filter(
            Lease.property_id == property_id
        ).order_by(Lease.created_at.desc()).all()
    
    async def auto_activate_leases_on_start_date(self) -> int:
        """
        Automatic lease activation - called by scheduled job (e.g., cron).
        
        **Enterprise-grade automation:**
        - Finds all leases with status = COUNTER_SIGNED
        - Activates leases where start_date <= today
        - Returns count of activated leases
        
        **Usage:** Call this method daily (e.g., via cron job or scheduled task)
        """
        today = datetime.now(timezone.utc).date()
        
        # Find leases ready for activation
        leases_to_activate = self.db.query(Lease).filter(
            and_(
                Lease.status == LeaseStatus.COUNTER_SIGNED,
                Lease.start_date <= today
            )
        ).all()
        
        activated_count = 0
        
        for lease in leases_to_activate:
            try:
                # Verify both signatures exist
                tenant_sig = self.db.query(LeaseSignature).filter(
                    and_(
                        LeaseSignature.lease_id == lease.id,
                        LeaseSignature.role == "tenant"
                    )
                ).first()
                
                landlord_sig = self.db.query(LeaseSignature).filter(
                    and_(
                        LeaseSignature.lease_id == lease.id,
                        LeaseSignature.role == "landlord"
                    )
                ).first()
                
                if tenant_sig and landlord_sig:
                    # Activate lease
                    lease.status = LeaseStatus.ACTIVE
                    lease.activated_at = datetime.now(timezone.utc)
                    self.db.commit()
                    
                    # Update application if linked
                    if lease.application_id:
                        app = self.db.query(Application).filter(Application.id == lease.application_id).first()
                        if app:
                            app.status = ApplicationStatus.ACTIVE_LEASE
                            self.db.commit()
                    
                    # Make property unavailable
                    property = self.db.query(Property).filter(Property.id == lease.property_id).first()
                    if property:
                        property.is_active = False
                        self.db.commit()
                    
                    # Publish real-time event (fire-and-forget)
                    self._publish_event_async(lease.id, {
                        "type": "LEASE_ACTIVATED",
                        "lease_id": lease.id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    activated_count += 1
                    
                    logger.info(
                        "lease_auto_activated",
                        lease_id=lease.id,
                        property_id=lease.property_id,
                        tenant_id=lease.tenant_id,
                        start_date=str(lease.start_date)
                    )
            except Exception as e:
                logger.error(
                    "lease_auto_activation_failed",
                    lease_id=lease.id,
                    error=str(e)
                )
                self.db.rollback()
                continue
        
        return activated_count
    
    def _publish_event_async(self, lease_id: int, event: dict):
        """
        Publish event asynchronously from sync method (fire-and-forget).
        Enterprise-grade: Non-blocking event publishing.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Event loop is running, create task
                asyncio.create_task(event_bus.publish(lease_id, event))
            else:
                # No running loop, run in new loop
                asyncio.run(event_bus.publish(lease_id, event))
        except RuntimeError:
            # No event loop available, skip event publishing
            logger.debug(
                "lease_event_skip_no_loop",
                lease_id=lease_id,
                event_type=event.get("type")
            )
        except Exception as e:
            # Don't fail the main operation if event publishing fails
            logger.error(
                "lease_event_publish_error",
                lease_id=lease_id,
                error=str(e)
            )
    
    def _log_audit(self, action: str, target_type: str, target_id: int, actor_id: int, meta: dict):
        """Log audit event"""
        audit_log = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            meta=meta
        )
        self.db.add(audit_log)
        self.db.commit()

