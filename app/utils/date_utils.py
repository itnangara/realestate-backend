"""
Date utility functions for consistent date handling across the application.

Enterprise-grade date parsing and validation utilities that ensure:
- Consistent date format handling (ISO 8601)
- Proper timezone management (UTC)
- Type safety and error handling
- Reusability across all routes and services
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status


def parse_date_query_param(
    date_str: Optional[str],
    param_name: str = "date",
    allow_time: bool = True
) -> Optional[datetime]:
    """
    Parse a date string from a query parameter into a datetime object.
    
    **Enterprise-grade date parsing:**
    - Supports ISO 8601 formats: YYYY-MM-DD and YYYY-MM-DDTHH:MM:SS
    - Always returns UTC timezone-aware datetime
    - Provides clear error messages for invalid formats
    - Handles None values gracefully
    
    **Args:**
        date_str: Date string from query parameter (can be None)
        param_name: Name of the parameter for error messages (default: "date")
        allow_time: Whether to allow time component (default: True)
    
    **Returns:**
        datetime object with UTC timezone, or None if date_str is None
    
    **Raises:**
        HTTPException: If date format is invalid
    
    **Examples:**
        >>> parse_date_query_param("2024-01-15")
        datetime.datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)
        
        >>> parse_date_query_param("2024-01-15T10:30:00")
        datetime.datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        
        >>> parse_date_query_param(None)
        None
    """
    if date_str is None:
        return None
    
    # Try ISO 8601 format with time (YYYY-MM-DDTHH:MM:SS)
    if allow_time:
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Ensure timezone-aware (default to UTC if not specified)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            pass
    
    # Try date-only format (YYYY-MM-DD)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    
    # If all parsing attempts fail, raise error
    format_hint = "YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS" if allow_time else "YYYY-MM-DD"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid {param_name} format. Use {format_hint} (ISO 8601)"
    )


def normalize_date_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize a datetime to UTC timezone.
    
    **Args:**
        dt: Datetime object (can be None or timezone-aware/naive)
    
    **Returns:**
        UTC timezone-aware datetime, or None if dt is None
    
    **Examples:**
        >>> normalize_date_to_utc(datetime(2024, 1, 15))
        datetime.datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Assume UTC if timezone-naive
        return dt.replace(tzinfo=timezone.utc)
    
    # Convert to UTC if timezone-aware
    return dt.astimezone(timezone.utc)


def validate_date_range(
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    param_name_from: str = "date_from",
    param_name_to: str = "date_to"
) -> None:
    """
    Validate that date_from <= date_to.
    
    **Args:**
        date_from: Start date (can be None)
        date_to: End date (can be None)
        param_name_from: Name of from parameter for error messages
        param_name_to: Name of to parameter for error messages
    
    **Raises:**
        HTTPException: If date_from > date_to
    """
    if date_from is not None and date_to is not None:
        if date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{param_name_from} must be less than or equal to {param_name_to}"
            )
