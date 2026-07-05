"""
Viewing service for property viewing requests.
"""

from datetime import datetime, timezone
import math
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.property import ListingType, Property, PropertyStatus
from app.models.user import User
from app.models.user_property import RelationshipType, UserProperty
from app.models.viewing import ViewingRequest, ViewingStatus
from app.schemas.viewing import ViewingRequestCreate
from app.core.logger import get_logger

logger = get_logger(__name__)


VIEWING_MANAGER_RELATIONSHIPS = [
    RelationshipType.LANDLORD,
    RelationshipType.SELLER,
    RelationshipType.AGENT,
    RelationshipType.ADMIN,
]


class ViewingService:
    """Business logic for viewing requests."""

    def __init__(self, db: Session):
        self.db = db

    def create_request(self, data: ViewingRequestCreate, requester: User) -> ViewingRequest:
        property_obj = self._get_bookable_property(data.property_id, requester)
        assigned_to_id = self._resolve_viewing_manager(property_obj)

        if assigned_to_id == requester.id and not requester.has_role("admin"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot request a viewing for your own property",
            )

        viewing = ViewingRequest(
            property_id=property_obj.id,
            requester_id=requester.id,
            assigned_to_id=assigned_to_id,
            requested_slots=[slot.isoformat() for slot in data.requested_slots],
            message=data.message,
            status=ViewingStatus.PENDING,
            is_active=True,
        )

        self.db.add(viewing)
        self.db.commit()
        self.db.refresh(viewing)

        logger.info(
            "viewing_request_created",
            viewing_id=viewing.id,
            property_id=property_obj.id,
            requester_id=requester.id,
            assigned_to_id=assigned_to_id,
        )

        return viewing

    def get_request(self, viewing_id: int, user: User) -> ViewingRequest:
        viewing = self.db.query(ViewingRequest).filter(
            ViewingRequest.id == viewing_id,
            ViewingRequest.is_active == True,
        ).first()

        if not viewing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Viewing request not found")

        if not self._can_access_viewing(viewing, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this viewing request",
            )

        return viewing

    def list_requests(
        self,
        user: User,
        viewing_status: Optional[ViewingStatus] = None,
        property_id: Optional[int] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[ViewingRequest], int, Dict[str, int]]:
        query = self.db.query(ViewingRequest).filter(ViewingRequest.is_active == True)

        if user.has_role("admin"):
            pass
        elif self._has_manager_role(user):
            managed_property_ids = self._managed_property_ids(user.id)
            query = query.filter(
                or_(
                    ViewingRequest.requester_id == user.id,
                    ViewingRequest.assigned_to_id == user.id,
                    ViewingRequest.property_id.in_(managed_property_ids) if managed_property_ids else ViewingRequest.id == -1,
                )
            )
        else:
            query = query.filter(ViewingRequest.requester_id == user.id)

        if viewing_status:
            query = query.filter(ViewingRequest.status == viewing_status)
        if property_id:
            query = query.filter(ViewingRequest.property_id == property_id)

        total = query.count()
        status_counts: Dict[str, int] = {s.value: 0 for s in ViewingStatus}
        status_counts["all"] = int(total)

        db_counts = query.with_entities(ViewingRequest.status, func.count(ViewingRequest.id)).group_by(ViewingRequest.status).all()
        for st, count in db_counts:
            key = st.value if hasattr(st, "value") else str(st)
            status_counts[key] = int(count)

        offset = (page - 1) * limit
        items = query.order_by(ViewingRequest.created_at.desc()).offset(offset).limit(limit).all()

        return items, total, status_counts

    def confirm_request(
        self,
        viewing_id: int,
        confirmed_slot: datetime,
        actor: User,
        response_note: Optional[str] = None,
    ) -> ViewingRequest:
        viewing = self.get_request(viewing_id, actor)
        self._require_manager(viewing, actor)

        if viewing.status != ViewingStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending viewings can be confirmed")

        requested_slots = self._requested_slot_datetimes(viewing)
        if confirmed_slot not in requested_slots:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="confirmed_slot must be one of the requested slots",
            )

        viewing.status = ViewingStatus.CONFIRMED
        viewing.confirmed_slot = confirmed_slot
        viewing.response_note = response_note
        viewing.responded_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(viewing)
        return viewing

    def decline_request(
        self,
        viewing_id: int,
        actor: User,
        response_note: Optional[str] = None,
    ) -> ViewingRequest:
        viewing = self.get_request(viewing_id, actor)
        self._require_manager(viewing, actor)

        if viewing.status != ViewingStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending viewings can be declined")

        viewing.status = ViewingStatus.DECLINED
        viewing.response_note = response_note
        viewing.responded_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(viewing)
        return viewing

    def cancel_request(self, viewing_id: int, actor: User, reason: Optional[str] = None) -> ViewingRequest:
        viewing = self.get_request(viewing_id, actor)

        if viewing.status not in [ViewingStatus.PENDING, ViewingStatus.CONFIRMED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only pending or confirmed viewings can be cancelled",
            )

        if not (actor.has_role("admin") or viewing.requester_id == actor.id or self._is_viewing_manager(viewing, actor)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot cancel this viewing request")

        viewing.status = ViewingStatus.CANCELLED
        viewing.cancellation_reason = reason
        viewing.responded_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(viewing)
        return viewing

    def complete_request(self, viewing_id: int, actor: User) -> ViewingRequest:
        viewing = self.get_request(viewing_id, actor)
        self._require_manager(viewing, actor)

        if viewing.status != ViewingStatus.CONFIRMED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only confirmed viewings can be completed")

        viewing.status = ViewingStatus.COMPLETED
        viewing.responded_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(viewing)
        return viewing

    def _get_bookable_property(self, property_id: int, requester: User) -> Property:
        property_obj = self.db.query(Property).filter(
            Property.id == property_id,
            Property.is_active == True,
            Property.status != PropertyStatus.DELETED,
        ).first()

        if not property_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

        if property_obj.status != PropertyStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active properties can be viewed")

        if property_obj.listing_type not in [ListingType.FOR_SALE, ListingType.FOR_RENT, ListingType.FOR_LEASE]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This property is not available for viewing requests")

        return property_obj

    def _resolve_viewing_manager(self, property_obj: Property) -> Optional[int]:
        if property_obj.listing_type == ListingType.FOR_SALE:
            priority = [RelationshipType.SELLER, RelationshipType.AGENT, RelationshipType.LANDLORD, RelationshipType.ADMIN]
        else:
            priority = [RelationshipType.LANDLORD, RelationshipType.AGENT, RelationshipType.SELLER, RelationshipType.ADMIN]

        for relationship_type in priority:
            link = self.db.query(UserProperty).filter(
                UserProperty.property_id == property_obj.id,
                UserProperty.relationship_type == relationship_type,
            ).first()
            if link:
                return link.user_id

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No landlord, seller, or agent is assigned to this property",
        )

    def _managed_property_ids(self, user_id: int) -> List[int]:
        rows = self.db.query(UserProperty.property_id).filter(
            UserProperty.user_id == user_id,
            UserProperty.relationship_type.in_(VIEWING_MANAGER_RELATIONSHIPS),
        ).all()
        return [row.property_id for row in rows]

    def _has_manager_role(self, user: User) -> bool:
        return any(user.has_role(role) for role in ["landlord", "seller", "agent"])

    def _can_access_viewing(self, viewing: ViewingRequest, user: User) -> bool:
        return (
            user.has_role("admin")
            or viewing.requester_id == user.id
            or self._is_viewing_manager(viewing, user)
        )

    def _is_viewing_manager(self, viewing: ViewingRequest, user: User) -> bool:
        if viewing.assigned_to_id == user.id:
            return True

        return self.db.query(UserProperty).filter(
            UserProperty.user_id == user.id,
            UserProperty.property_id == viewing.property_id,
            UserProperty.relationship_type.in_(VIEWING_MANAGER_RELATIONSHIPS),
        ).first() is not None

    def _require_manager(self, viewing: ViewingRequest, user: User) -> None:
        if not (user.has_role("admin") or self._is_viewing_manager(viewing, user)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the landlord, seller, agent, or admin can manage this viewing request",
            )

    def _requested_slot_datetimes(self, viewing: ViewingRequest) -> List[datetime]:
        return [datetime.fromisoformat(slot) for slot in viewing.requested_slots or []]


def viewing_pages(total: int, limit: int) -> int:
    return math.ceil(total / limit) if total > 0 else 0
