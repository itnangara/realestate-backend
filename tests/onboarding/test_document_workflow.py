"""
Integration tests for document upload workflow

Tests end-to-end document upload flow:
- Upload initiation → Confirm → Download
- Feature flag disabled scenario
- Invalid file type/size
- S3 unavailable scenario
- Authorization checks
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import status

from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.core.feature_flags import feature_flags


@pytest.fixture(scope="function", autouse=True)
def setup_document_tables(db_session):
    """
    Create tables needed for document workflow tests.
    
    Uses ORM model creation - custom types handle SQLite compatibility automatically.
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create Document table
    Document.__table__.create(bind=db_session.bind, checkfirst=True)
    
    yield
    
    # Clean up
    try:
        Document.__table__.drop(bind=db_session.bind, checkfirst=True)
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


@pytest.fixture
def test_user_with_email_verified(db_session, auth_service, test_roles):
    """Create test user with verified email"""
    from datetime import datetime
    hashed_password = auth_service.get_password_hash("testpass123")
    user = User(
        email="user@test.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        hashed_password=hashed_password,
        email_verified_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # Assign buyer role
    buyer_role = db_session.query(test_roles[0].__class__).filter_by(name="buyer").first()
    from app.models.user_role import UserRole
    user_role = UserRole(user_id=user.id, role_id=buyer_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


@pytest.fixture
def user_token(client, test_user_with_email_verified):
    """Get user authentication token"""
    response = client.post("/api/auth/login", data={
        "username": "user@test.com",
        "password": "testpass123"
    })
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def user_headers(user_token):
    """User authentication headers"""
    return {"Authorization": f"Bearer {user_token}"}


class TestDocumentUploadWorkflow:
    """Tests for complete document upload workflow"""
    
    @pytest.mark.asyncio
    async def test_complete_upload_workflow(self, client, user_headers, db_session, test_user_with_email_verified):
        """Test complete workflow: initiate → confirm → download"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch('app.services.document_service.s3_service.generate_s3_key', return_value="test-doc-123.pdf"), \
             patch('app.services.document_service.s3_service.generate_presigned_put_url', return_value="https://s3.amazonaws.com/upload-url"), \
             patch('app.services.document_service.s3_service.generate_presigned_get_url', return_value="https://s3.amazonaws.com/download-url"):
            
            mock_flag.return_value = True
            
            # Step 1: Initiate upload
            upload_data = {
                "document_type": "id_front",
                "file_name": "id_front.pdf",
                "content_type": "application/pdf",
                "file_size": 100 * 1024  # 100KB
            }
            
            response = client.post(
                "/api/documents/upload",
                json=upload_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            upload_response = response.json()
            assert "document_id" in upload_response
            assert "upload_url" in upload_response
            assert "s3_key" in upload_response
            document_id = upload_response["document_id"]
            
            # Verify document in database
            document = db_session.query(Document).filter_by(id=document_id).first()
            assert document is not None
            assert document.user_id == test_user_with_email_verified.id
            assert document.type == DocumentType.ID_FRONT
            assert document.status == DocumentStatus.PENDING
            
            # Step 2: Confirm upload
            response = client.post(
                f"/api/documents/{document_id}/confirm",
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            confirm_response = response.json()
            assert confirm_response["status"] == DocumentStatus.UPLOADED.value
            
            # Verify document status updated
            db_session.refresh(document)
            assert document.status == DocumentStatus.UPLOADED
            
            # Step 3: Get download URL
            response = client.get(
                f"/api/documents/{document_id}",
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_200_OK
            download_response = response.json()
            assert "download_url" in download_response
            assert download_response["document_id"] == document_id
    
    @pytest.mark.asyncio
    async def test_upload_feature_flag_disabled(self, client, user_headers):
        """Test upload fails when feature flag is disabled"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = False
            
            upload_data = {
                "document_type": "id_front",
                "file_name": "id_front.pdf",
                "content_type": "application/pdf",
                "file_size": 100 * 1024
            }
            
            response = client.post(
                "/api/documents/upload",
                json=upload_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "disabled" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_upload_invalid_file_size(self, client, user_headers):
        """Test upload fails with file size exceeding limit"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            upload_data = {
                "document_type": "id_front",
                "file_name": "large_file.pdf",
                "content_type": "application/pdf",
                "file_size": 11 * 1024 * 1024  # 11MB (exceeds 10MB limit)
            }
            
            response = client.post(
                "/api/documents/upload",
                json=upload_data,
                headers=user_headers
            )
            
            # Pydantic validation happens first, so we get 422 instead of 400
            assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
            response_data = response.json()
            detail = response_data.get("detail", [])
            
            # Pydantic returns list of error dicts, extract messages
            if isinstance(detail, list):
                error_messages = []
                for error in detail:
                    if isinstance(error, dict):
                        # Extract message from error dict
                        msg = error.get("msg", "")
                        loc = error.get("loc", [])
                        error_messages.append(f"{'.'.join(str(l) for l in loc)}: {msg}")
                    else:
                        error_messages.append(str(error))
                detail_str = " ".join(error_messages)
            else:
                detail_str = str(detail)
            
            # Check for size-related validation errors (Pydantic uses "less_than_equal" type)
            assert ("size" in detail_str.lower() or 
                    "file_size" in detail_str.lower() or
                    "less_than_equal" in str(response_data).lower() or
                    any("file_size" in str(error).lower() for error in detail if isinstance(error, dict)))
    
    @pytest.mark.asyncio
    async def test_upload_invalid_content_type(self, client, user_headers):
        """Test upload fails with invalid content type"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            upload_data = {
                "document_type": "id_front",
                "file_name": "document.exe",
                "content_type": "application/x-executable",
                "file_size": 100 * 1024
            }
            
            response = client.post(
                "/api/documents/upload",
                json=upload_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_upload_s3_unavailable(self, client, user_headers):
        """Test upload fails gracefully when S3 is unavailable"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch('app.services.document_service.s3_service.generate_s3_key', return_value="test-doc-123.pdf"), \
             patch('app.services.document_service.s3_service.generate_presigned_put_url', return_value=None):
            
            mock_flag.return_value = True
            
            upload_data = {
                "document_type": "id_front",
                "file_name": "id_front.pdf",
                "content_type": "application/pdf",
                "file_size": 100 * 1024
            }
            
            response = client.post(
                "/api/documents/upload",
                json=upload_data,
                headers=user_headers
            )
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "s3" in response.json()["detail"].lower() or "unavailable" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_confirm_upload_unauthorized(self, client, user_headers, db_session, test_user_with_email_verified):
        """Test confirming another user's document fails"""
        # Create another user
        from app.services.auth_service import AuthService
        auth_service = AuthService(db_session)
        hashed_password = auth_service.get_password_hash("otherpass")
        other_user = User(
            email="other@test.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password=hashed_password
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        # Create document for other user
        document = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="other-user-doc.pdf",
            status=DocumentStatus.PENDING
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        # Try to confirm as different user
        response = client.post(
            f"/api/documents/{document.id}/confirm",
            headers=user_headers
        )
        
        # Document service returns 404 if document not found or doesn't belong to user
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    @pytest.mark.asyncio
    async def test_download_unauthorized(self, client, user_headers, db_session, test_user_with_email_verified):
        """Test downloading another user's document fails"""
        # Create another user
        from app.services.auth_service import AuthService
        auth_service = AuthService(db_session)
        hashed_password = auth_service.get_password_hash("otherpass")
        other_user = User(
            email="other@test.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password=hashed_password
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        # Create document for other user
        document = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="other-user-doc.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        # Try to download as different user
        with patch('app.services.document_service.s3_service.generate_presigned_get_url', return_value="https://s3.amazonaws.com/download-url"):
            response = client.get(
                f"/api/documents/{document.id}",
                headers=user_headers
            )
            
            # Document service returns 404 if document not found or doesn't belong to user
            assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    @pytest.mark.asyncio
    async def test_list_user_documents(self, client, user_headers, db_session, test_user_with_email_verified):
        """Test listing user's documents"""
        # Create multiple documents for the user
        documents = [
            Document(
                user_id=test_user_with_email_verified.id,
                type=DocumentType.ID_FRONT,
                s3_key="doc1.pdf",
                status=DocumentStatus.UPLOADED
            ),
            Document(
                user_id=test_user_with_email_verified.id,
                type=DocumentType.ID_BACK,
                s3_key="doc2.pdf",
                status=DocumentStatus.PENDING
            ),
            Document(
                user_id=test_user_with_email_verified.id,
                type=DocumentType.PROOF_OF_ADDRESS,
                s3_key="doc3.pdf",
                status=DocumentStatus.UPLOADED
            )
        ]
        for doc in documents:
            db_session.add(doc)
        db_session.commit()
        
        # List all documents
        response = client.get(
            "/api/documents",
            headers=user_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert list_response["total"] == 3
        assert len(list_response["documents"]) == 3
        
        # Filter by status
        response = client.get(
            "/api/documents?status=uploaded",
            headers=user_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert list_response["total"] == 2
        assert all(doc["status"] == DocumentStatus.UPLOADED.value for doc in list_response["documents"])
        
        # Filter by type
        response = client.get(
            "/api/documents?document_type=id_front",
            headers=user_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        list_response = response.json()
        assert list_response["total"] == 1
        assert list_response["documents"][0]["type"] == DocumentType.ID_FRONT.value

