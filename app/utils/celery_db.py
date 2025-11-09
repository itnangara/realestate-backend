"""
Database session management for Celery tasks

Provides context manager for database sessions in async Celery workers.
"""

from contextlib import contextmanager
from sqlalchemy.orm import Session
from app.utils.database import SessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


@contextmanager
def get_db_session() -> Session:
    """
    Context manager for database sessions in Celery tasks.
    
    Usage:
        with get_db_session() as db:
            # Use db session
            user = db.query(User).first()
            db.commit()
    
    Automatically handles:
    - Session creation
    - Commit on success
    - Rollback on exception
    - Session cleanup
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(
            "celery_db_session_error",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise
    finally:
        db.close()

