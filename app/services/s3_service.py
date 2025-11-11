"""
S3 Service for secure document uploads with presigned URLs

Handles:
- Presigned PUT URLs for uploads (15 min expiry)
- Presigned GET URLs for downloads (1 hour expiry)
- Separate PII bucket/path handling
- Document metadata storage
"""

import boto3
from botocore.exceptions import ClientError
from decouple import config
from typing import Optional
from datetime import timedelta
import uuid
from app.core.logger import get_logger

logger = get_logger(__name__)


class S3Service:
    """S3 service for document uploads with presigned URLs"""
    
    def __init__(self):
        """Initialize S3 client with credentials from environment"""
        self.aws_access_key_id = config("AWS_ACCESS_KEY_ID", default=None)
        self.aws_secret_access_key = config("AWS_SECRET_ACCESS_KEY", default=None)
        self.aws_region = config("AWS_REGION", default="us-east-1")
        self.bucket_name = config("AWS_BUCKET_NAME", default=None)
        
        # Separate PII bucket/path for sensitive documents
        # Default to bucket_name if AWS_S3_PII_BUCKET is not set or empty
        pii_bucket_config = config("AWS_S3_PII_BUCKET", default="")
        self.pii_bucket = pii_bucket_config if pii_bucket_config else self.bucket_name
        self.pii_path = config("AWS_S3_PII_PATH", default="kyc-documents/")
        
        # Initialize S3 client
        if self.aws_access_key_id and self.aws_secret_access_key:
            try:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region
                )
                logger.info(
                    "s3_service_initialized",
                    region=self.aws_region,
                    bucket_name=self.bucket_name,
                    pii_bucket=self.pii_bucket,
                    has_access_key=bool(self.aws_access_key_id),
                    has_secret_key=bool(self.aws_secret_access_key)
                )
            except Exception as e:
                logger.error(
                    "s3_service_init_failed",
                    error=str(e),
                    region=self.aws_region
                )
                self.s3_client = None
        else:
            logger.warning(
                "s3_service_no_credentials",
                has_access_key=bool(self.aws_access_key_id),
                has_secret_key=bool(self.aws_secret_access_key),
                message="AWS credentials not configured - S3 service will not work"
            )
            self.s3_client = None
    
    def generate_presigned_put_url(
        self,
        s3_key: str,
        content_type: str = "application/octet-stream",
        expires_in: int = 900,  # 15 minutes default
        is_pii: bool = False
    ) -> Optional[str]:
        """
        Generate presigned PUT URL for document upload
        
        Args:
            s3_key: S3 object key (path) where file will be stored
            content_type: MIME type of the file
            expires_in: URL expiration time in seconds (default 900 = 15 min)
            is_pii: Whether this is a PII document (uses separate bucket/path)
        
        Returns:
            Presigned PUT URL or None if S3 not configured
        """
        if not self.s3_client:
            logger.error("S3 client not initialized - check AWS credentials")
            return None
        
        try:
            # Use PII bucket/path if specified
            bucket = self.pii_bucket if is_pii else self.bucket_name
            key = f"{self.pii_path}{s3_key}" if is_pii else s3_key
            
            logger.debug(
                "presigned_url_generation_start",
                bucket=bucket,
                key=key,
                is_pii=is_pii,
                content_type=content_type,
                expires_in=expires_in
            )
            
            if not bucket:
                logger.error(
                    "s3_bucket_not_configured",
                    bucket_name=self.bucket_name,
                    pii_bucket=self.pii_bucket,
                    is_pii=is_pii
                )
                return None
            
            # Generate presigned URL
            url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket,
                    'Key': key,
                    'ContentType': content_type
                },
                ExpiresIn=expires_in
            )
            
            logger.info(
                "presigned_put_url_generated",
                bucket=bucket,
                key=key,
                expires_in=expires_in,
                is_pii=is_pii,
                url_length=len(url) if url else 0
            )
            
            return url
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown') if hasattr(e, 'response') else 'Unknown'
            error_message = e.response.get('Error', {}).get('Message', str(e)) if hasattr(e, 'response') else str(e)
            logger.error(
                "failed_to_generate_presigned_put_url_client_error",
                error_code=error_code,
                error_message=error_message,
                s3_key=s3_key,
                bucket=bucket if 'bucket' in locals() else None,
                is_pii=is_pii,
                region=self.aws_region
            )
            return None
        except Exception as e:
            logger.error(
                "failed_to_generate_presigned_put_url_unexpected_error",
                error_type=type(e).__name__,
                error_message=str(e),
                s3_key=s3_key,
                bucket=bucket if 'bucket' in locals() else None,
                is_pii=is_pii,
                region=self.aws_region,
                exc_info=True
            )
            return None
    
    def generate_presigned_get_url(
        self,
        s3_key: str,
        expires_in: int = 3600,  # 1 hour default
        is_pii: bool = False
    ) -> Optional[str]:
        """
        Generate presigned GET URL for document download
        
        Args:
            s3_key: S3 object key (path) of the file
            expires_in: URL expiration time in seconds (default 3600 = 1 hour)
            is_pii: Whether this is a PII document (uses separate bucket/path)
        
        Returns:
            Presigned GET URL or None if S3 not configured
        """
        if not self.s3_client:
            logger.error("S3 client not initialized - check AWS credentials")
            return None
        
        try:
            # Use PII bucket/path if specified
            bucket = self.pii_bucket if is_pii else self.bucket_name
            key = f"{self.pii_path}{s3_key}" if is_pii else s3_key
            
            if not bucket:
                logger.error("S3 bucket name not configured")
                return None
            
            # Generate presigned URL
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket,
                    'Key': key
                },
                ExpiresIn=expires_in
            )
            
            logger.info(
                "presigned_get_url_generated",
                bucket=bucket,
                key=key,
                expires_in=expires_in,
                is_pii=is_pii
            )
            
            return url
            
        except ClientError as e:
            logger.error(
                "failed_to_generate_presigned_get_url",
                error=str(e),
                s3_key=s3_key,
                is_pii=is_pii
            )
            return None
    
    def generate_s3_key(
        self,
        user_id: int,
        document_type: str,
        file_extension: str = ""
    ) -> str:
        """
        Generate unique S3 key for document storage
        
        Args:
            user_id: User ID who owns the document
            document_type: Type of document (e.g., 'id_front', 'proof_of_address')
            file_extension: File extension (e.g., '.pdf', '.jpg')
        
        Returns:
            S3 key path (e.g., 'users/123/id_front/abc123.pdf')
        """
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{document_type}_{unique_id}{file_extension}"
        return f"users/{user_id}/{document_type}/{filename}"
    
    def delete_object(
        self,
        s3_key: str,
        is_pii: bool = False
    ) -> bool:
        """
        Delete object from S3
        
        Args:
            s3_key: S3 object key to delete
            is_pii: Whether this is a PII document
        
        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            logger.error("S3 client not initialized - check AWS credentials")
            return False
        
        try:
            bucket = self.pii_bucket if is_pii else self.bucket_name
            key = f"{self.pii_path}{s3_key}" if is_pii else s3_key
            
            if not bucket:
                logger.error("S3 bucket name not configured")
                return False
            
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            
            logger.info(
                "s3_object_deleted",
                bucket=bucket,
                key=key,
                is_pii=is_pii
            )
            
            return True
            
        except ClientError as e:
            logger.error(
                "failed_to_delete_s3_object",
                error=str(e),
                s3_key=s3_key,
                is_pii=is_pii
            )
            return False


# Singleton instance
s3_service = S3Service()

