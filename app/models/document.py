"""
Document model for secure document storage with S3 integration
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from app.utils.database import Base
import enum


class DocumentType(str, enum.Enum):
    """Document type enum"""
    ID_FRONT = "id_front"
    ID_BACK = "id_back"
    PROOF_OF_ADDRESS = "proof_of_address"
    COMPANY_DOC = "company_doc"


class DocumentStatus(str, enum.Enum):
    """Document status enum"""
    PENDING = "pending"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Document(Base):
    """
    Document model for storing document metadata with S3 keys
    
    Documents are stored in S3; this table stores metadata and S3 keys.
    Access is controlled via presigned URLs.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(UUID(as_uuid=True), server_default=text("gen_random_uuid()"), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Document metadata
    file_name = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    
    # Document type
    type = Column(
        SQLEnum(DocumentType, native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        index=True
    )
    
    # S3 storage
    s3_key = Column(String(255), nullable=False, unique=True)
    
    # Status tracking
    status = Column(
        SQLEnum(DocumentStatus, native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Timestamps
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", backref="documents")
    
    # Indexes for common queries
    # Composite indexes optimize queries filtering by user_id + status/type
    # Single index on file_id for UUID lookups (external API exposure)
    __table_args__ = (
        Index("idx_documents_user_type", "user_id", "type"),
        Index("idx_documents_user_status", "user_id", "status"),
        Index("idx_documents_file_id", "file_id"),
    )

    def __repr__(self):
        return f"<Document(id={self.id}, file_id={self.file_id}, user_id={self.user_id}, type='{self.type.value}')>"

