"""
Enterprise-Grade Document Service Tests

Comprehensive test suite for DocumentService covering:
- Document upload initiation with feature flag validation
- File size validation
- S3 presigned URL generation
- Document confirmation workflow
- Download URL generation
- Document retrieval and listing
- Authorization checks
- Error handling and edge cases
- Audit logging integration
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.document_service import DocumentService
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.user import User
from app.services.s3_service import s3_service
from app.services.audit_service import audit_service
from app.core.feature_flags import feature_flags


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def setup_document_tables(db_session):
    """
    Create tables needed for document tests (User and Document).
    SQLite-compatible version for testing.
    """
    # Create User table first
    User.__table__.create(bind=db_session.bind, checkfirst=True)
    
    # Create documents table with SQLite-compatible SQL
    from sqlalchemy import inspect as sqlalchemy_inspect, text
    inspector = sqlalchemy_inspect(db_session.bind)
    if 'documents' not in inspector.get_table_names():
        create_table_sql = """
        CREATE TABLE documents (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            type VARCHAR(50) NOT NULL,
            s3_key VARCHAR(255) NOT NULL UNIQUE,
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
        db_session.execute(text(create_table_sql))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents(user_id)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_type ON documents(type)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_user_type ON documents(user_id, type)"))
        db_session.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_user_status ON documents(user_id, status)"))
        db_session.commit()
    
    yield
    
    # Clean up
    try:
        db_session.execute(text("DROP TABLE IF EXISTS documents"))
        db_session.commit()
    except Exception:
        pass
    try:
        User.__table__.drop(bind=db_session.bind, checkfirst=True)
    except Exception:
        pass


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        email="test@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        hashed_password="hashed_password"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def document_service(db_session):
    """Create DocumentService instance"""
    return DocumentService(db_session)


# ============================================================================
# Test Initiate Upload
# ============================================================================

class TestInitiateUpload:
    """Tests for initiate_upload method"""
    
    @pytest.mark.asyncio
    async def test_initiate_upload_success(self, document_service, test_user, db_session):
        """Test successful document upload initiation"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(s3_service, 'generate_s3_key', return_value="documents/123/id_front_abc123.pdf") as mock_key, \
             patch.object(s3_service, 'generate_presigned_put_url', return_value="https://s3.amazonaws.com/upload-url") as mock_url, \
             patch.object(audit_service, 'log_user_action') as mock_audit:
            
            mock_flag.return_value = True
            
            result = await document_service.initiate_upload(
                user_id=test_user.id,
                document_type=DocumentType.ID_FRONT,
                file_name="id_front.pdf",
                content_type="application/pdf",
                file_size=1024 * 1024,  # 1MB
                request_id="req-123"
            )
            
            assert result["document_id"] is not None
            assert result["upload_url"] == "https://s3.amazonaws.com/upload-url"
            assert result["s3_key"] == "documents/123/id_front_abc123.pdf"
            assert result["expires_in"] == 900
            
            # Verify document was created
            document = db_session.query(Document).filter(Document.id == result["document_id"]).first()
            assert document is not None
            assert document.user_id == test_user.id
            assert document.type == DocumentType.ID_FRONT
            assert document.status == DocumentStatus.PENDING
            assert document.s3_key == "documents/123/id_front_abc123.pdf"
            
            # Verify audit log was called
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "document_upload_initiated"
            assert call_args[1]["user_id"] == test_user.id
            assert call_args[1]["target_type"] == "document"
            assert call_args[1]["target_id"] == document.id
    
    @pytest.mark.asyncio
    async def test_initiate_upload_feature_flag_disabled(self, document_service, test_user):
        """Test upload fails when feature flag is disabled"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = False
            
            with pytest.raises(HTTPException) as exc_info:
                await document_service.initiate_upload(
                    user_id=test_user.id,
                    document_type=DocumentType.ID_FRONT,
                    file_name="id_front.pdf",
                    content_type="application/pdf",
                    file_size=1024
                )
            
            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "disabled" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_initiate_upload_file_size_exceeds_limit(self, document_service, test_user):
        """Test upload fails when file size exceeds 10MB"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag:
            mock_flag.return_value = True
            
            with pytest.raises(HTTPException) as exc_info:
                await document_service.initiate_upload(
                    user_id=test_user.id,
                    document_type=DocumentType.ID_FRONT,
                    file_name="large_file.pdf",
                    content_type="application/pdf",
                    file_size=11 * 1024 * 1024  # 11MB
                )
            
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "size" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_initiate_upload_pii_document_separate_bucket(self, document_service, test_user, db_session):
        """Test PII documents use separate bucket/path"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(s3_service, 'generate_s3_key', return_value="kyc-documents/123/id_front_abc123.pdf") as mock_key, \
             patch.object(s3_service, 'generate_presigned_put_url') as mock_url, \
             patch.object(audit_service, 'log_user_action'):
            
            mock_flag.return_value = True
            mock_url.return_value = "https://s3.amazonaws.com/upload-url"
            
            await document_service.initiate_upload(
                user_id=test_user.id,
                document_type=DocumentType.ID_FRONT,  # PII document
                file_name="id_front.pdf",
                content_type="application/pdf",
                file_size=1024
            )
            
            # Verify is_pii=True was passed to S3 service
            mock_url.assert_called_once()
            call_kwargs = mock_url.call_args[1]
            assert call_kwargs["is_pii"] is True
    
    @pytest.mark.asyncio
    async def test_initiate_upload_s3_url_generation_fails(self, document_service, test_user, db_session):
        """Test rollback when S3 URL generation fails"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(s3_service, 'generate_s3_key', return_value="documents/123/id_front_abc123.pdf") as mock_key, \
             patch.object(s3_service, 'generate_presigned_put_url', return_value=None) as mock_url:
            
            mock_flag.return_value = True
            
            with pytest.raises(HTTPException) as exc_info:
                await document_service.initiate_upload(
                    user_id=test_user.id,
                    document_type=DocumentType.ID_FRONT,
                    file_name="id_front.pdf",
                    content_type="application/pdf",
                    file_size=1024
                )
            
            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            
            # Verify document was not persisted (rollback occurred)
            documents = db_session.query(Document).filter(Document.user_id == test_user.id).all()
            assert len(documents) == 0
    
    @pytest.mark.asyncio
    async def test_initiate_upload_file_without_extension(self, document_service, test_user, db_session):
        """Test upload with file that has no extension"""
        with patch.object(feature_flags, 'is_enabled', new_callable=AsyncMock) as mock_flag, \
             patch.object(s3_service, 'generate_s3_key', return_value="documents/123/id_front_abc123") as mock_key, \
             patch.object(s3_service, 'generate_presigned_put_url', return_value="https://s3.amazonaws.com/upload-url") as mock_url, \
             patch.object(audit_service, 'log_user_action'):
            
            mock_flag.return_value = True
            
            result = await document_service.initiate_upload(
                user_id=test_user.id,
                document_type=DocumentType.ID_FRONT,
                file_name="id_front",  # No extension
                content_type="application/pdf",
                file_size=1024
            )
            
            assert result["document_id"] is not None
            # Verify S3 key generation was called with empty extension
            mock_key.assert_called_once()
            call_kwargs = mock_key.call_args[1]
            assert call_kwargs["file_extension"] == ""


# ============================================================================
# Test Confirm Upload
# ============================================================================

class TestConfirmUpload:
    """Tests for confirm_upload method"""
    
    @pytest.mark.asyncio
    async def test_confirm_upload_success(self, document_service, test_user, db_session):
        """Test successful document upload confirmation"""
        # Create a pending document
        document = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front_abc123.pdf",
            status=DocumentStatus.PENDING
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        with patch.object(audit_service, 'log_user_action') as mock_audit:
            result = await document_service.confirm_upload(
                document_id=document.id,
                user_id=test_user.id,
                request_id="req-123"
            )
            
            assert result.status == DocumentStatus.UPLOADED
            assert result.id == document.id
            
            # Verify audit log
            mock_audit.assert_called_once()
            call_args = mock_audit.call_args
            assert call_args[1]["action"] == "document_upload_completed"
            assert call_args[1]["user_id"] == test_user.id
    
    @pytest.mark.asyncio
    async def test_confirm_upload_document_not_found(self, document_service, test_user):
        """Test confirmation fails for non-existent document"""
        with pytest.raises(HTTPException) as exc_info:
            await document_service.confirm_upload(
                document_id=99999,
                user_id=test_user.id
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_confirm_upload_unauthorized_user(self, document_service, test_user, db_session):
        """Test confirmation fails for document owned by different user"""
        # Create another user
        other_user = User(
            email="other@example.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password="hashed_password"
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        # Create document for other user
        document = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/456/id_front_abc123.pdf",
            status=DocumentStatus.PENDING
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        # Try to confirm as test_user (should fail)
        with pytest.raises(HTTPException) as exc_info:
            await document_service.confirm_upload(
                document_id=document.id,
                user_id=test_user.id
            )
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Test Get Download URL
# ============================================================================

class TestGetDownloadUrl:
    """Tests for get_download_url method"""
    
    @pytest.mark.asyncio
    async def test_get_download_url_success(self, document_service, test_user, db_session):
        """Test successful download URL generation"""
        document = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front_abc123.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        with patch.object(s3_service, 'generate_presigned_get_url', return_value="https://s3.amazonaws.com/download-url") as mock_url, \
             patch.object(audit_service, 'log_user_action') as mock_audit:
            
            result = await document_service.get_download_url(
                document_id=document.id,
                user_id=test_user.id,
                request_id="req-123"
            )
            
            assert result["document_id"] == document.id
            assert result["download_url"] == "https://s3.amazonaws.com/download-url"
            assert result["expires_in"] == 3600
            
            # Verify is_pii was passed correctly
            mock_url.assert_called_once()
            call_kwargs = mock_url.call_args[1]
            assert call_kwargs["is_pii"] is True  # ID_FRONT is PII
            assert call_kwargs["expires_in"] == 3600
            
            # Verify audit log
            mock_audit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_download_url_non_pii_document(self, document_service, test_user, db_session):
        """Test download URL for non-PII document"""
        document = Document(
            user_id=test_user.id,
            type=DocumentType.COMPANY_DOC,  # Not PII
            s3_key="documents/123/company_doc_abc123.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        with patch.object(s3_service, 'generate_presigned_get_url', return_value="https://s3.amazonaws.com/download-url") as mock_url, \
             patch.object(audit_service, 'log_user_action'):
            
            await document_service.get_download_url(
                document_id=document.id,
                user_id=test_user.id
            )
            
            # Verify is_pii=False was passed
            call_kwargs = mock_url.call_args[1]
            assert call_kwargs["is_pii"] is False
    
    @pytest.mark.asyncio
    async def test_get_download_url_s3_fails(self, document_service, test_user, db_session):
        """Test download URL generation fails when S3 is unavailable"""
        document = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front_abc123.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        with patch.object(s3_service, 'generate_presigned_get_url', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await document_service.get_download_url(
                    document_id=document.id,
                    user_id=test_user.id
                )
            
            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ============================================================================
# Test Get Document
# ============================================================================

class TestGetDocument:
    """Tests for get_document method"""
    
    def test_get_document_success(self, document_service, test_user, db_session):
        """Test successful document retrieval"""
        document = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front_abc123.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        result = document_service.get_document(
            document_id=document.id,
            user_id=test_user.id
        )
        
        assert result is not None
        assert result.id == document.id
        assert result.user_id == test_user.id
    
    def test_get_document_not_found(self, document_service, test_user):
        """Test retrieval returns None for non-existent document"""
        result = document_service.get_document(
            document_id=99999,
            user_id=test_user.id
        )
        
        assert result is None
    
    def test_get_document_unauthorized(self, document_service, test_user, db_session):
        """Test retrieval returns None for document owned by different user"""
        other_user = User(
            email="other@example.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password="hashed_password"
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        document = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/456/id_front_abc123.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        result = document_service.get_document(
            document_id=document.id,
            user_id=test_user.id
        )
        
        assert result is None


# ============================================================================
# Test List User Documents
# ============================================================================

class TestListUserDocuments:
    """Tests for list_user_documents method"""
    
    def test_list_user_documents_all(self, document_service, test_user, db_session):
        """Test listing all documents for a user"""
        # Create multiple documents
        documents = [
            Document(
                user_id=test_user.id,
                type=DocumentType.ID_FRONT,
                s3_key=f"documents/123/id_front_{i}.pdf",
                status=DocumentStatus.UPLOADED
            )
            for i in range(3)
        ]
        for doc in documents:
            db_session.add(doc)
        db_session.commit()
        
        result = document_service.list_user_documents(user_id=test_user.id)
        
        assert len(result) == 3
        assert all(doc.user_id == test_user.id for doc in result)
    
    def test_list_user_documents_filter_by_type(self, document_service, test_user, db_session):
        """Test filtering documents by type"""
        # Create documents of different types
        doc1 = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front.pdf",
            status=DocumentStatus.UPLOADED
        )
        doc2 = Document(
            user_id=test_user.id,
            type=DocumentType.COMPANY_DOC,
            s3_key="documents/123/company_doc.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(doc1)
        db_session.add(doc2)
        db_session.commit()
        
        result = document_service.list_user_documents(
            user_id=test_user.id,
            document_type=DocumentType.ID_FRONT
        )
        
        assert len(result) == 1
        assert result[0].type == DocumentType.ID_FRONT
    
    def test_list_user_documents_filter_by_status(self, document_service, test_user, db_session):
        """Test filtering documents by status"""
        # Create documents with different statuses
        doc1 = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/id_front.pdf",
            status=DocumentStatus.PENDING
        )
        doc2 = Document(
            user_id=test_user.id,
            type=DocumentType.ID_BACK,
            s3_key="documents/123/id_back.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(doc1)
        db_session.add(doc2)
        db_session.commit()
        
        result = document_service.list_user_documents(
            user_id=test_user.id,
            status=DocumentStatus.UPLOADED
        )
        
        assert len(result) == 1
        assert result[0].status == DocumentStatus.UPLOADED
    
    def test_list_user_documents_empty(self, document_service, test_user):
        """Test listing documents when user has none"""
        result = document_service.list_user_documents(user_id=test_user.id)
        
        assert len(result) == 0


# ============================================================================
# Test Get Documents By IDs
# ============================================================================

class TestGetDocumentsByIds:
    """Tests for get_documents_by_ids method"""
    
    def test_get_documents_by_ids_success(self, document_service, test_user, db_session):
        """Test retrieving multiple documents by IDs"""
        documents = [
            Document(
                user_id=test_user.id,
                type=DocumentType.ID_FRONT,
                s3_key=f"documents/123/doc_{i}.pdf",
                status=DocumentStatus.UPLOADED
            )
            for i in range(3)
        ]
        for doc in documents:
            db_session.add(doc)
        db_session.commit()
        
        document_ids = [doc.id for doc in documents]
        result = document_service.get_documents_by_ids(
            document_ids=document_ids,
            user_id=test_user.id
        )
        
        assert len(result) == 3
        assert all(doc.id in document_ids for doc in result)
    
    def test_get_documents_by_ids_partial_match(self, document_service, test_user, db_session):
        """Test retrieving documents when some IDs don't exist"""
        document = Document(
            user_id=test_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/123/doc.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        result = document_service.get_documents_by_ids(
            document_ids=[document.id, 99999],  # One exists, one doesn't
            user_id=test_user.id
        )
        
        assert len(result) == 1
        assert result[0].id == document.id
    
    def test_get_documents_by_ids_unauthorized(self, document_service, test_user, db_session):
        """Test retrieving documents owned by different user returns empty"""
        other_user = User(
            email="other@example.com",
            username="otheruser",
            first_name="Other",
            last_name="User",
            hashed_password="hashed_password"
        )
        db_session.add(other_user)
        db_session.commit()
        db_session.refresh(other_user)
        
        document = Document(
            user_id=other_user.id,
            type=DocumentType.ID_FRONT,
            s3_key="documents/456/doc.pdf",
            status=DocumentStatus.UPLOADED
        )
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        
        result = document_service.get_documents_by_ids(
            document_ids=[document.id],
            user_id=test_user.id
        )
        
        assert len(result) == 0

