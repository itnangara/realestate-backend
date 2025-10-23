"""
Application Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime
from app.models.application import ApplicationStatus

class ApplicationBase(BaseModel):
    """Base application schema"""
    message: Optional[str] = None
    move_in_date: Optional[datetime] = None
    lease_duration: Optional[int] = None  # in months
    annual_income: Optional[int] = None
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    phone: Optional[str] = None
    alternate_email: Optional[str] = None

class ApplicationCreate(ApplicationBase):
    """Schema for creating an application"""
    property_id: int
    
    @validator('lease_duration')
    def validate_lease_duration(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Lease duration must be positive')
        return v
    
    @validator('annual_income')
    def validate_annual_income(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Annual income must be positive')
        return v
    
    @validator('credit_score')
    def validate_credit_score(cls, v):
        if v is not None and (v < 300 or v > 850):
            raise ValueError('Credit score must be between 300 and 850')
        return v

class ApplicationUpdate(BaseModel):
    """Schema for updating an application"""
    status: Optional[ApplicationStatus] = None
    message: Optional[str] = None
    move_in_date: Optional[datetime] = None
    lease_duration: Optional[int] = None
    annual_income: Optional[int] = None
    credit_score: Optional[int] = None
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    phone: Optional[str] = None
    alternate_email: Optional[str] = None
    documents_urls: Optional[List[str]] = None

class ApplicationResponse(ApplicationBase):
    """Schema for application response"""
    id: int
    status: ApplicationStatus
    documents_urls: Optional[List[str]] = None
    is_active: bool = True
    applicant_id: int
    property_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ApplicationWithDetails(ApplicationResponse):
    """Schema for application with related data"""
    applicant: Optional[dict] = None  # User data
    property: Optional[dict] = None   # Property data


