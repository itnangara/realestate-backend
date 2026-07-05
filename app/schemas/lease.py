"""
Lease schemas for API request/response validation
"""

from pydantic import BaseModel, Field, field_validator, field_serializer, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from decimal import Decimal
from app.models.lease import LeaseStatus


class LeaseCreate(BaseModel):
    """Schema for creating a lease draft - supports both application-driven and manual creation"""
    # Application-driven lease (one of these must be provided)
    application_id: Optional[int] = Field(None, description="ID of the approved application (for application-driven leases)")
    
    # Manual lease creation (required if application_id is None)
    property_id: Optional[int] = Field(None, description="Property ID (required for manual leases)")
    tenant_id: Optional[int] = Field(None, description="Tenant ID (required for manual leases)")
    
    # Lease terms (required for all leases)
    rent: Decimal = Field(..., gt=0, description="Monthly rent amount")
    deposit: Optional[Decimal] = Field(None, ge=0, description="Security deposit")
    start_date: datetime = Field(..., description="Lease start date (ISO 8601 date or datetime)")
    end_date: datetime = Field(..., description="Lease end date (ISO 8601 date or datetime)")
    terms: Optional[str] = Field(None, description="Lease terms (markdown or plain text)")
    clauses: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Array of lease clauses")
    
    @model_validator(mode='after')
    def validate_lease_creation_mode(self):
        """
        Enterprise-grade validation: Ensure proper lease creation mode.
        
        Rules:
        - If application_id is None → both property_id AND tenant_id must be provided (manual lease)
        - If application_id is provided → property_id and tenant_id must be None (application-driven lease)
        """
        application_id = self.application_id
        property_id = self.property_id
        tenant_id = self.tenant_id
        
        if application_id is None:
            # Manual lease creation: both property_id and tenant_id are required
            if property_id is None or tenant_id is None:
                raise ValueError(
                    'For manual lease creation, both property_id and tenant_id are required when application_id is not provided'
                )
        else:
            # Application-driven lease: property_id and tenant_id should not be provided
            if property_id is not None or tenant_id is not None:
                raise ValueError(
                    'Cannot provide property_id or tenant_id when application_id is set. '
                    'These fields will be automatically derived from the application.'
                )
        
        return self
    
    @field_validator('start_date', mode='before')
    @classmethod
    def parse_start_date(cls, v: Union[str, date, datetime]) -> datetime:
        """Accept date strings (YYYY-MM-DD) or datetime, convert to datetime"""
        if isinstance(v, str):
            # Try parsing as date first (YYYY-MM-DD)
            try:
                parsed_date = datetime.strptime(v, '%Y-%m-%d')
                return parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                # If not a date string, let Pydantic handle it as datetime
                pass
        elif isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, datetime.min.time())
        return v
    
    @field_validator('end_date', mode='before')
    @classmethod
    def parse_end_date(cls, v: Union[str, date, datetime]) -> datetime:
        """Accept date strings (YYYY-MM-DD) or datetime, convert to datetime"""
        if isinstance(v, str):
            # Try parsing as date first (YYYY-MM-DD)
            try:
                parsed_date = datetime.strptime(v, '%Y-%m-%d')
                return parsed_date.replace(hour=23, minute=59, second=59, microsecond=0)
            except ValueError:
                # If not a date string, let Pydantic handle it as datetime
                pass
        elif isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, datetime.max.time().replace(microsecond=0))
        return v
    
    @field_validator('end_date')
    @classmethod
    def validate_end_date(cls, v: datetime, info) -> datetime:
        """Ensure end_date is after start_date"""
        if 'start_date' in info.data and v <= info.data['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class LeaseUpdate(BaseModel):
    """Schema for updating a lease draft"""
    rent: Optional[Decimal] = Field(None, gt=0, description="Monthly rent amount")
    deposit: Optional[Decimal] = Field(None, ge=0, description="Security deposit")
    start_date: Optional[datetime] = Field(None, description="Lease start date (ISO 8601 date or datetime)")
    end_date: Optional[datetime] = Field(None, description="Lease end date (ISO 8601 date or datetime)")
    terms: Optional[str] = Field(None, description="Lease terms")
    clauses: Optional[List[Dict[str, Any]]] = Field(None, description="Array of lease clauses")
    
    @field_validator('start_date', mode='before')
    @classmethod
    def parse_start_date(cls, v: Union[str, date, datetime, None]) -> Optional[datetime]:
        """Accept date strings (YYYY-MM-DD) or datetime, convert to datetime"""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                parsed_date = datetime.strptime(v, '%Y-%m-%d')
                return parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                pass
        elif isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, datetime.min.time())
        return v
    
    @field_validator('end_date', mode='before')
    @classmethod
    def parse_end_date(cls, v: Union[str, date, datetime, None]) -> Optional[datetime]:
        """Accept date strings (YYYY-MM-DD) or datetime, convert to datetime"""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                parsed_date = datetime.strptime(v, '%Y-%m-%d')
                return parsed_date.replace(hour=23, minute=59, second=59, microsecond=0)
            except ValueError:
                pass
        elif isinstance(v, date) and not isinstance(v, datetime):
            return datetime.combine(v, datetime.max.time().replace(microsecond=0))
        return v


class LeaseSendRequest(BaseModel):
    """Schema for sending lease to tenant"""
    message: Optional[str] = Field(None, description="Optional message to tenant")


class LeaseSignRequest(BaseModel):
    """Schema for signing a lease"""
    signature: Optional[str] = Field(None, description="Typed signature or e-signature data")
    signed_at: Optional[datetime] = Field(None, description="Signature timestamp (defaults to now)")


class LeaseSignatureResponse(BaseModel):
    """Schema for lease signature response"""
    id: int
    lease_id: int
    user_id: int
    role: str
    signed_at: datetime
    method: str
    
    class Config:
        from_attributes = True


class LeaseResponse(BaseModel):
    """Schema for lease response"""
    id: int
    application_id: Optional[int] = None  # Nullable for manual leases
    landlord_id: int
    tenant_id: int
    property_id: int
    rent: Decimal
    deposit: Optional[Decimal]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    terms: Optional[str]
    clauses: Optional[List[Dict[str, Any]]]
    status: LeaseStatus
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime]
    signed_at: Optional[datetime]
    activated_at: Optional[datetime]
    signatures: List[LeaseSignatureResponse] = Field(default_factory=list)
    
    @field_serializer('rent', 'deposit', when_used='json')
    def serialize_decimal_to_float(self, value: Optional[Decimal], _info) -> Optional[float]:
        """Convert Decimal to float for JSON serialization (enterprise-grade)"""
        if value is None:
            return None
        return float(value)
    
    class Config:
        from_attributes = True


class LeaseListResponse(BaseModel):
    """Schema for paginated lease list response"""
    items: List[LeaseResponse]
    total: int
    page: int
    limit: int
    pages: int
    status_counts: Dict[str, int]

