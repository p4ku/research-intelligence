import logging
import botocore.exceptions
from storages.backends.s3boto3 import S3Boto3Storage

logger = logging.getLogger(__name__)


class ResilientS3Boto3Storage(S3Boto3Storage):
    """
    Subclass of S3Boto3Storage that automatically ensures the target S3 or MinIO
    bucket exists before writing, querying, or reading objects.
    Prevents 'NoSuchBucket' crashes during automated pipelines, local MinIO setups,
    and fresh environment deployments.
    """

    _verified_buckets = set()

    def _ensure_bucket_exists(self):
        bucket_name = self.bucket_name
        if not bucket_name or bucket_name in ResilientS3Boto3Storage._verified_buckets:
            return

        try:
            self.connection.meta.client.head_bucket(Bucket=bucket_name)
            ResilientS3Boto3Storage._verified_buckets.add(bucket_name)
        except botocore.exceptions.ClientError as err:
            error_code = str(err.response.get("Error", {}).get("Code", ""))
            if error_code in ["404", "NoSuchBucket", "NotFound"]:
                try:
                    logger.info("Bucket '%s' does not exist. Auto-creating bucket...", bucket_name)
                    region = getattr(self, "region_name", None)
                    # MinIO and standard AWS us-east-1 accept create_bucket without LocationConstraint
                    try:
                        self.connection.meta.client.create_bucket(Bucket=bucket_name)
                    except Exception:
                        if region and region != "us-east-1":
                            self.connection.meta.client.create_bucket(
                                Bucket=bucket_name,
                                CreateBucketConfiguration={"LocationConstraint": region},
                            )
                        else:
                            raise
                    ResilientS3Boto3Storage._verified_buckets.add(bucket_name)
                    logger.info("Successfully created bucket '%s'.", bucket_name)
                except Exception as create_err:
                    logger.warning("Could not auto-create S3/MinIO bucket '%s': %s", bucket_name, create_err)
            else:
                logger.warning("S3/MinIO head_bucket check error for '%s': %s", bucket_name, err)

    @property
    def bucket(self):
        self._ensure_bucket_exists()
        return super().bucket

    def _save(self, name, content):
        self._ensure_bucket_exists()
        return super()._save(name, content)

    def _open(self, name, mode="rb"):
        self._ensure_bucket_exists()
        return super()._open(name, mode)

    def exists(self, name):
        self._ensure_bucket_exists()
        try:
            return super().exists(name)
        except botocore.exceptions.ClientError as err:
            if err.response.get("Error", {}).get("Code") in ["404", "NoSuchBucket", "NotFound"]:
                return False
            raise

    def listdir(self, name):
        self._ensure_bucket_exists()
        try:
            return super().listdir(name)
        except botocore.exceptions.ClientError as err:
            if err.response.get("Error", {}).get("Code") in ["404", "NoSuchBucket", "NotFound"]:
                return [], []
            raise

    def size(self, name):
        self._ensure_bucket_exists()
        return super().size(name)

    def delete(self, name):
        self._ensure_bucket_exists()
        try:
            return super().delete(name)
        except botocore.exceptions.ClientError as err:
            if err.response.get("Error", {}).get("Code") in ["404", "NoSuchBucket", "NotFound"]:
                return
            raise
