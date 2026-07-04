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

    async def head_object(self, filename: str) -> Optional[dict]:
        """Return object metadata (size, etag, last-modified, content-type)
        without downloading the body. Returns ``None`` when the object
        doesn't exist.

        Used at the evidence-export size cap to cross-check the recorded
        ``Evidence.file_size`` against the actual object size — an
        operator with direct MinIO access could have swapped in a
        larger file after upload (GHSA-q8q6-22jx-7rjj follow-up)."""
        try:
            resp = self.s3.head_object(Bucket=self.bucket_name, Key=filename)
            return {
                "size": resp.get("ContentLength"),
                "etag": resp.get("ETag"),
                "last_modified": resp.get("LastModified"),
                "content_type": resp.get("ContentType"),
            }
        except Exception:
            # boto raises ClientError with 404 or NoSuchKey — either way,
            # "we can't verify" is the answer callers care about.
            return None

    def get_presigned_url(self, filename: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for a file.

        GHSA-h77m-pjqc-5cm3: force ``Content-Disposition: attachment`` on
        the presigned response so MinIO instructs the browser to download
        the object rather than render it inline. Closes stored-XSS via a
        ``text/html`` (or ``image/svg+xml``) Content-Type that the
        uploader may have supplied at upload time. The original
        ``Content-Type`` is left intact for clients that explicitly want
        the bytes.
        """
        # Use a safe basename in the Content-Disposition so the storage key
        # itself can't smuggle quote characters or directory traversal.
        import os as _os
        safe_name = _os.path.basename(filename) or "download"
        url = self.s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': self.bucket_name,
                'Key': filename,
                'ResponseContentDisposition': f'attachment; filename="{safe_name}"',
            },
            ExpiresIn=expires_in,
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
