"""
Document routes for upload and download operations

Endpoints:
- POST /api/documents/upload - Generate presigned PUT URL
- POST /api/documents/{id}/confirm - Confirm upload completion
- GET /api/documents/{id} - Generate presigned GET URL
- GET /api/documents - List user documents
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.utils.database import get_db
from app.schemas.document import (
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentUploadRequestMulti,
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
    "/initiate-upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate single document upload (DEPRECATED)",
    response_description="Presigned PUT URL for uploading a single document to S3. Use POST /api/documents/upload instead."
)
async def initiate_document_upload(
    request_data: DocumentUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    ⚠️ DEPRECATED: Use POST /api/documents/upload instead.
    
    This legacy endpoint is maintained for backward compatibility only.
    The new endpoint supports multiple files and returns full metadata including UUIDs.
    
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
    summary="Confirm document upload (DEPRECATED)",
    response_description="Updated document record with uploaded status. Only needed for legacy /initiate-upload flow."
)
async def confirm_document_upload(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    ⚠️ DEPRECATED: Only needed if using legacy /initiate-upload endpoint.
    
    The new POST /api/documents/upload endpoint handles uploads automatically.
    This endpoint is maintained for backward compatibility only.
    
    Confirm that document upload to S3 has been completed.
    
    This endpoint:
    - Validates document ownership (user_id check)
    - Updates the document status from PENDING to UPLOADED
    - Logs the completion in the audit trail
    """
    request_id = getattr(request.state, 'request_id', None)
    
    service = DocumentService(db)
    document = await service.confirm_upload(
        document_id=document_id,
        user_id=current_user.id,
        request_id=request_id
    )
    
    return DocumentResponse.model_validate(document)


@router.post(
    "/upload",
    response_model=List[DocumentUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple documents",
    response_description="List of uploaded documents with full metadata and presigned URLs"
)
async def upload_documents(
    request_data: DocumentUploadRequestMulti,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Upload multiple documents in a single request.
    
    This endpoint:
    - Accepts multiple files with metadata
    - Creates document records in the database
    - Generates presigned S3 PUT URLs for each file
    - Returns full metadata including file_id (UUID) for frontend state management
    
    The client should:
    1. Upload files directly to S3 using the provided presigned URLs
    2. Call POST /api/documents/{id}/confirm after each successful upload
    """
    request_id = getattr(request.state, 'request_id', None)
    service = DocumentService(db)
    
    results = []
    errors = []
    
    for file_data in request_data.files:
        try:
            result = await service.initiate_upload(
                user_id=current_user.id,
                document_type=file_data.document_type,
                file_name=file_data.file_name,
                content_type=file_data.content_type,
                file_size=file_data.file_size,
                request_id=request_id
            )
            results.append(DocumentUploadResponse(**result))
        except HTTPException as e:
            errors.append({
                "file_name": file_data.file_name,
                "error": e.detail,
                "status_code": e.status_code
            })
        except Exception as e:
            logger.error(
                "document_upload_error",
                file_name=file_data.file_name,
                error=str(e),
                exc_info=True
            )
            errors.append({
                "file_name": file_data.file_name,
                "error": "Internal server error during upload initiation"
            })
    
    if not results and errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors, "message": "All file uploads failed"}
        )
    
    if errors:
        logger.warning(
            "partial_document_upload_failures",
            successful=len(results),
            failed=len(errors),
            errors=errors
        )
    
    return results


@router.get(
    "/me",
    response_model=DocumentListResponse,
    summary="Get my documents",
    response_description="List of all documents belonging to the authenticated user with signed URLs"
)
async def get_my_documents(
    document_type: Optional[DocumentType] = None,
    status: Optional[DocumentStatus] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all documents for the authenticated user with full metadata.
    
    Security: Automatically filters by current_user.id - users can only see their own documents.
    
    Frontend Integration:
    - Returns file_id (UUID) for each document for state management
    - Includes signed_url (presigned URL) for document access
    - Returns complete metadata: file_name, size, mime_type, status, uploaded_at
    - Enables frontend to fully rehydrate Zustand state on page reload
    
    Optional query parameters:
    - document_type: Filter by document type
    - status: Filter by status
    """
    service = DocumentService(db)
    documents = service.list_user_documents(
        user_id=current_user.id,
        document_type=document_type,
        status=status
    )
    
    document_responses = []
    for doc in documents:
        doc_data = await service.get_document_with_url(doc)
        document_responses.append(DocumentResponse(**doc_data))
    
    return DocumentListResponse(
        documents=document_responses,
        total=len(document_responses)
    )


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
    
    Security: Validates document ownership (user_id check) before generating URL.
    
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
    summary="List user documents (deprecated - use /me)",
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
    
    document_responses = []
    for doc in documents:
        doc_data = await service.get_document_with_url(doc)
        document_responses.append(DocumentResponse(**doc_data))
    
    return DocumentListResponse(
        documents=document_responses,
        total=len(document_responses)
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    response_description="Document deleted successfully"
)
async def delete_document(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Delete a document by file UUID.
    
    This endpoint:
    - Validates document ownership
    - Prevents deletion of documents attached to role requests
    - Removes document record from database
    - Logs deletion in audit trail
    """
    request_id = getattr(request.state, 'request_id', None)
    service = DocumentService(db)
    
    deleted = await service.delete_document(
        file_id=file_id,
        user_id=current_user.id,
        request_id=request_id
    )
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)

