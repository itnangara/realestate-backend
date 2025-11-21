"""
Tenant Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class TenantProfileBase(BaseModel):
    """Base tenant profile schema"""
    employment_status: Optional[str] = Field(None, description="Employment status (employed, self_employed, student, unemployed)")
    employer_name: Optional[str] = Field(None, max_length=200, description="Name of current employer")
    job_title: Optional[str] = Field(None, max_length=100, description="Job title")
    annual_income: Optional[float] = Field(None, ge=0, description="Annual income")
    monthly_income: Optional[float] = Field(None, ge=0, description="Monthly income")
    credit_score: Optional[int] = Field(None, ge=300, le=850, description="Credit score")
    bank_name: Optional[str] = Field(None, max_length=100, description="Bank name")
    bank_account_type: Optional[str] = Field(None, max_length=50, description="Bank account type")
    previous_landlord_name: Optional[str] = Field(None, max_length=200, description="Previous landlord name")
    previous_landlord_phone: Optional[str] = Field(None, max_length=20, description="Previous landlord phone")
    previous_rent_amount: Optional[float] = Field(None, ge=0, description="Previous rent amount")
    rental_history_years: Optional[float] = Field(None, ge=0, description="Years of rental history")
    eviction_history: Optional[bool] = Field(False, description="Eviction history")
    preferred_lease_duration: Optional[int] = Field(None, ge=1, description="Preferred lease duration in months")
    pet_owner: Optional[bool] = Field(False, description="Pet owner")
    smoking: Optional[bool] = Field(False, description="Smoking preference")
    max_rent_budget: Optional[float] = Field(None, ge=0, description="Maximum rent budget")


class TenantProfileCreate(TenantProfileBase):
    """Schema for creating a tenant profile"""
    pass


class TenantProfileUpdate(TenantProfileBase):
    """Schema for updating a tenant profile"""
    pass


class TenantProfileResponse(TenantProfileBase):
    """Schema for tenant profile response"""
    id: int
    user_id: int
    income_verification_documents: Optional[List[str]] = None
    credit_score_date: Optional[datetime] = None
    references: Optional[List[Dict[str, Any]]] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TenantOnboardingData(BaseModel):
    """Schema for tenant onboarding data collection"""
    # Personal information (from User model - handled separately)
    # Employment & Income
    employment_status: Optional[str] = Field(None, description="Employment status")
    employer_name: Optional[str] = Field(None, max_length=200)
    job_title: Optional[str] = Field(None, max_length=100)
    annual_income: Optional[float] = Field(None, ge=0)
    monthly_income: Optional[float] = Field(None, ge=0)
    
    # Financial Information
    credit_score: Optional[int] = Field(None, ge=300, le=850)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account_type: Optional[str] = Field(None, max_length=50)
    
    # Rental History
    previous_landlord_name: Optional[str] = Field(None, max_length=200)
    previous_landlord_phone: Optional[str] = Field(None, max_length=20)
    previous_rent_amount: Optional[float] = Field(None, ge=0)
    rental_history_years: Optional[float] = Field(None, ge=0)
    eviction_history: Optional[bool] = Field(False)
    
    # Preferences
    preferred_lease_duration: Optional[int] = Field(None, ge=1)
    pet_owner: Optional[bool] = Field(False)
    smoking: Optional[bool] = Field(False)
    max_rent_budget: Optional[float] = Field(None, ge=0)
    
    # Document IDs (already uploaded)
    document_ids: Optional[List[str]] = Field(default_factory=list, description="List of uploaded document file IDs")


class TenantOnboardingStatus(BaseModel):
    """Schema for tenant onboarding status"""
    is_complete: bool = Field(description="Whether onboarding is complete")
    has_tenant_role: bool = Field(description="Whether user has tenant role")
    has_profile: bool = Field(description="Whether tenant profile exists")
    completed_steps: List[str] = Field(default_factory=list, description="List of completed steps")
    pending_steps: List[str] = Field(default_factory=list, description="List of pending steps")
    profile: Optional[TenantProfileResponse] = Field(None, description="Tenant profile if exists")


class TenantDashboardResponse(BaseModel):
    """Schema for tenant dashboard response"""
    profile: Optional[TenantProfileResponse] = None
    active_applications_count: int = 0
    pending_applications_count: int = 0
    approved_applications_count: int = 0
    has_tenant_role: bool = True

    model_config = ConfigDict(from_attributes=True)

