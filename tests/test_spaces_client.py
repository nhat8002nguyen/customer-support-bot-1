"""Tests for shared DigitalOcean Spaces client helpers."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from src.spaces_client import make_spaces_client, put_text_object


@dataclass(frozen=True)
class SpacesCfg:
    spaces_access_key_id: str = "KEY"
    spaces_secret_access_key: str = "SECRET"
    spaces_bucket: str = "my-bucket"
    spaces_region: str = "sgp1"


@patch("src.spaces_client.boto3.client")
def test_make_spaces_client_uses_sgp1_endpoint(mock_boto_client):
    make_spaces_client(SpacesCfg())
    mock_boto_client.assert_called_once_with(
        "s3",
        endpoint_url="https://sgp1.digitaloceanspaces.com",
        aws_access_key_id="KEY",
        aws_secret_access_key="SECRET",
        region_name="sgp1",
    )


@patch("src.spaces_client.make_spaces_client")
def test_put_text_object_replaces_entire_object(mock_make_client):
    mock_client = MagicMock()
    mock_make_client.return_value = mock_client
    cfg = SpacesCfg()

    put_text_object(cfg, "optibot/job.log", "line1\nline2\n", "text/plain")

    mock_client.put_object.assert_called_once_with(
        Bucket="my-bucket",
        Key="optibot/job.log",
        Body=b"line1\nline2\n",
        ContentType="text/plain",
    )
