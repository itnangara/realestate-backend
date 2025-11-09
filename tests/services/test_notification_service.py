"""
Enterprise-Grade Notification Service Tests

Comprehensive test suite for NotificationService covering:
- Email sending via AWS SES
- Role approval/rejection notifications
- KYC approval/rejection notifications
- Template generation (text and HTML)
- Error handling and graceful degradation
- SES client initialization
- Configuration validation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from app.services.notification_service import NotificationService, notification_service


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_ses_client():
    """Create a mock AWS SES client"""
    mock_client = MagicMock()
    mock_client.send_email = MagicMock(return_value={"MessageId": "test-message-id"})
    return mock_client


@pytest.fixture
def notification_service_with_mock(mock_ses_client):
    """Create NotificationService with mocked SES client"""
    service = NotificationService()
    service.ses_client = mock_ses_client
    service.from_email = "test@example.com"
    return service


# ============================================================================
# Test Initialization
# ============================================================================

class TestNotificationServiceInitialization:
    """Tests for NotificationService initialization"""
    
    def test_init_with_credentials(self, mock_ses_client):
        """Test initialization with AWS credentials"""
        with patch('boto3.client', return_value=mock_ses_client), \
             patch('app.services.notification_service.config') as mock_config:
            
            mock_config.side_effect = lambda key, default=None: {
                "AWS_ACCESS_KEY_ID": "test-key",
                "AWS_SECRET_ACCESS_KEY": "test-secret",
                "AWS_REGION": "us-east-1",
                "AWS_SES_FROM_EMAIL": "noreply@example.com"
            }.get(key, default)
            
            service = NotificationService()
            
            assert service.ses_client is not None
            assert service.from_email == "noreply@example.com"
    
    def test_init_without_credentials(self):
        """Test initialization without AWS credentials"""
        with patch('app.services.notification_service.config') as mock_config:
            mock_config.side_effect = lambda key, default=None: None
            
            service = NotificationService()
            
            assert service.ses_client is None
    
    def test_init_ses_client_failure_handled_gracefully(self):
        """Test that SES client initialization failure is handled gracefully"""
        with patch('boto3.client', side_effect=Exception("Connection failed")), \
             patch('app.services.notification_service.config') as mock_config, \
             patch('app.services.notification_service.logger') as mock_logger:
            
            mock_config.side_effect = lambda key, default=None: {
                "AWS_ACCESS_KEY_ID": "test-key",
                "AWS_SECRET_ACCESS_KEY": "test-secret"
            }.get(key, default)
            
            service = NotificationService()
            
            assert service.ses_client is None
            # Verify warning was logged
            mock_logger.warning.assert_called()


# ============================================================================
# Test Send Email
# ============================================================================

class TestSendEmail:
    """Tests for send_email method"""
    
    def test_send_email_success_text_only(self, notification_service_with_mock, mock_ses_client):
        """Test successful email sending with text only"""
        result = notification_service_with_mock.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Test body"
        )
        
        assert result is True
        mock_ses_client.send_email.assert_called_once()
        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args["Source"] == "test@example.com"
        assert call_args["Destination"]["ToAddresses"] == ["recipient@example.com"]
        assert call_args["Message"]["Subject"]["Data"] == "Test Subject"
        assert call_args["Message"]["Body"]["Text"]["Data"] == "Test body"
        assert "Html" not in call_args["Message"]["Body"]
    
    def test_send_email_success_with_html(self, notification_service_with_mock, mock_ses_client):
        """Test successful email sending with HTML body"""
        result = notification_service_with_mock.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Test body",
            body_html="<html><body>Test HTML</body></html>"
        )
        
        assert result is True
        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args["Message"]["Body"]["Html"]["Data"] == "<html><body>Test HTML</body></html>"
    
    def test_send_email_ses_unavailable(self):
        """Test email sending when SES is unavailable"""
        service = NotificationService()
        service.ses_client = None
        
        result = service.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Test body"
        )
        
        assert result is False
    
    def test_send_email_client_error(self, notification_service_with_mock, mock_ses_client):
        """Test email sending handles ClientError gracefully"""
        error_response = {
            "Error": {
                "Code": "MessageRejected",
                "Message": "Email address not verified"
            }
        }
        mock_ses_client.send_email.side_effect = ClientError(error_response, "SendEmail")
        
        result = notification_service_with_mock.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Test body"
        )
        
        assert result is False
    
    def test_send_email_generic_exception(self, notification_service_with_mock, mock_ses_client):
        """Test email sending handles generic exceptions gracefully"""
        mock_ses_client.send_email.side_effect = Exception("Unexpected error")
        
        result = notification_service_with_mock.send_email(
            to_email="recipient@example.com",
            subject="Test Subject",
            body_text="Test body"
        )
        
        assert result is False


# ============================================================================
# Test Role Approval Notification
# ============================================================================

class TestSendRoleApprovalNotification:
    """Tests for send_role_approval_notification method"""
    
    def test_send_role_approval_notification_success(self, notification_service_with_mock, mock_ses_client):
        """Test successful role approval notification"""
        result = notification_service_with_mock.send_role_approval_notification(
            to_email="user@example.com",
            user_name="John Doe",
            approved_roles=["seller", "agent"]
        )
        
        assert result is True
        mock_ses_client.send_email.assert_called_once()
        call_args = mock_ses_client.send_email.call_args[1]
        
        # Verify subject
        assert "Role Request Approved" in call_args["Message"]["Subject"]["Data"]
        assert "seller" in call_args["Message"]["Subject"]["Data"]
        assert "agent" in call_args["Message"]["Subject"]["Data"]
        
        # Verify body contains user name and roles
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        assert "John Doe" in body_text
        assert "seller" in body_text
        assert "agent" in body_text
        
        # Verify HTML body
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        assert "John Doe" in body_html
        assert "seller" in body_html
        assert "agent" in body_html
    
    def test_send_role_approval_notification_single_role(self, notification_service_with_mock, mock_ses_client):
        """Test role approval notification with single role"""
        result = notification_service_with_mock.send_role_approval_notification(
            to_email="user@example.com",
            user_name="Jane Doe",
            approved_roles=["seller"]
        )
        
        assert result is True
        call_args = mock_ses_client.send_email.call_args[1]
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        assert "seller" in body_text
        assert "Jane Doe" in body_text
    
    def test_send_role_approval_notification_ses_unavailable(self):
        """Test role approval notification when SES is unavailable"""
        service = NotificationService()
        service.ses_client = None
        
        result = service.send_role_approval_notification(
            to_email="user@example.com",
            user_name="John Doe",
            approved_roles=["seller"]
        )
        
        assert result is False


# ============================================================================
# Test Role Rejection Notification
# ============================================================================

class TestSendRoleRejectionNotification:
    """Tests for send_role_rejection_notification method"""
    
    def test_send_role_rejection_notification_success_with_reason(self, notification_service_with_mock, mock_ses_client):
        """Test successful role rejection notification with reason"""
        result = notification_service_with_mock.send_role_rejection_notification(
            to_email="user@example.com",
            user_name="John Doe",
            rejected_roles=["seller", "agent"],
            reason="Insufficient documentation"
        )
        
        assert result is True
        mock_ses_client.send_email.assert_called_once()
        call_args = mock_ses_client.send_email.call_args[1]
        
        # Verify subject
        assert "Role Request Rejected" in call_args["Message"]["Subject"]["Data"]
        
        # Verify body contains reason
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        assert "John Doe" in body_text
        assert "seller" in body_text
        assert "agent" in body_text
        assert "Insufficient documentation" in body_text
        
        # Verify HTML body contains reason
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        assert "Insufficient documentation" in body_html
    
    def test_send_role_rejection_notification_without_reason(self, notification_service_with_mock, mock_ses_client):
        """Test role rejection notification without reason"""
        result = notification_service_with_mock.send_role_rejection_notification(
            to_email="user@example.com",
            user_name="Jane Doe",
            rejected_roles=["seller"],
            reason=None
        )
        
        assert result is True
        call_args = mock_ses_client.send_email.call_args[1]
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        
        # Should not contain reason section
        assert "Reason:" not in body_text
        assert "Reason:" not in body_html
    
    def test_send_role_rejection_notification_ses_unavailable(self):
        """Test role rejection notification when SES is unavailable"""
        service = NotificationService()
        service.ses_client = None
        
        result = service.send_role_rejection_notification(
            to_email="user@example.com",
            user_name="John Doe",
            rejected_roles=["seller"]
        )
        
        assert result is False


# ============================================================================
# Test KYC Approval Notification
# ============================================================================

class TestSendKYCApprovalNotification:
    """Tests for send_kyc_approval_notification method"""
    
    def test_send_kyc_approval_notification_success(self, notification_service_with_mock, mock_ses_client):
        """Test successful KYC approval notification"""
        result = notification_service_with_mock.send_kyc_approval_notification(
            to_email="user@example.com",
            user_name="John Doe"
        )
        
        assert result is True
        mock_ses_client.send_email.assert_called_once()
        call_args = mock_ses_client.send_email.call_args[1]
        
        # Verify subject
        assert call_args["Message"]["Subject"]["Data"] == "KYC Verification Approved"
        
        # Verify body
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        assert "John Doe" in body_text
        assert "KYC" in body_text or "Know Your Customer" in body_text
        assert "approved" in body_text.lower()
        
        # Verify HTML body
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        assert "John Doe" in body_html
        assert "approved" in body_html.lower()
    
    def test_send_kyc_approval_notification_ses_unavailable(self):
        """Test KYC approval notification when SES is unavailable"""
        service = NotificationService()
        service.ses_client = None
        
        result = service.send_kyc_approval_notification(
            to_email="user@example.com",
            user_name="John Doe"
        )
        
        assert result is False


# ============================================================================
# Test KYC Rejection Notification
# ============================================================================

class TestSendKYCRejectionNotification:
    """Tests for send_kyc_rejection_notification method"""
    
    def test_send_kyc_rejection_notification_success_with_reason(self, notification_service_with_mock, mock_ses_client):
        """Test successful KYC rejection notification with reason"""
        result = notification_service_with_mock.send_kyc_rejection_notification(
            to_email="user@example.com",
            user_name="John Doe",
            reason="Document quality insufficient"
        )
        
        assert result is True
        mock_ses_client.send_email.assert_called_once()
        call_args = mock_ses_client.send_email.call_args[1]
        
        # Verify subject
        assert call_args["Message"]["Subject"]["Data"] == "KYC Verification Rejected"
        
        # Verify body contains reason
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        assert "John Doe" in body_text
        assert "rejected" in body_text.lower()
        assert "Document quality insufficient" in body_text
        
        # Verify HTML body contains reason
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        assert "Document quality insufficient" in body_html
    
    def test_send_kyc_rejection_notification_without_reason(self, notification_service_with_mock, mock_ses_client):
        """Test KYC rejection notification without reason"""
        result = notification_service_with_mock.send_kyc_rejection_notification(
            to_email="user@example.com",
            user_name="Jane Doe",
            reason=None
        )
        
        assert result is True
        call_args = mock_ses_client.send_email.call_args[1]
        body_text = call_args["Message"]["Body"]["Text"]["Data"]
        body_html = call_args["Message"]["Body"]["Html"]["Data"]
        
        # Should not contain reason section
        assert "Reason:" not in body_text
        assert "Reason:" not in body_html
    
    def test_send_kyc_rejection_notification_ses_unavailable(self):
        """Test KYC rejection notification when SES is unavailable"""
        service = NotificationService()
        service.ses_client = None
        
        result = service.send_kyc_rejection_notification(
            to_email="user@example.com",
            user_name="John Doe"
        )
        
        assert result is False


# ============================================================================
# Test Singleton Instance
# ============================================================================

class TestNotificationServiceSingleton:
    """Tests for notification_service singleton instance"""
    
    def test_notification_service_singleton_exists(self):
        """Test that singleton instance exists"""
        assert notification_service is not None
        assert isinstance(notification_service, NotificationService)
    
    def test_notification_service_singleton_consistent(self):
        """Test that singleton instance is consistent"""
        from app.services.notification_service import notification_service as service1
        from app.services.notification_service import notification_service as service2
        
        assert service1 is service2

