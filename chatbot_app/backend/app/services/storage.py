import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self, bucket_name: str):
        """
        Initializes the StorageService.
        Credential resolution order (most specific first):
        - BACKBLAZE_B2_KEY_ID / BACKBLAZE_B2_APPLICATION_KEY / BACKBLAZE_B2_S3_ENDPOINT / BACKBLAZE_B2_REGION
        - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_ENDPOINT_URL / AWS_REGION
        """
        if not bucket_name:
            raise ValueError("Storage service bucket name is not provided.")
        
        self.bucket_name = bucket_name
        
        # Resolve endpoint/region (prefer Backblaze-specific names)
        endpoint_url = (os.environ.get('BACKBLAZE_B2_S3_ENDPOINT') or os.environ.get('AWS_ENDPOINT_URL', '')).strip()
        region = (
            (os.environ.get('BACKBLAZE_B2_REGION') or '').strip()
            or (endpoint_url.split('.')[1] if 'backblazeb2.com' in endpoint_url else None)
            or (os.environ.get('AWS_REGION') or '').strip()
        )

        # Resolve credentials (prefer Backblaze-specific names)
        key_id = (os.environ.get('BACKBLAZE_B2_KEY_ID') or os.environ.get('AWS_ACCESS_KEY_ID') or '').strip()
        app_key = (os.environ.get('BACKBLAZE_B2_APPLICATION_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY') or '').strip()

        # Log minimal, non-sensitive diagnostics to help detect whitespace/typos
        try:
            masked_key = (key_id[:4] + '...' + key_id[-4:]) if key_id else '(none)'
        except Exception:
            masked_key = '(unavailable)'
        logger.info(
            "Initializing StorageService bucket=%s endpoint=%s region=%s key_id=%s",
            bucket_name,
            endpoint_url or '(default)',
            region or '(default)',
            masked_key,
        )

        # Create the client. If explicit creds are provided, pass them; otherwise, allow
        # boto3 to fall back to its default credential chain (env, config files, IAM, etc.).
        if key_id and app_key:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url or None,
                region_name=region,
                aws_access_key_id=key_id,
                aws_secret_access_key=app_key,
            )
        else:
            self.s3_client = boto3.client('s3', endpoint_url=endpoint_url or None, region_name=region)

    def check_connection(self) -> bool:
        """
        Checks if the connection to the B2 bucket is working.
        Returns True if successful, False otherwise.
        Note: Some application keys may not have permission for HeadBucket/ListBucket.
        In that case, we treat AccessDenied as a "restricted but valid" connection.
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("Successfully connected to B2 bucket.")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code in {"403", "AccessDenied"}:
                logger.warning(
                    "HeadBucket denied (likely restricted key without ListBucket). Proceeding as connected."
                )
                return True
            logger.error(f"Failed to connect to B2 bucket: {e}", exc_info=True)
            return False

    def upload_file(self, file_path: str, object_key: str) -> bool:
        """
        Uploads a file to the B2 bucket.
        """
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_key)
            logger.info(f"Successfully uploaded {file_path} to bucket {self.bucket_name} with key {object_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {file_path}: {e}", exc_info=True)
            return False
        except FileNotFoundError:
            logger.error(f"The file {file_path} was not found for upload.", exc_info=True)
            return False

    def create_presigned_url(self, object_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generates a pre-signed URL to download a file.
        """
        try:
            response = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=expiration
            )
            logger.info(f"Generated pre-signed URL for key {object_key}")
            return response
        except ClientError as e:
            logger.error(f"Failed to generate pre-signed URL for key {object_key}: {e}", exc_info=True)
            return None

_storage_service_instance = None

def get_storage_service():
    """
    Returns a singleton instance of the StorageService, initialized from environment variables.
    """
    global _storage_service_instance
    if _storage_service_instance is None:
        bucket_name = os.getenv("BACKBLAZE_B2_BUCKET") or os.getenv("B2_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("BACKBLAZE_B2_BUCKET or B2_BUCKET_NAME environment variable not set.")
        # Boto3 will now implicitly use the AWS_* environment variables.
        # We only need to provide the bucket name.
        _storage_service_instance = StorageService(bucket_name=bucket_name)
    return _storage_service_instance