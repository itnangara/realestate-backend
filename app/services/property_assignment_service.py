"""
Property Assignment Service

Enterprise-grade service for idempotent property linking to users.
Unified helper for all user-property relationship types.
"""

from typing import List, Iterable
from sqlalchemy.orm import Session
from app.models.user_property import UserProperty, RelationshipType
from app.core.logger import get_logger

logger = get_logger(__name__)


class PropertyAssignmentService:
    """
    Helper service to attach property links to users idempotently.
    
    Enterprise-grade: Prevents duplicates, supports all relationship types,
    and is safe to call multiple times.
    """

    def __init__(self, db: Session):
        self.db = db

    def attach_properties(
        self,
        user_id: int,
        property_ids: Iterable[int],
        relationship_type: RelationshipType
    ) -> List[UserProperty]:
        """
        Attach properties to a user with specified relationship type.
        
        Args:
            user_id: User ID to attach properties to
            property_ids: Iterable of property IDs to attach
            relationship_type: Type of relationship (OWNER, MAINTENANCE, etc.)
            
        Returns:
            List of created UserProperty objects
            
        Note:
            Idempotent - will skip properties that already have this relationship
        """
        created = []
        if not property_ids:
            return created

        property_ids_list = list(property_ids)
        
        # Fetch existing to avoid duplicates
        existing_rows = (
            self.db.query(UserProperty.property_id)
            .filter(
                UserProperty.user_id == user_id,
                UserProperty.relationship_type == relationship_type,
                UserProperty.property_id.in_(property_ids_list)
            )
            .all()
        )
        existing_pids = {r[0] for r in existing_rows}

        for pid in property_ids_list:
            if pid in existing_pids:
                logger.debug(
                    "property_link_already_exists",
                    user_id=user_id,
                    property_id=pid,
                    relationship_type=relationship_type.value
                )
                continue
                
            up = UserProperty(
                user_id=user_id,
                property_id=pid,
                relationship_type=relationship_type
            )
            self.db.add(up)
            created.append(up)
            
            logger.info(
                "property_link_created",
                user_id=user_id,
                property_id=pid,
                relationship_type=relationship_type.value
            )

        # Note: commit should be handled by the caller transactionally
        return created
    
    def detach_properties(
        self,
        user_id: int,
        property_ids: Iterable[int],
        relationship_type: RelationshipType
    ) -> int:
        """
        Detach properties from a user for specified relationship type.
        
        Args:
            user_id: User ID
            property_ids: Iterable of property IDs to detach
            relationship_type: Type of relationship to remove
            
        Returns:
            Number of links removed
        """
        property_ids_list = list(property_ids)
        if not property_ids_list:
            return 0
        
        deleted_count = (
            self.db.query(UserProperty)
            .filter(
                UserProperty.user_id == user_id,
                UserProperty.property_id.in_(property_ids_list),
                UserProperty.relationship_type == relationship_type
            )
            .delete(synchronize_session=False)
        )
        
        logger.info(
            "property_links_removed",
            user_id=user_id,
            count=deleted_count,
            relationship_type=relationship_type.value
        )
        
        return deleted_count
    
    def get_user_properties(
        self,
        user_id: int,
        relationship_type: RelationshipType = None
    ) -> List[UserProperty]:
        """
        Get all property links for a user, optionally filtered by relationship type.
        
        Args:
            user_id: User ID
            relationship_type: Optional filter by relationship type
            
        Returns:
            List of UserProperty objects
        """
        query = self.db.query(UserProperty).filter(UserProperty.user_id == user_id)
        
        if relationship_type:
            query = query.filter(UserProperty.relationship_type == relationship_type)
        
        return query.all()

