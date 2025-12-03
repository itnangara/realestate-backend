"""
Maintenance service for managing maintenance requests
Enterprise-grade business logic with proper validation and audit logging
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from fastapi import HTTPException, status
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal

from app.models.maintenance import (
    MaintenanceRequest, MaintenanceStatusHistory, MaintenanceAttachment, 
    MaintenanceActivity, MaintenanceStatus, MaintenancePriority, MaintenanceCategory
)
from app.models.property import Property
from app.models.user import User
from app.schemas.maintenance import (
    MaintenanceRequestCreate, MaintenanceRequestUpdate, MaintenanceRequestAssign,
    MaintenanceCommentCreate
)
from app.core.logger import get_logger

logger = get_logger(__name__)


# Valid status transitions - enterprise-grade workflow compliance
VALID_TRANSITIONS: Dict[str, List[str]] = {
    MaintenanceStatus.REPORTED: [MaintenanceStatus.REVIEWING, MaintenanceStatus.REJECTED, MaintenanceStatus.CANCELLED],
    MaintenanceStatus.REVIEWING: [MaintenanceStatus.ASSIGNED, MaintenanceStatus.REJECTED, MaintenanceStatus.CANCELLED],
    MaintenanceStatus.ASSIGNED: [MaintenanceStatus.ACKNOWLEDGED, MaintenanceStatus.CANCELLED],
    MaintenanceStatus.ACKNOWLEDGED: [MaintenanceStatus.IN_PROGRESS],
    MaintenanceStatus.IN_PROGRESS: [MaintenanceStatus.COMPLETED],
    MaintenanceStatus.COMPLETED: [MaintenanceStatus.VERIFIED, MaintenanceStatus.REOPENED],
    MaintenanceStatus.VERIFIED: [MaintenanceStatus.CLOSED, MaintenanceStatus.REOPENED],
    MaintenanceStatus.CLOSED: [MaintenanceStatus.REOPENED],
    MaintenanceStatus.REOPENED: [MaintenanceStatus.ASSIGNED],  # Loops back to ASSIGNED
    MaintenanceStatus.REJECTED: [],  # Terminal state
    MaintenanceStatus.CANCELLED: [],  # Terminal state
}


def can_transition(current_status: MaintenanceStatus, new_status: MaintenanceStatus) -> bool:
    """Check if status transition is valid"""
    return new_status.value in VALID_TRANSITIONS.get(current_status.value, [])


class MaintenanceService:
    """Maintenance service for managing maintenance requests"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_request(self, request_data: MaintenanceRequestCreate, tenant_id: int, reported_by_id: int) -> MaintenanceRequest:
        """
        Create a new maintenance request.
        
        **Business Rules:**
        - Only tenants can create requests
        - Property must exist and be accessible
        - Request starts in REPORTED status
        - Emergency priority triggers immediate notification (future enhancement)
        """
        # Validate property exists
        property_obj = self.db.query(Property).filter(Property.id == request_data.property_id).first()
        if not property_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        
        # Create request
        request = MaintenanceRequest(
            property_id=request_data.property_id,
            unit_number=request_data.unit_number,
            tenant_id=tenant_id,
            reported_by_id=reported_by_id,
            title=request_data.title,
            description=request_data.description,
            priority=request_data.priority,
            category=request_data.category,
            access_instructions=request_data.access_instructions,
            preferred_date=request_data.preferred_date,
            preferred_time=request_data.preferred_time,
            status=MaintenanceStatus.REPORTED,
            is_active=True
        )
        
        self.db.add(request)
        self.db.flush()  # Get ID before commit
        
        # Create initial status history entry
        status_history = MaintenanceStatusHistory(
            request_id=request.id,
            changed_by_id=reported_by_id,
            old_status=None,
            new_status=MaintenanceStatus.REPORTED.value,
            note="Request created"
        )
        self.db.add(status_history)
        
        # Create activity log
        activity = MaintenanceActivity(
            request_id=request.id,
            actor_id=reported_by_id,
            action_type="request_created",
            description=f"Maintenance request created: {request_data.title}",
            action_data={"priority": request_data.priority.value, "category": request_data.category.value}
        )
        self.db.add(activity)
        
        self.db.commit()
        self.db.refresh(request)
        
        logger.info(
            "maintenance_request_created",
            request_id=request.id,
            property_id=request_data.property_id,
            tenant_id=tenant_id,
            priority=request_data.priority.value
        )
        
        return request
    
    def get_request(self, request_id: int, user: User) -> MaintenanceRequest:
        """
        Get a maintenance request by ID with authorization check.
        
        **Authorization:**
        - Tenant: Can only view their own requests
        - Landlord/Agent: Can view requests for their properties
        - Staff: Can view assigned requests
        """
        request = self.db.query(MaintenanceRequest).filter(
            MaintenanceRequest.id == request_id,
            MaintenanceRequest.is_active == True
        ).first()
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance request not found"
            )
        
        # Authorization check
        is_tenant = user.has_role("tenant") and request.tenant_id == user.id
        # Enterprise-grade: Use unified ownership check instead of direct owner_id
        from app.utils.property_ownership import is_property_owner
        is_landlord = (user.has_role("landlord") or user.has_role("agent")) and is_property_owner(self.db, user.id, request.property_id)
        is_staff = request.assigned_staff_id == user.id
        is_admin = user.has_role("admin")
        
        if not (is_tenant or is_landlord or is_staff or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this maintenance request"
            )
        
        return request
    
    def get_request_by_id(self, request_id: int) -> Optional[MaintenanceRequest]:
        """
        Get a maintenance request by ID without authorization check.
        Used internally by service methods that perform their own authorization.
        """
        return self.db.query(MaintenanceRequest).filter(
            MaintenanceRequest.id == request_id,
            MaintenanceRequest.is_active == True
        ).first()
    
    def list_requests(
        self,
        user: User,
        status: Optional[MaintenanceStatus] = None,
        property_id: Optional[int] = None,
        priority: Optional[MaintenancePriority] = None,
        category: Optional[MaintenanceCategory] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[MaintenanceRequest], int]:
        """
        List maintenance requests with role-based filtering.
        
        **Role-based filtering:**
        - Tenant: Only their own requests
        - Landlord/Agent: Requests for their properties
        - Staff: Assigned requests
        - Admin: All requests
        """
        query = self.db.query(MaintenanceRequest).filter(MaintenanceRequest.is_active == True)
        
        # Role-based filtering
        if user.has_role("tenant"):
            query = query.filter(MaintenanceRequest.tenant_id == user.id)
        elif user.has_role("landlord") or user.has_role("agent"):
            # Enterprise-grade: Get properties owned/managed by user using unified ownership model
            from app.models.user_property import UserProperty, RelationshipType
            
            # Get property IDs from user_properties table exclusively
            property_ids = [
                up.property_id for up in self.db.query(UserProperty)
                .filter(
                    UserProperty.user_id == user.id,
                    UserProperty.relationship_type.in_([RelationshipType.LANDLORD, RelationshipType.AGENT, RelationshipType.ADMIN])
                ).all()
            ]
            
            if property_ids:
                query = query.filter(MaintenanceRequest.property_id.in_(property_ids))
            else:
                # No properties - return empty result
                query = query.filter(MaintenanceRequest.id == -1)
        elif user.has_role("admin"):
            # Admin sees all
            pass
        else:
            # Staff sees assigned requests
            query = query.filter(MaintenanceRequest.assigned_staff_id == user.id)
        
        # Apply filters
        if status:
            query = query.filter(MaintenanceRequest.status == status)
        if property_id:
            query = query.filter(MaintenanceRequest.property_id == property_id)
        if priority:
            query = query.filter(MaintenanceRequest.priority == priority)
        if category:
            query = query.filter(MaintenanceRequest.category == category)
        if search:
            search_filter = or_(
                MaintenanceRequest.title.ilike(f"%{search}%"),
                MaintenanceRequest.description.ilike(f"%{search}%"),
                MaintenanceRequest.unit_number.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)
        
        # Get total count
        total = query.count()
        
        # Pagination
        offset = (page - 1) * limit
        requests = query.order_by(desc(MaintenanceRequest.created_at)).offset(offset).limit(limit).all()
        
        return requests, total
    
    def update_status(
        self,
        request_id: int,
        new_status: MaintenanceStatus,
        changed_by: User,
        note: Optional[str] = None
    ) -> MaintenanceRequest:
        """
        Update maintenance request status with validation.
        
        **Business Rules:**
        - Status transitions must be valid
        - Authorization checks based on role and current status
        - Creates status history and activity log entries
        """
        request = self.get_request(request_id, changed_by)
        
        # Check if transition is valid
        if not can_transition(request.status, new_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition: {request.status.value} → {new_status.value}"
            )
        
        # Authorization checks for specific transitions
        if new_status == MaintenanceStatus.REVIEWING:
            if not (changed_by.has_role("landlord") or changed_by.has_role("agent")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only landlords/agents can review requests"
                )
        
        if new_status == MaintenanceStatus.ASSIGNED:
            if not (changed_by.has_role("landlord") or changed_by.has_role("agent")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only landlords/agents can assign requests"
                )
        
        if new_status == MaintenanceStatus.ACKNOWLEDGED:
            if request.assigned_staff_id != changed_by.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only assigned staff can acknowledge requests"
                )
        
        if new_status == MaintenanceStatus.IN_PROGRESS:
            if request.assigned_staff_id != changed_by.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only assigned staff can start work"
                )
            if request.status != MaintenanceStatus.ACKNOWLEDGED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Request must be acknowledged before starting work"
                )
        
        if new_status == MaintenanceStatus.COMPLETED:
            if request.assigned_staff_id != changed_by.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only assigned staff can mark as completed"
                )
        
        if new_status == MaintenanceStatus.VERIFIED:
            if not (changed_by.has_role("landlord") or changed_by.has_role("agent")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only landlords/agents can verify completion"
                )
        
        if new_status == MaintenanceStatus.CLOSED:
            if not (changed_by.has_role("tenant") or changed_by.has_role("landlord") or changed_by.has_role("agent")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only tenant or landlord can close requests"
                )
        
        # Update status
        old_status = request.status
        request.status = new_status
        request.last_status_change = datetime.now(timezone.utc)
        
        # Create status history entry
        status_history = MaintenanceStatusHistory(
            request_id=request.id,
            changed_by_id=changed_by.id,
            old_status=old_status.value,
            new_status=new_status.value,
            note=note
        )
        self.db.add(status_history)
        
        # Create activity log
        activity = MaintenanceActivity(
            request_id=request.id,
            actor_id=changed_by.id,
            action_type="status_change",
            description=f"Status changed from {old_status.value} to {new_status.value}",
            action_data={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "note": note
            }
        )
        self.db.add(activity)
        
        self.db.commit()
        self.db.refresh(request)
        
        logger.info(
            "maintenance_status_changed",
            request_id=request.id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by=changed_by.id
        )
        
        return request
    
    def assign_request(
        self,
        request_id: int,
        assign_data: MaintenanceRequestAssign,
        assigned_by: User
    ) -> MaintenanceRequest:
        """
        Assign a maintenance request to staff or vendor.
        
        **Business Rules:**
        - Only landlords/agents can assign
        - Can assign to staff member or external vendor
        - Automatically transitions to ASSIGNED status
        """
        request = self.get_request(request_id, assigned_by)
        
        if not (assigned_by.has_role("landlord") or assigned_by.has_role("agent")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only landlords/agents can assign requests"
            )
        
        # Update assignment
        if assign_data.assigned_staff_id:
            # Validate staff exists and has appropriate role
            staff = self.db.query(User).filter(User.id == assign_data.assigned_staff_id).first()
            if not staff:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Staff member not found"
                )
            request.assigned_staff_id = assign_data.assigned_staff_id
            request.external_vendor_name = None
            request.external_vendor_contact = None
        elif assign_data.external_vendor_name:
            request.assigned_staff_id = None
            request.external_vendor_name = assign_data.external_vendor_name
            request.external_vendor_contact = assign_data.external_vendor_contact
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either assigned_staff_id or external_vendor_name must be provided"
            )
        
        # Update status to ASSIGNED if not already
        if request.status != MaintenanceStatus.ASSIGNED:
            if not can_transition(request.status, MaintenanceStatus.ASSIGNED):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot assign request in {request.status.value} status"
                )
            request.status = MaintenanceStatus.ASSIGNED
            request.last_status_change = datetime.now(timezone.utc)
            
            # Create status history
            status_history = MaintenanceStatusHistory(
                request_id=request.id,
                changed_by_id=assigned_by.id,
                old_status=request.status.value,
                new_status=MaintenanceStatus.ASSIGNED.value,
                note=assign_data.note or "Request assigned"
            )
            self.db.add(status_history)
        
        # Create activity log
        activity = MaintenanceActivity(
            request_id=request.id,
            actor_id=assigned_by.id,
            action_type="assignment",
            description=f"Request assigned to {assign_data.assigned_staff_id or assign_data.external_vendor_name}",
            action_data={
                "assigned_staff_id": assign_data.assigned_staff_id,
                "external_vendor_name": assign_data.external_vendor_name,
                "external_vendor_contact": assign_data.external_vendor_contact,
                "note": assign_data.note
            }
        )
        self.db.add(activity)
        
        self.db.commit()
        self.db.refresh(request)
        
        return request
    
    def update_request(
        self,
        request_id: int,
        update_data: MaintenanceRequestUpdate,
        updated_by: User
    ) -> MaintenanceRequest:
        """
        Update maintenance request details.
        
        **Business Rules:**
        - Landlords/agents can update priority, costs, assignment
        - Status updates go through update_status method
        - Tenants cannot update after creation
        """
        request = self.get_request(request_id, updated_by)
        
        # Authorization: Only landlords/agents can update
        if not (updated_by.has_role("landlord") or updated_by.has_role("agent") or updated_by.has_role("admin")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only landlords/agents can update requests"
            )
        
        # Update fields
        if update_data.priority is not None:
            request.priority = update_data.priority
        
        if update_data.assigned_staff_id is not None:
            request.assigned_staff_id = update_data.assigned_staff_id
        
        if update_data.estimated_cost is not None:
            request.estimated_cost = update_data.estimated_cost
        
        if update_data.actual_cost is not None:
            request.actual_cost = update_data.actual_cost
            if updated_by.has_role("landlord") or updated_by.has_role("agent"):
                request.cost_approved_by_id = updated_by.id
        
        if update_data.external_vendor_name is not None:
            request.external_vendor_name = update_data.external_vendor_name
        
        if update_data.external_vendor_contact is not None:
            request.external_vendor_contact = update_data.external_vendor_contact
        
        # Handle status update separately
        if update_data.status is not None:
            return self.update_status(request_id, update_data.status, updated_by, update_data.note)
        
        # Create activity log if any changes
        if any([
            update_data.priority, update_data.assigned_staff_id,
            update_data.estimated_cost, update_data.actual_cost,
            update_data.external_vendor_name, update_data.external_vendor_contact
        ]):
            activity = MaintenanceActivity(
                request_id=request.id,
                actor_id=updated_by.id,
                action_type="request_updated",
                description="Request details updated",
                action_data=update_data.model_dump(exclude_none=True)
            )
            self.db.add(activity)
        
        self.db.commit()
        self.db.refresh(request)
        
        return request
    
    def get_summary(self, user: User) -> Dict[str, int]:
        """Get maintenance request summary statistics"""
        query = self.db.query(
            MaintenanceRequest.status,
            func.count(MaintenanceRequest.id).label('count')
        ).filter(MaintenanceRequest.is_active == True)
        
        # Role-based filtering
        if user.has_role("tenant"):
            query = query.filter(MaintenanceRequest.tenant_id == user.id)
        elif user.has_role("landlord") or user.has_role("agent"):
            # Enterprise-grade: Use unified model exclusively
            from app.models.user_property import UserProperty, RelationshipType
            property_ids = [
                up.property_id for up in self.db.query(UserProperty)
                .filter(
                    UserProperty.user_id == user.id,
                    UserProperty.relationship_type == RelationshipType.LANDLORD
                )
                .all()
            ]
            if not property_ids:
                property_ids = [-1]  # Empty list for subquery
            property_ids = self.db.query(Property.id).filter(Property.id.in_(property_ids)).subquery()
            query = query.filter(MaintenanceRequest.property_id.in_(self.db.query(property_ids)))
        elif not user.has_role("admin"):
            query = query.filter(MaintenanceRequest.assigned_staff_id == user.id)
        
        results = query.group_by(MaintenanceRequest.status).all()
        
        summary = {
            "total": 0,
            "reported": 0,
            "reviewing": 0,
            "assigned": 0,
            "acknowledged": 0,
            "in_progress": 0,
            "completed": 0,
            "verified": 0,
            "closed": 0,
            "reopened": 0,
            "rejected": 0,
            "cancelled": 0,
        }
        
        for status, count in results:
            summary["total"] += count
            status_key = status.value.lower()
            if status_key in summary:
                summary[status_key] = count
        
        return summary
    
    def list_assigned(
        self,
        staff_user: User,
        status: Optional[List[MaintenanceStatus]] = None,
        property_id: Optional[int] = None,
        priority: Optional[MaintenancePriority] = None,
        category: Optional[MaintenanceCategory] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        limit: int = 25
    ) -> Tuple[List[MaintenanceRequest], int]:
        """
        List maintenance requests assigned to staff member.
        
        **Enterprise-grade filtering:**
        - Only returns requests assigned to the staff user
        - Supports multiple status filters
        - Date range filtering
        - Search by title, description, unit
        """
        if not staff_user.has_role("maintenance_staff"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only maintenance staff can access assigned tasks"
            )
        
        # Base query: only assigned to this staff member
        query = self.db.query(MaintenanceRequest).filter(
            MaintenanceRequest.assigned_staff_id == staff_user.id,
            MaintenanceRequest.is_active == True
        )
        
        # Status filter (can be multiple)
        if status:
            query = query.filter(MaintenanceRequest.status.in_(status))
        
        # Other filters
        if property_id:
            query = query.filter(MaintenanceRequest.property_id == property_id)
        if priority:
            query = query.filter(MaintenanceRequest.priority == priority)
        if category:
            query = query.filter(MaintenanceRequest.category == category)
        if date_from:
            query = query.filter(MaintenanceRequest.created_at >= date_from)
        if date_to:
            query = query.filter(MaintenanceRequest.created_at <= date_to)
        if search:
            search_filter = or_(
                MaintenanceRequest.title.ilike(f"%{search}%"),
                MaintenanceRequest.description.ilike(f"%{search}%"),
                MaintenanceRequest.unit_number.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)
        
        # Get total count
        total = query.count()
        
        # Pagination
        offset = (page - 1) * limit
        requests = query.order_by(desc(MaintenanceRequest.created_at)).offset(offset).limit(limit).all()
        
        return requests, total
    
    def acknowledge_request(
        self,
        request_id: int,
        staff_user: User,
        note: Optional[str] = None
    ) -> MaintenanceRequest:
        """
        Staff acknowledges an assigned request.
        
        **Business Rules:**
        - Only assigned staff can acknowledge
        - Status must be ASSIGNED
        - Transitions to ACKNOWLEDGED
        """
        request = self.get_request_by_id(request_id)
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance request not found"
            )
        
        if request.assigned_staff_id != staff_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is not assigned to you"
            )
        
        if request.status != MaintenanceStatus.ASSIGNED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot acknowledge request in {request.status.value} status. Must be ASSIGNED."
            )
        
        return self.update_status(
            request_id=request_id,
            new_status=MaintenanceStatus.ACKNOWLEDGED,
            changed_by=staff_user,
            note=note or "Request acknowledged by staff"
        )
    
    def start_request(
        self,
        request_id: int,
        staff_user: User,
        started_at: Optional[datetime] = None
    ) -> MaintenanceRequest:
        """
        Staff starts work on a request.
        
        **Business Rules:**
        - Only assigned staff can start
        - Status must be ACKNOWLEDGED
        - Transitions to IN_PROGRESS
        """
        request = self.get_request_by_id(request_id)
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance request not found"
            )
        
        if request.assigned_staff_id != staff_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is not assigned to you"
            )
        
        if request.status != MaintenanceStatus.ACKNOWLEDGED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot start request in {request.status.value} status. Must be ACKNOWLEDGED."
            )
        
        note = f"Work started at {started_at.isoformat() if started_at else datetime.now(timezone.utc).isoformat()}"
        
        return self.update_status(
            request_id=request_id,
            new_status=MaintenanceStatus.IN_PROGRESS,
            changed_by=staff_user,
            note=note
        )
    
    def complete_request(
        self,
        request_id: int,
        staff_user: User,
        actual_cost: Optional[Decimal] = None,
        note: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> MaintenanceRequest:
        """
        Staff marks request as completed.
        
        **Business Rules:**
        - Only assigned staff can complete
        - Status must be IN_PROGRESS
        - Transitions to COMPLETED
        - Can include actual cost (requires manager approval)
        """
        request = self.get_request_by_id(request_id)
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance request not found"
            )
        
        if request.assigned_staff_id != staff_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is not assigned to you"
            )
        
        if request.status != MaintenanceStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot complete request in {request.status.value} status. Must be IN_PROGRESS."
            )
        
        # Update actual cost if provided
        if actual_cost is not None:
            request.actual_cost = actual_cost
            # Cost approval will be done by manager later
        
        completion_note = note or f"Work completed at {completed_at.isoformat() if completed_at else datetime.now(timezone.utc).isoformat()}"
        if actual_cost is not None:
            completion_note += f" | Actual cost: ${actual_cost}"
        
        return self.update_status(
            request_id=request_id,
            new_status=MaintenanceStatus.COMPLETED,
            changed_by=staff_user,
            note=completion_note
        )
    
    def add_note(
        self,
        request_id: int,
        staff_user: User,
        note_text: str
    ) -> MaintenanceActivity:
        """
        Add an internal note to a maintenance request.
        
        **Business Rules:**
        - Only assigned staff can add notes
        - Creates MaintenanceActivity entry
        """
        request = self.get_request_by_id(request_id)
        
        if not request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Maintenance request not found"
            )
        
        if request.assigned_staff_id != staff_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is not assigned to you"
            )
        
        # Create activity log entry
        activity = MaintenanceActivity(
            request_id=request.id,
            actor_id=staff_user.id,
            action_type="note",
            description=note_text,
            action_data={"note": note_text}
        )
        self.db.add(activity)
        self.db.commit()
        self.db.refresh(activity)
        
        logger.info(
            "maintenance_note_added",
            request_id=request.id,
            staff_id=staff_user.id,
            note_length=len(note_text)
        )
        
        return activity

