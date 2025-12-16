"""
Staff User Schemas for controlled exposure of user details.
Adheres to Least Privilege Principle.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class StaffUserSchema(BaseModel):
    """
    Schema representing a maintenance staff member's public details.
    Used for exposing staff information to non-admin roles (e.g., Landlord).
    """
    id: int = Field(..., description="The user ID of the staff member.")
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None # Optional contact field

    class Config:
        from_attributes = True