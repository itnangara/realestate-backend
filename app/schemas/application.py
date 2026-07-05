"""
Application Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field, computed_field, model_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from app.models.application import ApplicationStatus
from app.schemas.property import PropertyBriefSchema
#from app.schemas.application import UserBriefSchema

class ApplicationBase(BaseModel):
    """Base application schema"""
    message: Optional[str] = Field(None, description="Optional message to the property owner")
    move_in_date: Optional[datetime] = Field(None, description="Preferred move-in date")
    lease_duration: Optional[int] = Field(None, description="Lease duration in months")
    annual_income: Optional[int] = Field(None, description="Annual income in dollars", ge=0)
    credit_score: Optional[int] = Field(None, description="Credit score (300-850)", ge=300, le=850)
    employment_status: Optional[str] = Field(None, description="Current employment status")
    employer_name: Optional[str] = Field(None, description="Name of current employer")
    phone: Optional[str] = Field(None, description="Contact phone number")
    alternate_email: Optional[str] = Field(None, description="Alternate email address")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="List of references (name, phone, email, relationship)")
    background_check_consent: Optional[bool] = Field(False, description="Consent for background checks")

class ApplicationCreate(ApplicationBase):
    """Schema for creating an application"""
    property_id: int = Field(..., description="ID of the property to apply for")
    documents_urls: Optional[List[str]] = Field(default_factory=list, description="List of document URLs")
    references: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="List of references")
    background_check_consent: bool = Field(False, description="Consent for background checks")

    @model_validator(mode='after')
    def validate_application_data(self):
        if self.move_in_date and self.move_in_date < datetime.now(timezone.utc):
            raise ValueError('Move-in date cannot be in the past')
        return self

class ApplicationUpdate(BaseModel):
    """Schema for updating an application"""
    status: Optional[ApplicationStatus] = Field(None, description="Application status")
    message: Optional[str] = Field(None, description="Optional message to the property owner")
    move_in_date: Optional[datetime] = Field(None, description="Preferred move-in date")
    lease_duration: Optional[int] = Field(None, description="Lease duration in months", ge=1)
    annual_income: Optional[int] = Field(None, description="Annual income in dollars", ge=0)
    credit_score: Optional[int] = Field(None, description="Credit score (300-850)", ge=300, le=850)
    employment_status: Optional[str] = Field(None, description="Current employment status")
    employer_name: Optional[str] = Field(None, description="Name of current employer")
    phone: Optional[str] = Field(None, description="Contact phone number")
    alternate_email: Optional[str] = Field(None, description="Alternate email address")
    documents_urls: Optional[List[str]] = Field(default_factory=list, description="List of document URLs")
    references: Optional[List[Dict[str, Any]]] = Field(None, description="List of references")
    background_check_consent: Optional[bool] = Field(None, description="Consent for background checks")

class ApplicationResponse(ApplicationBase):
    """Schema for application response"""
    id: int
    status: ApplicationStatus
    documents_urls: List[str] = Field(default_factory=list)
    references: Optional[List[Dict[str, Any]]] = None
    background_check_consent: bool = False
    is_active: bool = True
    applicant_id: int
    property_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    lease_signed_at: Optional[datetime] = Field(None, description="Timestamp when lease was signed")

    @computed_field
    @property
    def is_long_term(self) -> bool:
        """Whether lease is long-term (>12 months)"""
        return self.lease_duration is not None and self.lease_duration > 12

    model_config = ConfigDict(from_attributes=True)

class UserBriefSchema(BaseModel):
    """Safe user data for application details"""
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None # Added for contact parity
    avatar_url: Optional[str] = None   # Added for UI polish
    roles: List[str] = []

    # Handle null checks and string concatenation for the name (for frontend display).
    @computed_field
    @property
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.email

    model_config = ConfigDict(from_attributes=True)

class ApplicationDetailResponse(ApplicationResponse):
    """Schema for application with related data"""
    applicant: Optional[UserBriefSchema] = Field(None, description="Applicant user information")
    property: Optional[PropertyBriefSchema] = Field(None, description="Property information with owner context")

class ApplicationListResponse(BaseModel):
    """
    Enterprise-grade paginated response for application lists.
    
    Standardized format matching industry best practices:
    - items: List of applications (always an array, never null)
    - total: Total count matching filters (not total DB rows)
    - page: Current page number (1-indexed)
    - limit: Items per page
    - pages: Total number of pages
    """
    items: List[ApplicationResponse] = Field(default_factory=list, description="List of applications")
    total: int = Field(ge=0, description="Total count matching filters")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    limit: int = Field(ge=1, description="Items per page")
    pages: int = Field(ge=0, description="Total number of pages")
    
    status_counts: Optional[Dict[str, int]] = Field(default=None, description="Aggregated status counts for current filter (ignore pagination)")
    
    model_config = ConfigDict(from_attributes=True)
