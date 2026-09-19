from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
import botocore.exceptions

from research_intelligence.storage import ResilientS3Boto3Storage


class TestResilientS3Boto3Storage(SimpleTestCase):
    def setUp(self):
        ResilientS3Boto3Storage._verified_buckets.clear()

    @patch("storages.backends.s3boto3.S3Boto3Storage.connection")
    def test_auto_creates_bucket_when_not_found(self, mock_connection):
        storage = ResilientS3Boto3Storage()
        storage.bucket_name = "test-auto-bucket"
        storage.region_name = "eu-central-1"

        # Mock head_bucket returning 404
        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket"
        )
        storage.connection.meta.client = mock_client

        # Call _ensure_bucket_exists
        storage._ensure_bucket_exists()

        # Verify create_bucket was called
        mock_client.create_bucket.assert_called_once()
        self.assertIn("test-auto-bucket", ResilientS3Boto3Storage._verified_buckets)

        # Subsequent call is cached and does not hit client again
        mock_client.head_bucket.reset_mock()
        storage._ensure_bucket_exists()
        mock_client.head_bucket.assert_not_called()

    @patch("storages.backends.s3boto3.S3Boto3Storage.connection")
    def test_exists_returns_false_on_no_such_bucket(self, mock_connection):
        storage = ResilientS3Boto3Storage()
        storage.bucket_name = "nonexistent-bucket"

        mock_client = MagicMock()
        storage.connection.meta.client = mock_client

        with patch.object(ResilientS3Boto3Storage, "_ensure_bucket_exists") as mock_ensure:
            with patch("storages.backends.s3boto3.S3Boto3Storage.exists", side_effect=botocore.exceptions.ClientError(
                {"Error": {"Code": "NoSuchBucket", "Message": "Bucket does not exist"}},
                "HeadObject"
            )):
                result = storage.exists("some/file.pdf")
                self.assertFalse(result)
                mock_ensure.assert_called_once()
