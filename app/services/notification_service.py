"""
Notification Service for sending emails via AWS SES

Handles:
- Email notifications for role approvals/rejections
- KYC approval/rejection notifications
- Template-based email sending
"""

import boto3
from botocore.exceptions import ClientError
from decouple import config
from typing import Optional, Dict, Any
from app.core.logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Service for sending notifications via AWS SES"""
    
    def __init__(self):
        """Initialize SES client with credentials from environment"""
        self.aws_access_key_id = config("AWS_ACCESS_KEY_ID", default=None)
        self.aws_secret_access_key = config("AWS_SECRET_ACCESS_KEY", default=None)
        self.aws_region = config("AWS_REGION", default="us-east-1")
        self.from_email = config("AWS_SES_FROM_EMAIL", default="noreply@example.com")
        
        # Initialize SES client
        if self.aws_access_key_id and self.aws_secret_access_key:
            try:
                self.ses_client = boto3.client(
                    'ses',
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region
                )
            except Exception as e:
                logger.warning(
                    "ses_client_initialization_failed",
                    error=str(e),
                    message="SES client initialization failed - notifications will not work"
                )
                self.ses_client = None
        else:
            logger.warning("AWS credentials not configured - SES service will not work")
            self.ses_client = None
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None
    ) -> bool:
        """
        Send email via AWS SES
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text email body
            body_html: Optional HTML email body
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.ses_client:
            logger.warning(
                "email_not_sent_ses_unavailable",
                to_email=to_email,
                subject=subject
            )
            return False
        
        try:
            destination = {"ToAddresses": [to_email]}
            message = {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}}
            }
            
            if body_html:
                message["Body"]["Html"] = {"Data": body_html, "Charset": "UTF-8"}
            
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination=destination,
                Message=message
            )
            
            logger.info(
                "email_sent",
                to_email=to_email,
                subject=subject,
                message_id=response.get("MessageId")
            )
            
            return True
            
        except ClientError as e:
            logger.error(
                "email_send_failed",
                to_email=to_email,
                subject=subject,
                error_code=e.response.get("Error", {}).get("Code"),
                error_message=e.response.get("Error", {}).get("Message")
            )
            return False
        except Exception as e:
            logger.error(
                "email_send_unexpected_error",
                to_email=to_email,
                subject=subject,
                error=str(e),
                exc_info=True
            )
            return False
    
    def send_role_approval_notification(
        self,
        to_email: str,
        user_name: str,
        approved_roles: list[str]
    ) -> bool:
        """
        Send notification for role approval
        
        Args:
            to_email: Recipient email address
            user_name: User's name
            approved_roles: List of approved role names
            
        Returns:
            True if email sent successfully
        """
        subject = f"Role Request Approved - {', '.join(approved_roles)}"
        
        body_text = f"""
Hello {user_name},

Your role request has been approved!

Approved roles: {', '.join(approved_roles)}

You can now access features associated with these roles.

Thank you,
Real Estate Platform Team
        """.strip()
        
        body_html = f"""
<html>
<body>
    <h2>Role Request Approved</h2>
    <p>Hello {user_name},</p>
    <p>Your role request has been approved!</p>
    <p><strong>Approved roles:</strong> {', '.join(approved_roles)}</p>
    <p>You can now access features associated with these roles.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
        """.strip()
        
        return self.send_email(to_email, subject, body_text, body_html)
    
    def send_role_rejection_notification(
        self,
        to_email: str,
        user_name: str,
        rejected_roles: list[str],
        reason: Optional[str] = None
    ) -> bool:
        """
        Send notification for role rejection
        
        Args:
            to_email: Recipient email address
            user_name: User's name
            rejected_roles: List of rejected role names
            reason: Optional rejection reason
            
        Returns:
            True if email sent successfully
        """
        subject = f"Role Request Rejected - {', '.join(rejected_roles)}"
        
        body_text = f"""
Hello {user_name},

Your role request has been rejected.

Rejected roles: {', '.join(rejected_roles)}
        """.strip()
        
        if reason:
            body_text += f"\n\nReason: {reason}"
        
        body_text += "\n\nIf you have questions, please contact support.\n\nThank you,\nReal Estate Platform Team"
        
        body_html = f"""
<html>
<body>
    <h2>Role Request Rejected</h2>
    <p>Hello {user_name},</p>
    <p>Your role request has been rejected.</p>
    <p><strong>Rejected roles:</strong> {', '.join(rejected_roles)}</p>
        """.strip()
        
        if reason:
            body_html += f"<p><strong>Reason:</strong> {reason}</p>"
        
        body_html += """
    <p>If you have questions, please contact support.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
        """.strip()
        
        return self.send_email(to_email, subject, body_text, body_html)
    
    def send_kyc_approval_notification(
        self,
        to_email: str,
        user_name: str
    ) -> bool:
        """
        Send notification for KYC approval
        
        Args:
            to_email: Recipient email address
            user_name: User's name
            
        Returns:
            True if email sent successfully
        """
        subject = "KYC Verification Approved"
        
        body_text = f"""
Hello {user_name},

Your KYC (Know Your Customer) verification has been approved.

You can now proceed with your role requests.

Thank you,
Real Estate Platform Team
        """.strip()
        
        body_html = f"""
<html>
<body>
    <h2>KYC Verification Approved</h2>
    <p>Hello {user_name},</p>
    <p>Your KYC (Know Your Customer) verification has been approved.</p>
    <p>You can now proceed with your role requests.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
        """.strip()
        
        return self.send_email(to_email, subject, body_text, body_html)
    
    def send_kyc_rejection_notification(
        self,
        to_email: str,
        user_name: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send notification for KYC rejection
        
        Args:
            to_email: Recipient email address
            user_name: User's name
            reason: Optional rejection reason
            
        Returns:
            True if email sent successfully
        """
        subject = "KYC Verification Rejected"
        
        body_text = f"""
Hello {user_name},

Your KYC (Know Your Customer) verification has been rejected.
        """.strip()
        
        if reason:
            body_text += f"\n\nReason: {reason}"
        
        body_text += "\n\nPlease review your documents and submit again if needed.\n\nThank you,\nReal Estate Platform Team"
        
        body_html = f"""
<html>
<body>
    <h2>KYC Verification Rejected</h2>
    <p>Hello {user_name},</p>
    <p>Your KYC (Know Your Customer) verification has been rejected.</p>
        """.strip()
        
        if reason:
            body_html += f"<p><strong>Reason:</strong> {reason}</p>"
        
        body_html += """
    <p>Please review your documents and submit again if needed.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
        """.strip()
        
        return self.send_email(to_email, subject, body_text, body_html)


# Singleton instance
notification_service = NotificationService()

