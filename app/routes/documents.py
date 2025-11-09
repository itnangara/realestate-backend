"""
Document routes for upload and download operations

Endpoints:
- POST /api/documents/upload - Generate presigned PUT URL
- POST /api/documents/{id}/confirm - Confirm upload completion
- GET /api/documents/{id} - Generate presigned GET URL
- GET /api/documents - List user documents
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.document import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentDownloadResponse,
    DocumentResponse,
    DocumentListResponse
)
from app.services.document_service import DocumentService
from app.dependencies.user_dependencies import get_current_user
from app.models.user import User
from app.models.document import DocumentType, DocumentStatus
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


def get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    """Dependency to get document service instance"""
    return DocumentService(db)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate document upload",
    response_description="Presigned PUT URL for uploading the document to S3"
)
async def initiate_document_upload(
    request_data: DocumentUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Initiate document upload by generating a presigned PUT URL.
    
    This endpoint:
    - Validates file type and size
    - Creates a document record in the database
    - Generates a presigned S3 PUT URL for direct upload
    - Logs the action in audit trail
    
    After receiving the upload URL, the client should:
    1. Upload the file directly to S3 using the presigned URL
    2. Call POST /api/documents/{id}/confirm to mark upload as complete
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = DocumentService(db)
    result = await service.initiate_upload(
        user_id=current_user.id,
        document_type=request_data.document_type,
        file_name=request_data.file_name,
        content_type=request_data.content_type,
        file_size=request_data.file_size,
        request_id=request_id
    )
    
    return DocumentUploadResponse(**result)


@router.post(
    "/{document_id}/confirm",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm document upload",
    response_description="Updated document record with uploaded status"
)
async def confirm_document_upload(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Confirm that document upload to S3 has been completed.
    
    This endpoint updates the document status from PENDING to UPLOADED
    and logs the completion in the audit trail.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = DocumentService(db)
    document = await service.confirm_upload(
        document_id=document_id,
        user_id=current_user.id,
        request_id=request_id
    )
    
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}",
    response_model=DocumentDownloadResponse,
    summary="Get document download URL",
    response_description="Presigned GET URL for downloading the document from S3"
)
async def get_document_download_url(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Generate a presigned GET URL for downloading a document.
    
    The URL is valid for 1 hour and provides direct access to the document
    stored in S3. All download requests are logged in the audit trail.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = DocumentService(db)
    result = await service.get_download_url(
        document_id=document_id,
        user_id=current_user.id,
        request_id=request_id
    )
    
    return DocumentDownloadResponse(**result)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List user documents",
    response_description="List of all documents belonging to the authenticated user"
)
async def list_user_documents(
    document_type: Optional[DocumentType] = None,
    status: Optional[DocumentStatus] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all documents for the authenticated user.
    
    Optional query parameters:
    - document_type: Filter by document type (id_front, id_back, proof_of_address, company_doc)
    - status: Filter by status (pending, uploaded, verified, rejected)
    """
    service = DocumentService(db)
    documents = service.list_user_documents(
        user_id=current_user.id,
        document_type=document_type,
        status=status
    )
    
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(doc) for doc in documents],
        total=len(documents)
    )

