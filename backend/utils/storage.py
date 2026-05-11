import os
import boto3
from botocore.exceptions import ClientError
from typing import Optional
import io

class StorageService:
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.external_endpoint = os.getenv("MINIO_EXTERNAL_ENDPOINT", self.endpoint)
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket_name = os.getenv("MINIO_BUCKET", "redwire-evidence")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        
        # Initialize S3 client
        self.s3 = boto3.client(
            's3',
            endpoint_url=f"{'https' if self.secure else 'http'}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name='us-east-1' # Minio doesn't strictly need this but boto3 does
        )
        
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Ensure the configured bucket exists in MinIO."""
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"🪣 Creating bucket: {self.bucket_name}")
                self.s3.create_bucket(Bucket=self.bucket_name)
            else:
                print(f"❌ Error checking bucket: {e}")

    async def upload_file(self, file_content: bytes, filename: str, content_type: Optional[str] = None) -> str:
        """Upload a file to MinIO and return its storage key/path."""
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
            
        file_obj = io.BytesIO(file_content)
        self.s3.upload_fileobj(
            file_obj,
            self.bucket_name,
            filename,
            ExtraArgs=extra_args
        )
        return filename

    async def download_file(self, filename: str) -> bytes:
        """Download a file from MinIO."""
        file_obj = io.BytesIO()
        self.s3.download_fileobj(self.bucket_name, filename, file_obj)
        return file_obj.getvalue()

    async def delete_file(self, filename: str):
        """Delete a file from MinIO."""
        self.s3.delete_object(Bucket=self.bucket_name, Key=filename)

    def get_presigned_url(self, filename: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for a file."""
        url = self.s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': filename},
            ExpiresIn=expires_in
        )
        
        # If external endpoint is different from internal, swap it
        if self.external_endpoint != self.endpoint:
            internal_prefix = f"{'https' if self.secure else 'http'}://{self.endpoint}"
            external_prefix = f"{'https' if self.secure else 'http'}://{self.external_endpoint}"
            url = url.replace(internal_prefix, external_prefix)
            
        return url

    async def get_file_stream(self, filename: str):
        """Get a file stream from MinIO."""
        response = self.s3.get_object(Bucket=self.bucket_name, Key=filename)
        return response['Body']

storage_service = StorageService()
