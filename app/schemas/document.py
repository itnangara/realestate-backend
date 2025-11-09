"""
Document schemas for API requests and responses
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from app.models.document import DocumentType, DocumentStatus


class DocumentUploadRequest(BaseModel):
    """Request schema for initiating document upload"""
    document_type: DocumentType = Field(..., description="Type of document to upload")
    file_name: str = Field(..., min_length=1, max_length=255, description="Original file name")
    content_type: str = Field(default="application/octet-stream", description="MIME type of the file")
    file_size: int = Field(..., gt=0, le=10 * 1024 * 1024, description="File size in bytes (max 10MB)")
    
    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        """Validate content type is allowed"""
        allowed_types = [
            "application/pdf",
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp"
        ]
        if v not in allowed_types:
            raise ValueError(f"Content type must be one of: {', '.join(allowed_types)}")
        return v


class DocumentUploadResponse(BaseModel):
    """Response schema for document upload initiation"""
    document_id: int = Field(..., description="ID of the created document record")
    upload_url: str = Field(..., description="Presigned PUT URL for uploading the file")
    s3_key: str = Field(..., description="S3 key where the file will be stored")
    expires_in: int = Field(default=900, description="URL expiration time in seconds (15 minutes)")


class DocumentResponse(BaseModel):
    """Response schema for document retrieval"""
    id: int
    user_id: int
    type: DocumentType
    s3_key: str
    status: DocumentStatus
    uploaded_at: datetime
    
    class Config:
        from_attributes = True


class DocumentDownloadResponse(BaseModel):
    """Response schema for document download URL"""
    document_id: int = Field(..., description="ID of the document")
    download_url: str = Field(..., description="Presigned GET URL for downloading the file")
    expires_in: int = Field(default=3600, description="URL expiration time in seconds (1 hour)")


class DocumentListResponse(BaseModel):
    """Response schema for listing user documents"""
    documents: List[DocumentResponse]
    total: int

