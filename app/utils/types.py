"""
Enterprise-Grade Custom SQLAlchemy Types

Provides database-agnostic type adapters for PostgreSQL-specific types
that need to work with SQLite for testing.

Types:
- ArrayType: PostgreSQL ARRAY that works as JSON in SQLite
- JSONBType: PostgreSQL JSONB that works as JSON in SQLite
- UUIDType: PostgreSQL UUID that works as String in SQLite
"""

import json
from typing import Any, List, Optional, Type
from uuid import UUID as PythonUUID
from sqlalchemy import TypeDecorator, String, Text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.types import TypeEngine


class ArrayType(TypeDecorator):
    """
    Enterprise-grade ARRAY type that works with both PostgreSQL and SQLite.
    
    In PostgreSQL: Uses native ARRAY type for optimal performance
    In SQLite: Uses JSON text storage with automatic serialization/deserialization
    
    Usage:
        requested_roles = Column(ArrayType(String), nullable=False)
    """
    
    impl = String
    cache_ok = True
    
    def __init__(self, item_type: Type[TypeEngine], **kwargs):
        """
        Initialize ArrayType
        
        Args:
            item_type: The SQLAlchemy type for array items (e.g., String, Integer)
            **kwargs: Additional arguments passed to TypeDecorator
        """
        super().__init__(**kwargs)
        self.item_type = item_type
        # Store PostgreSQL ARRAY type for dialect-specific behavior
        self._postgresql_array = postgresql.ARRAY(item_type)
    
    def load_dialect_impl(self, dialect):
        """
        Return the appropriate type implementation based on database dialect.
        
        Args:
            dialect: SQLAlchemy dialect object
            
        Returns:
            TypeEngine appropriate for the dialect
        """
        if dialect.name == 'postgresql':
            # Use native PostgreSQL ARRAY for production
            return self._postgresql_array
        else:
            # Use JSON text storage for SQLite and other databases
            return dialect.type_descriptor(Text())
    
    def process_bind_param(self, value: Optional[List[Any]], dialect) -> Optional[str]:
        """
        Convert Python list to database value.
        
        Args:
            value: Python list or None
            dialect: SQLAlchemy dialect object
            
        Returns:
            String (JSON) for SQLite, list for PostgreSQL, None if value is None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL handles arrays natively
            return value
        else:
            # SQLite: serialize list to JSON string
            if not isinstance(value, list):
                raise ValueError(f"ArrayType expects a list, got {type(value)}")
            return json.dumps(value)
    
    def process_result_value(self, value: Optional[Any], dialect) -> Optional[List[Any]]:
        """
        Convert database value to Python list.
        
        Args:
            value: Database value (list for PostgreSQL, JSON string for SQLite)
            dialect: SQLAlchemy dialect object
            
        Returns:
            Python list or None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL returns native list
            return value if isinstance(value, list) else list(value) if value else None
        else:
            # SQLite: deserialize JSON string to list
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValueError(f"Failed to deserialize ArrayType value: {value}") from e
            elif isinstance(value, list):
                # Already a list (shouldn't happen, but handle gracefully)
                return value
            else:
                raise ValueError(f"Unexpected ArrayType value type: {type(value)}")
    
    def compare_values(self, x: Optional[List[Any]], y: Optional[List[Any]]) -> bool:
        """
        Compare two array values for equality.
        
        Args:
            x: First array value
            y: Second array value
            
        Returns:
            True if arrays are equal, False otherwise
        """
        if x is None and y is None:
            return True
        if x is None or y is None:
            return False
        return x == y


class JSONBType(TypeDecorator):
    """
    Enterprise-grade JSONB type that works with both PostgreSQL and SQLite.
    
    In PostgreSQL: Uses native JSONB type for optimal performance and indexing
    In SQLite: Uses JSON text storage with automatic serialization/deserialization
    
    Usage:
        meta = Column(JSONBType, nullable=True)
    """
    
    impl = Text
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        """
        Return the appropriate type implementation based on database dialect.
        
        Args:
            dialect: SQLAlchemy dialect object
            
        Returns:
            TypeEngine appropriate for the dialect
        """
        if dialect.name == 'postgresql':
            # Use native PostgreSQL JSONB for production
            return dialect.type_descriptor(postgresql.JSONB())
        else:
            # Use JSON text storage for SQLite and other databases
            return dialect.type_descriptor(Text())
    
    def process_bind_param(self, value: Optional[dict], dialect) -> Optional[str]:
        """
        Convert Python dict to database value.
        
        Args:
            value: Python dict or None
            dialect: SQLAlchemy dialect object
            
        Returns:
            String (JSON) for SQLite, dict for PostgreSQL, None if value is None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL handles JSONB natively
            return value
        else:
            # SQLite: serialize dict to JSON string
            if not isinstance(value, (dict, list)):
                raise ValueError(f"JSONBType expects a dict or list, got {type(value)}")
            return json.dumps(value)
    
    def process_result_value(self, value: Optional[Any], dialect) -> Optional[dict]:
        """
        Convert database value to Python dict.
        
        Args:
            value: Database value (dict for PostgreSQL, JSON string for SQLite)
            dialect: SQLAlchemy dialect object
            
        Returns:
            Python dict/list or None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL returns native dict/list
            return value
        else:
            # SQLite: deserialize JSON string to dict/list
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError) as e:
                    raise ValueError(f"Failed to deserialize JSONBType value: {value}") from e
            elif isinstance(value, (dict, list)):
                # Already a dict/list (shouldn't happen, but handle gracefully)
                return value
            else:
                raise ValueError(f"Unexpected JSONBType value type: {type(value)}")
    
    def compare_values(self, x: Optional[dict], y: Optional[dict]) -> bool:
        """
        Compare two JSON values for equality.
        
        Args:
            x: First JSON value
            y: Second JSON value
            
        Returns:
            True if values are equal, False otherwise
        """
        if x is None and y is None:
            return True
        if x is None or y is None:
            return False
        return x == y


class UUIDType(TypeDecorator):
    """
    Enterprise-grade UUID type that works with both PostgreSQL and SQLite.
    
    In PostgreSQL: Uses native UUID type for optimal performance
    In SQLite: Uses String(36) storage with automatic serialization/deserialization
    
    Usage:
        file_id = Column(UUIDType(as_uuid=True), nullable=False)
    """
    
    impl = String
    cache_ok = True
    
    def __init__(self, as_uuid: bool = True, **kwargs):
        """
        Initialize UUIDType
        
        Args:
            as_uuid: If True, work with Python UUID objects. If False, work with strings.
            **kwargs: Additional arguments passed to TypeDecorator
        """
        super().__init__(**kwargs)
        self.as_uuid = as_uuid
        # Store PostgreSQL UUID type for dialect-specific behavior
        self._postgresql_uuid = postgresql.UUID(as_uuid=as_uuid)
    
    def load_dialect_impl(self, dialect):
        """
        Return the appropriate type implementation based on database dialect.
        
        Args:
            dialect: SQLAlchemy dialect object
            
        Returns:
            TypeEngine appropriate for the dialect
        """
        if dialect.name == 'postgresql':
            # Use native PostgreSQL UUID for production
            return self._postgresql_uuid
        else:
            # Use String(36) for SQLite and other databases (UUID string format)
            return dialect.type_descriptor(String(36))
    
    def process_bind_param(self, value: Optional[Any], dialect) -> Optional[str]:
        """
        Convert Python UUID to database value.
        
        Args:
            value: Python UUID object or UUID string or None
            dialect: SQLAlchemy dialect object
            
        Returns:
            UUID for PostgreSQL, string for SQLite, None if value is None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL handles UUID natively
            return value
        else:
            # SQLite: convert UUID to string
            if isinstance(value, PythonUUID):
                return str(value)
            elif isinstance(value, str):
                # Validate it's a valid UUID string
                try:
                    PythonUUID(value)
                    return value
                except ValueError:
                    raise ValueError(f"Invalid UUID string: {value}")
            else:
                raise ValueError(f"UUIDType expects UUID or string, got {type(value)}")
    
    def process_result_value(self, value: Optional[Any], dialect) -> Optional[Any]:
        """
        Convert database value to Python UUID.
        
        Args:
            value: Database value (UUID for PostgreSQL, string for SQLite)
            dialect: SQLAlchemy dialect object
            
        Returns:
            Python UUID object if as_uuid=True, string if as_uuid=False, None if value is None
        """
        if value is None:
            return None
        
        if dialect.name == 'postgresql':
            # PostgreSQL returns native UUID
            return value
        else:
            # SQLite: convert string to UUID
            if isinstance(value, str):
                if self.as_uuid:
                    try:
                        return PythonUUID(value)
                    except ValueError:
                        raise ValueError(f"Invalid UUID string from database: {value}")
                else:
                    return value
            elif isinstance(value, PythonUUID):
                # Already a UUID (shouldn't happen in SQLite, but handle gracefully)
                return value if self.as_uuid else str(value)
            else:
                raise ValueError(f"Unexpected UUIDType value type: {type(value)}")
    
    def compare_values(self, x: Optional[Any], y: Optional[Any]) -> bool:
        """
        Compare two UUID values for equality.
        
        Args:
            x: First UUID value
            y: Second UUID value
            
        Returns:
            True if UUIDs are equal, False otherwise
        """
        if x is None and y is None:
            return True
        if x is None or y is None:
            return False
        
        # Normalize to strings for comparison
        x_str = str(x) if isinstance(x, PythonUUID) else x
        y_str = str(y) if isinstance(y, PythonUUID) else y
        return x_str == y_str

