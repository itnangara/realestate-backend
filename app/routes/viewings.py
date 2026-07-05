"""
Viewing routes for property viewing requests.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.models.viewing import ViewingRequest, ViewingStatus
from app.schemas.viewing import (
    ViewingRequestCancel,
    ViewingRequestCreate,
    ViewingRequestDecision,
    ViewingRequestListResponse,
    ViewingRequestResponse,
)
from app.services.viewing_service import ViewingService, viewing_pages
from app.utils.database import get_db


router = APIRouter(prefix="/viewings", tags=["Viewings"])


def _user_summary(user):
    if not user:
        return None
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
    }


def _property_summary(property_obj):
    if not property_obj:
        return None
    return {
        "id": property_obj.id,
        "title": property_obj.title,
        "address": property_obj.address,
        "city": property_obj.city,
        "listing_type": property_obj.listing_type.value if hasattr(property_obj.listing_type, "value") else property_obj.listing_type,
        "display_price": property_obj.display_price,
    }


def _build_viewing_response(viewing: ViewingRequest) -> ViewingRequestResponse:
    return ViewingRequestResponse(
        id=viewing.id,
        property_id=viewing.property_id,
        requester_id=viewing.requester_id,
        assigned_to_id=viewing.assigned_to_id,
        status=viewing.status,
        requested_slots=viewing.requested_slots or [],
        confirmed_slot=viewing.confirmed_slot,
        message=viewing.message,
        response_note=viewing.response_note,
        cancellation_reason=viewing.cancellation_reason,
        created_at=viewing.created_at,
        updated_at=viewing.updated_at,
        responded_at=viewing.responded_at,
        is_active=viewing.is_active,
        property=_property_summary(viewing.property),
        requester=_user_summary(viewing.requester),
        assigned_to=_user_summary(viewing.assigned_to),
    )


@router.post("", response_model=ViewingRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_viewing_request(
    request_data: ViewingRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    viewing = service.create_request(request_data, current_user)
    return _build_viewing_response(viewing)


@router.get("", response_model=ViewingRequestListResponse)
async def list_viewing_requests(
    status_filter: ViewingStatus | None = Query(None, alias="status"),
    property_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    items, total, status_counts = service.list_requests(
        user=current_user,
        viewing_status=status_filter,
        property_id=property_id,
        page=page,
        limit=limit,
    )
    return ViewingRequestListResponse(
        items=[_build_viewing_response(item) for item in items],
        total=total,
        page=page,
        limit=limit,
        pages=viewing_pages(total, limit),
        status_counts=status_counts,
    )


@router.get("/{viewing_id}", response_model=ViewingRequestResponse)
async def get_viewing_request(
    viewing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    viewing = service.get_request(viewing_id, current_user)
    return _build_viewing_response(viewing)


@router.post("/{viewing_id}/confirm", response_model=ViewingRequestResponse)
async def confirm_viewing_request(
    viewing_id: int,
    decision: ViewingRequestDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if decision.confirmed_slot is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="confirmed_slot is required")

    service = ViewingService(db)
    viewing = service.confirm_request(
        viewing_id=viewing_id,
        confirmed_slot=decision.confirmed_slot,
        actor=current_user,
        response_note=decision.response_note,
    )
    return _build_viewing_response(viewing)


@router.post("/{viewing_id}/decline", response_model=ViewingRequestResponse)
async def decline_viewing_request(
    viewing_id: int,
    decision: ViewingRequestDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    viewing = service.decline_request(viewing_id, current_user, decision.response_note)
    return _build_viewing_response(viewing)


@router.post("/{viewing_id}/cancel", response_model=ViewingRequestResponse)
async def cancel_viewing_request(
    viewing_id: int,
    cancel_data: ViewingRequestCancel,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    viewing = service.cancel_request(viewing_id, current_user, cancel_data.reason)
    return _build_viewing_response(viewing)


@router.post("/{viewing_id}/complete", response_model=ViewingRequestResponse)
async def complete_viewing_request(
    viewing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ViewingService(db)
    viewing = service.complete_request(viewing_id, current_user)
    return _build_viewing_response(viewing)
