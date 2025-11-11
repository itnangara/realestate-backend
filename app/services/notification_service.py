"""
Notification Service for sending emails via AWS SES

Handles:
- Email sending via AWS SES
- Role approval/rejection notifications
- KYC approval/rejection notifications
- Template generation (text and HTML)
- Error handling and graceful degradation
"""

import boto3
from botocore.exceptions import ClientError
from decouple import config
from typing import Optional, List
from app.core.logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    """
    Service for sending email notifications via AWS SES
    
    Features:
    - Singleton pattern for consistent instance
    - Graceful degradation when SES unavailable
    - Text and HTML email support
    - Template-based notifications
    """
    
    def __init__(self):
        """Initialize NotificationService with AWS SES client"""
        self.aws_access_key_id = config("AWS_ACCESS_KEY_ID", default=None)
        self.aws_secret_access_key = config("AWS_SECRET_ACCESS_KEY", default=None)
        self.aws_region = config("AWS_REGION", default="us-east-1")
        self.from_email = config("AWS_SES_FROM_EMAIL", default=None)
        
        # Initialize SES client if credentials available
        self.ses_client = None
        if self.aws_access_key_id and self.aws_secret_access_key:
            try:
                self.ses_client = boto3.client(
                    'ses',
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region
                )
                logger.info(
                    "notification_service_initialized",
                    region=self.aws_region,
                    from_email=self.from_email
                )
            except Exception as e:
                logger.warning(
                    "notification_service_ses_client_failed",
                    error=str(e),
                    message="SES client initialization failed - notifications will be disabled"
                )
                self.ses_client = None
        else:
            logger.warning(
                "notification_service_no_credentials",
                message="AWS credentials not configured - notifications will be disabled"
            )
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None
    ) -> bool:
        """
        Send an email via AWS SES
        
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
                "email_send_skipped_ses_unavailable",
                to_email=to_email,
                subject=subject
            )
            return False
        
        if not self.from_email:
            logger.error(
                "email_send_failed_no_from_email",
                to_email=to_email,
                subject=subject
            )
            return False
        
        try:
            message = {
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8"
                },
                "Body": {
                    "Text": {
                        "Data": body_text,
                        "Charset": "UTF-8"
                    }
                }
            }
            
            # Add HTML body if provided
            if body_html:
                message["Body"]["Html"] = {
                    "Data": body_html,
                    "Charset": "UTF-8"
                }
            
            response = self.ses_client.send_email(
                Source=self.from_email,
                Destination={
                    "ToAddresses": [to_email]
                },
                Message=message
            )
            
            logger.info(
                "email_sent_successfully",
                to_email=to_email,
                subject=subject,
                message_id=response.get("MessageId")
            )
            
            return True
            
        except ClientError as e:
            logger.error(
                "email_send_failed_client_error",
                to_email=to_email,
                subject=subject,
                error_code=e.response.get("Error", {}).get("Code"),
                error_message=e.response.get("Error", {}).get("Message")
            )
            return False
            
        except Exception as e:
            logger.error(
                "email_send_failed_unexpected_error",
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
        approved_roles: List[str]
    ) -> bool:
        """
        Send role approval notification email
        
        Args:
            to_email: User email address
            user_name: User's full name
            approved_roles: List of approved role names
            
        Returns:
            True if email sent successfully, False otherwise
        """
        roles_str = ", ".join(approved_roles)
        subject = f"Role Request Approved - {roles_str}"
        
        # Generate text body
        body_text = f"""
Dear {user_name},

Your role request has been approved! You have been granted the following role(s):

{roles_str}

You can now access features associated with these roles.

Thank you,
Real Estate Platform Team
"""
        
        # Generate HTML body
        body_html = f"""
<html>
<body>
    <h2>Role Request Approved</h2>
    <p>Dear {user_name},</p>
    <p>Your role request has been approved! You have been granted the following role(s):</p>
    <ul>
        {''.join(f'<li>{role}</li>' for role in approved_roles)}
    </ul>
    <p>You can now access features associated with these roles.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
"""
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text.strip(),
            body_html=body_html.strip()
        )
    
    def send_role_rejection_notification(
        self,
        to_email: str,
        user_name: str,
        rejected_roles: List[str],
        reason: Optional[str] = None
    ) -> bool:
        """
        Send role rejection notification email
        
        Args:
            to_email: User email address
            user_name: User's full name
            rejected_roles: List of rejected role names
            reason: Optional rejection reason
            
        Returns:
            True if email sent successfully, False otherwise
        """
        roles_str = ", ".join(rejected_roles)
        subject = f"Role Request Rejected - {roles_str}"
        
        # Generate text body
        body_text = f"""
Dear {user_name},

We regret to inform you that your role request for the following role(s) has been rejected:

{roles_str}
"""
        
        if reason:
            body_text += f"\nReason: {reason}\n"
        
        body_text += """
If you believe this is an error or would like to provide additional information, please contact our support team.

Thank you,
Real Estate Platform Team
"""
        
        # Generate HTML body
        body_html = f"""
<html>
<body>
    <h2>Role Request Update</h2>
    <p>Dear {user_name},</p>
    <p>We regret to inform you that your role request for the following role(s) has been rejected:</p>
    <ul>
        {''.join(f'<li>{role}</li>' for role in rejected_roles)}
    </ul>
"""
        
        if reason:
            body_html += f"<p><strong>Reason:</strong> {reason}</p>"
        
        body_html += """
    <p>If you believe this is an error or would like to provide additional information, please contact our support team.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
"""
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text.strip(),
            body_html=body_html.strip()
        )
    
    def send_kyc_approval_notification(
        self,
        to_email: str,
        user_name: str
    ) -> bool:
        """
        Send KYC approval notification email
        
        Args:
            to_email: User email address
            user_name: User's full name
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "KYC Verification Approved"
        
        # Generate text body
        body_text = f"""
Dear {user_name},

Your KYC (Know Your Customer) verification has been approved!

Your identity documents have been verified and you can now proceed with your role requests.

Thank you,
Real Estate Platform Team
"""
        
        # Generate HTML body
        body_html = f"""
<html>
<body>
    <h2>KYC Verification Approved</h2>
    <p>Dear {user_name},</p>
    <p>Your KYC (Know Your Customer) verification has been approved!</p>
    <p>Your identity documents have been verified and you can now proceed with your role requests.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
"""
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text.strip(),
            body_html=body_html.strip()
        )
    
    def send_kyc_rejection_notification(
        self,
        to_email: str,
        user_name: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send KYC rejection notification email
        
        Args:
            to_email: User email address
            user_name: User's full name
            reason: Optional rejection reason
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "KYC Verification Rejected"
        
        # Generate text body
        body_text = f"""
Dear {user_name},

We regret to inform you that your KYC (Know Your Customer) verification has been rejected.
"""
        
        if reason:
            body_text += f"\nReason: {reason}\n"
        
        body_text += """
Please ensure your documents are clear, valid, and match the information provided. You may resubmit your documents for verification.

If you have questions, please contact our support team.

Thank you,
Real Estate Platform Team
"""
        
        # Generate HTML body
        body_html = f"""
<html>
<body>
    <h2>KYC Verification Update</h2>
    <p>Dear {user_name},</p>
    <p>We regret to inform you that your KYC (Know Your Customer) verification could not be completed.</p>
"""
        
        if reason:
            body_html += f"<p><strong>Reason:</strong> {reason}</p>"
        
        body_html += """
    <p>Please ensure your documents are clear, valid, and match the information provided. You may resubmit your documents for verification.</p>
    <p>If you have questions, please contact our support team.</p>
    <p>Thank you,<br>Real Estate Platform Team</p>
</body>
</html>
"""
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text.strip(),
            body_html=body_html.strip()
        )
    
    def send_verification_email(
        self,
        to_email: str,
        user_name: str,
        verification_link: str
    ) -> bool:
        """
        Send email verification email with verification link.
        
        Args:
            to_email: User email address
            user_name: User's full name
            verification_link: Full URL to verification page with token
            
        Returns:
            True if email sent successfully, False otherwise
        """
        subject = "Verify Your Email Address"
        
        # Generate text body
        body_text = f"""
Dear {user_name},

Thank you for registering with Real Estate Platform!

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you did not create an account, please ignore this email.

Thank you,
Real Estate Platform Team
"""
        
        # Generate HTML body
        body_html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2c3e50;">Verify Your Email Address</h2>
        <p>Dear {user_name},</p>
        <p>Thank you for registering with Real Estate Platform!</p>
        <p>Please verify your email address by clicking the button below:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verification_link}" 
               style="background-color: #3498db; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 5px; display: inline-block;">
                Verify Email Address
            </a>
        </div>
        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #7f8c8d; font-size: 12px;">{verification_link}</p>
        <p style="color: #e74c3c; font-size: 14px;"><strong>This link will expire in 24 hours.</strong></p>
        <p>If you did not create an account, please ignore this email.</p>
        <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
        <p style="color: #95a5a6; font-size: 12px;">Thank you,<br>Real Estate Platform Team</p>
    </div>
</body>
</html>
"""
        
        return self.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text.strip(),
            body_html=body_html.strip()
        )


# Singleton instance
notification_service = NotificationService()

