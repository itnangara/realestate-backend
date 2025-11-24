"""
Server-Sent Events (SSE) endpoint for real-time lease status updates.

Enterprise-grade real-time solution for pushing lease status changes to clients
without polling or websockets. Uses standard HTTP streaming.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
import asyncio

from app.utils.database import get_db
from app.dependencies.user_dependencies import get_current_user, oauth2_scheme
from app.services.auth_service import AuthService
from app.models.user import User
from app.models.lease import Lease
from app.core.event_bus import event_bus
from app.core.logger import get_logger

router = APIRouter(prefix="/leases", tags=["Leases", "SSE"])
logger = get_logger(__name__)


@router.get(
    "/{lease_id}/events",
    summary="Subscribe to lease events (SSE)",
    response_description="Server-Sent Events stream for real-time lease updates"
)
async def lease_events(
    lease_id: int,
    request: Request,
    token: Optional[str] = Query(None, description="Bearer token (required for EventSource)"),
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events stream for real-time lease status updates.
    
    **Enterprise-grade real-time solution:**
    - Maintains a persistent HTTP connection
    - Pushes events instantly when lease status changes
    - No polling required
    - Automatic reconnection on disconnect
    
    **Authorization:**
    - Tenant can subscribe to their own leases
    - Landlord can subscribe to leases for their properties
    
    **Event Types:**
    - LEASE_STATUS_CHANGED: Status updated (e.g., SENT → SIGNED)
    - LEASE_ACTIVATED: Lease moved to ACTIVE status
    - LEASE_TERMINATED: Lease terminated
    
    **Usage:**
    ```javascript
    const source = new EventSource('/api/leases/123/events');
    source.onmessage = (e) => {
      const data = JSON.parse(e.data);
      // Handle event
    };
    ```
    """
    # Enterprise-grade: EventSource doesn't support custom headers, so accept token as query param
    # Try to get token from query param first, then from Authorization header
    auth_token = token
    if not auth_token:
        # Fallback to Authorization header (for testing with curl/Postman)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]
    
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required. Provide token as query parameter: ?token=YOUR_TOKEN",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Verify token and get user
    auth_service = AuthService(db)
    try:
        email = auth_service.verify_token(auth_token)
        from app.services.user_service import UserService
        user_service = UserService(db)
        current_user = user_service.get_user_by_email(email)
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
    except Exception as e:
        logger.error("sse_auth_failed", lease_id=lease_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Verify lease exists and user has access
    lease = db.query(Lease).filter(Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found"
        )
    
    # Verify access
    is_tenant = current_user.has_role("tenant") and lease.tenant_id == current_user.id
    is_landlord = (current_user.has_role("landlord") or current_user.has_role("agent")) and lease.landlord_id == current_user.id
    
    if not (is_tenant or is_landlord):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to subscribe to this lease's events"
        )
    
    # Subscribe to events
    queue = event_bus.subscribe(lease_id)
    
    async def event_stream():
        """Stream events as Server-Sent Events."""
        try:
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'CONNECTED', 'lease_id': lease_id})}\n\n"
            
            # Keep connection alive with periodic heartbeat
            last_heartbeat = asyncio.get_event_loop().time()
            heartbeat_interval = 30  # seconds
            
            while True:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    
                    # Send event as SSE
                    yield f"data: {json.dumps(event)}\n\n"
                    last_heartbeat = asyncio.get_event_loop().time()
                    
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield f"data: {json.dumps({'type': 'HEARTBEAT'})}\n\n"
                        last_heartbeat = current_time
                        
        except asyncio.CancelledError:
            # Client disconnected
            logger.info(
                "lease_sse_disconnected",
                lease_id=lease_id,
                user_id=current_user.id
            )
            event_bus.unsubscribe(lease_id, queue)
        except Exception as e:
            logger.error(
                "lease_sse_error",
                lease_id=lease_id,
                user_id=current_user.id,
                error=str(e),
                exc_info=True
            )
            event_bus.unsubscribe(lease_id, queue)
            raise
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

