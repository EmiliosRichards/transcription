import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self, bucket_name: str):
        """
        Initializes the StorageService.
        Boto3 will automatically use credentials from the environment variables:
        - AWS_ACCESS_KEY_ID
        - AWS_SECRET_ACCESS_KEY
        - AWS_ENDPOINT_URL
        """
        if not bucket_name:
            raise ValueError("Storage service bucket name is not provided.")
        
        self.bucket_name = bucket_name
        
        # The region is needed for some operations like pre-signed URLs.
        # It's derived from the endpoint URL.
        endpoint_url = os.environ.get('AWS_ENDPOINT_URL', '')
        region = endpoint_url.split('.')[1] if 'backblazeb2.com' in endpoint_url else None

        # Explicitly pass the Backblaze endpoint when creating the client
        # so boto3 talks to B2 rather than AWS S3.
        self.s3_client = boto3.client('s3', endpoint_url=endpoint_url or None, region_name=region)

    def check_connection(self) -> bool:
        """
        Checks if the connection to the B2 bucket is working.
        Returns True if successful, False otherwise.
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("Successfully connected to B2 bucket.")
            return True
        except ClientError as e:
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

    def create_presigned_url(self, object_key: str, expiration: int = 3600) -> str | None:
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
        bucket_name = os.getenv("B2_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("B2_BUCKET_NAME environment variable not set.")
        # Boto3 will now implicitly use the AWS_* environment variables.
        # We only need to provide the bucket name.
        _storage_service_instance = StorageService(bucket_name=bucket_name)
    return _storage_service_instance