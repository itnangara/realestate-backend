"""
Enterprise-grade event bus for real-time lease status updates using SSE (Server-Sent Events).

This is an in-memory event bus that allows publishing events to subscribers.
Perfect for workflow applications where state changes need to be pushed to clients instantly.
"""

import asyncio
from typing import Dict, List, Any
from app.core.logger import get_logger

logger = get_logger(__name__)


class EventBus:
    """
    In-memory event bus for publishing events to subscribers.
    
    Enterprise-grade pattern for real-time updates without external dependencies.
    Uses asyncio.Queue for thread-safe event distribution.
    """
    
    def __init__(self):
        """Initialize the event bus with empty subscribers dictionary."""
        self.subscribers: Dict[int, List[asyncio.Queue]] = {}
    
    def subscribe(self, lease_id: int) -> asyncio.Queue:
        """
        Subscribe to events for a specific lease.
        
        Args:
            lease_id: The lease ID to subscribe to
            
        Returns:
            An asyncio.Queue that will receive events for this lease
        """
        q = asyncio.Queue()
        self.subscribers.setdefault(lease_id, []).append(q)
        logger.info(
            "lease_event_subscribed",
            lease_id=lease_id,
            total_subscribers=len(self.subscribers.get(lease_id, []))
        )
        return q
    
    def unsubscribe(self, lease_id: int, queue: asyncio.Queue):
        """
        Unsubscribe a queue from lease events.
        
        Args:
            lease_id: The lease ID to unsubscribe from
            queue: The queue to remove
        """
        if lease_id in self.subscribers:
            try:
                self.subscribers[lease_id].remove(queue)
                if not self.subscribers[lease_id]:
                    del self.subscribers[lease_id]
                logger.info(
                    "lease_event_unsubscribed",
                    lease_id=lease_id,
                    remaining_subscribers=len(self.subscribers.get(lease_id, []))
                )
            except ValueError:
                # Queue not in list, ignore
                pass
    
    async def publish(self, lease_id: int, event: dict):
        """
        Publish an event to all subscribers of a lease.
        
        Args:
            lease_id: The lease ID to publish the event for
            event: The event data dictionary
        """
        if lease_id in self.subscribers:
            subscribers = self.subscribers[lease_id]
            logger.info(
                "lease_event_published",
                lease_id=lease_id,
                event_type=event.get("type"),
                subscriber_count=len(subscribers)
            )
            for q in subscribers:
                try:
                    await q.put(event)
                except Exception as e:
                    logger.error(
                        "lease_event_publish_failed",
                        lease_id=lease_id,
                        error=str(e)
                    )
        else:
            logger.debug(
                "lease_event_no_subscribers",
                lease_id=lease_id,
                event_type=event.get("type")
            )


# Global event bus instance
event_bus = EventBus()

