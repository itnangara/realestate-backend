"""
Viewing request schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.viewing import ViewingStatus


class ViewingRequestCreate(BaseModel):
    """Create a property viewing request."""

    property_id: int = Field(..., description="Property to view")
    requested_slots: List[datetime] = Field(..., min_length=1, max_length=5, description="Preferred viewing slots")
    message: Optional[str] = Field(None, max_length=2000, description="Optional note to the owner or agent")

    @field_validator("requested_slots")
    @classmethod
    def validate_requested_slots(cls, slots: List[datetime]) -> List[datetime]:
        unique_slots = {slot.isoformat() for slot in slots}
        if len(unique_slots) != len(slots):
            raise ValueError("requested_slots must not contain duplicates")
        return slots


class ViewingRequestDecision(BaseModel):
    """Confirm or decline a viewing request."""

    confirmed_slot: Optional[datetime] = Field(None, description="Confirmed viewing slot")
    response_note: Optional[str] = Field(None, max_length=2000, description="Optional response note")


class ViewingRequestCancel(BaseModel):
    """Cancel a viewing request."""

    reason: Optional[str] = Field(None, max_length=2000, description="Cancellation reason")


class ViewingRequestResponse(BaseModel):
    """Viewing request response."""

    id: int
    property_id: int
    requester_id: int
    assigned_to_id: Optional[int] = None
    status: ViewingStatus
    requested_slots: List[datetime]
    confirmed_slot: Optional[datetime] = None
    message: Optional[str] = None
    response_note: Optional[str] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime] = None
    is_active: bool
    property: Optional[Dict[str, Any]] = None
    requester: Optional[Dict[str, Any]] = None
    assigned_to: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ViewingRequestListResponse(BaseModel):
    """Paginated viewing request list."""

    items: List[ViewingRequestResponse]
    total: int
    page: int
    limit: int
    pages: int
    status_counts: Dict[str, int]
