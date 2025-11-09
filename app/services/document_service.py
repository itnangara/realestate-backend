"""
Document Service for managing document uploads and downloads

Handles:
- Document metadata storage
- S3 presigned URL generation
- File validation
- Integration with audit service
"""

from sqlalchemy.orm import Session
from typing import Optional, List
from fastapi import HTTPException, status

from app.models.document import Document, DocumentType, DocumentStatus
from app.services.s3_service import s3_service
from app.services.audit_service import audit_service
from app.core.feature_flags import feature_flags
from app.core.logger import get_logger

logger = get_logger(__name__)


class DocumentService:
    """Service for document management operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def initiate_upload(
        self,
        user_id: int,
        document_type: DocumentType,
        file_name: str,
        content_type: str,
        file_size: int,
        request_id: Optional[str] = None
    ) -> dict:
        """
        Initiate document upload by generating presigned PUT URL
        
        Args:
            user_id: ID of the user uploading the document
            document_type: Type of document
            file_name: Original file name
            content_type: MIME type of the file
            file_size: File size in bytes
            request_id: Optional request ID for correlation
            
        Returns:
            Dictionary with document_id, upload_url, s3_key, expires_in
            
        Raises:
            HTTPException: If feature flag is disabled or validation fails
        """
        # Check feature flag
        is_enabled = await feature_flags.is_enabled("document_upload_enabled")
        if not is_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Document upload is currently disabled"
            )
        
        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {max_size} bytes"
            )
        
        # Generate S3 key
        file_extension = file_name.split('.')[-1] if '.' in file_name else ''
        s3_key = s3_service.generate_s3_key(
            user_id=user_id,
            document_type=document_type.value,
            file_extension=f".{file_extension}" if file_extension else ""
        )
        
        # Create document record
        document = Document(
            user_id=user_id,
            type=document_type,
            s3_key=s3_key,
            status=DocumentStatus.PENDING
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        
        # Generate presigned PUT URL (PII documents go to separate bucket)
        is_pii = document_type in [DocumentType.ID_FRONT, DocumentType.ID_BACK, DocumentType.PROOF_OF_ADDRESS]
        upload_url = s3_service.generate_presigned_put_url(
            s3_key=s3_key,
            content_type=content_type,
            expires_in=900,  # 15 minutes
            is_pii=is_pii
        )
        
        if not upload_url:
            # Rollback document creation if S3 URL generation fails
            self.db.delete(document)
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to generate upload URL. S3 service may be unavailable."
            )
        
        # Audit log
        audit_service.log_user_action(
            db=self.db,
            action="document_upload_initiated",
            user_id=user_id,
            target_type="document",
            target_id=document.id,
            meta={
                "document_type": document_type.value,
                "file_name": file_name,
                "file_size": file_size,
                "content_type": content_type,
                "s3_key": s3_key
            },
            request_id=request_id
        )
        
        logger.info(
            "document_upload_initiated",
            document_id=document.id,
            user_id=user_id,
            document_type=document_type.value,
            s3_key=s3_key
        )
        
        return {
            "document_id": document.id,
            "upload_url": upload_url,
            "s3_key": s3_key,
            "expires_in": 900
        }
    
    async def confirm_upload(
        self,
        document_id: int,
        user_id: int,
        request_id: Optional[str] = None
    ) -> Document:
        """
        Confirm document upload completion and update status
        
        Args:
            document_id: ID of the document
            user_id: ID of the user (for authorization)
            request_id: Optional request ID for correlation
            
        Returns:
            Updated Document object
            
        Raises:
            HTTPException: If document not found or unauthorized
        """
        document = self.db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Update status to uploaded
        document.status = DocumentStatus.UPLOADED
        self.db.commit()
        self.db.refresh(document)
        
        # Audit log
        audit_service.log_user_action(
            db=self.db,
            action="document_upload_completed",
            user_id=user_id,
            target_type="document",
            target_id=document.id,
            meta={
                "document_type": document.type.value,
                "s3_key": document.s3_key,
                "status": document.status.value
            },
            request_id=request_id
        )
        
        logger.info(
            "document_upload_completed",
            document_id=document.id,
            user_id=user_id
        )
        
        return document
    
    async def get_download_url(
        self,
        document_id: int,
        user_id: int,
        request_id: Optional[str] = None
    ) -> dict:
        """
        Generate presigned GET URL for document download
        
        Args:
            document_id: ID of the document
            user_id: ID of the user (for authorization)
            request_id: Optional request ID for correlation
            
        Returns:
            Dictionary with document_id, download_url, expires_in
            
        Raises:
            HTTPException: If document not found or unauthorized
        """
        document = self.db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Determine if PII document
        is_pii = document.type in [DocumentType.ID_FRONT, DocumentType.ID_BACK, DocumentType.PROOF_OF_ADDRESS]
        
        # Generate presigned GET URL
        download_url = s3_service.generate_presigned_get_url(
            s3_key=document.s3_key,
            expires_in=3600,  # 1 hour
            is_pii=is_pii
        )
        
        if not download_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to generate download URL. S3 service may be unavailable."
            )
        
        # Audit log
        audit_service.log_user_action(
            db=self.db,
            action="document_download_requested",
            user_id=user_id,
            target_type="document",
            target_id=document.id,
            meta={
                "document_type": document.type.value,
                "s3_key": document.s3_key
            },
            request_id=request_id
        )
        
        logger.info(
            "document_download_url_generated",
            document_id=document.id,
            user_id=user_id
        )
        
        return {
            "document_id": document_id,
            "download_url": download_url,
            "expires_in": 3600
        }
    
    def get_document(
        self,
        document_id: int,
        user_id: int
    ) -> Optional[Document]:
        """
        Get document by ID (with authorization check)
        
        Args:
            document_id: ID of the document
            user_id: ID of the user (for authorization)
            
        Returns:
            Document object or None if not found/unauthorized
        """
        return self.db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
    
    def list_user_documents(
        self,
        user_id: int,
        document_type: Optional[DocumentType] = None,
        status: Optional[DocumentStatus] = None
    ) -> List[Document]:
        """
        List all documents for a user with optional filters
        
        Args:
            user_id: ID of the user
            document_type: Optional filter by document type
            status: Optional filter by status
            
        Returns:
            List of Document objects
        """
        query = self.db.query(Document).filter(Document.user_id == user_id)
        
        if document_type:
            query = query.filter(Document.type == document_type)
        
        if status:
            query = query.filter(Document.status == status)
        
        return query.order_by(Document.uploaded_at.desc()).all()
    
    def get_documents_by_ids(
        self,
        document_ids: List[int],
        user_id: int
    ) -> List[Document]:
        """
        Get multiple documents by IDs (with authorization check)
        
        Args:
            document_ids: List of document IDs
            user_id: ID of the user (for authorization)
            
        Returns:
            List of Document objects that belong to the user
        """
        return self.db.query(Document).filter(
            Document.id.in_(document_ids),
            Document.user_id == user_id
        ).all()

