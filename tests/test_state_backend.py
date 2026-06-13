"""Tests for state persistence backends."""

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.state_backend import LocalStateBackend, SpacesStateBackend
from src.types import ArticleState


@dataclass(frozen=True)
class FakeConfig:
    state_file_path: str = "state.json"


def _sample_state() -> dict[str, ArticleState]:
    return {
        "article-a": ArticleState(
            slug="article-a",
            sha256="abc123",
            last_modified="2026-01-01T00:00:00Z",
            article_id=42,
            openai_file_id="file-1",
        )
    }


class TestLocalStateBackend:
    def test_load_returns_empty_when_missing(self, tmp_path):
        cfg = FakeConfig(state_file_path=str(tmp_path / "missing.json"))
        backend = LocalStateBackend(cfg)
        assert backend.load() == {}

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "state.json"
        cfg = FakeConfig(state_file_path=str(path))
        backend = LocalStateBackend(cfg)
        state = _sample_state()

        backend.save(state)
        loaded = backend.load()

        assert loaded["article-a"].openai_file_id == "file-1"
        assert loaded["article-a"].article_id == 42
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["article-a"]["openai_file_id"] == "file-1"


@dataclass(frozen=True)
class SpacesFakeConfig:
    state_file_path: str = "optibot/state.json"
    spaces_access_key_id: str = "KEY"
    spaces_secret_access_key: str = "SECRET"
    spaces_bucket: str = "my-bucket"
    spaces_region: str = "sgp1"


class TestSpacesStateBackend:
    @patch("src.state_backend.boto3.client")
    def test_load_returns_empty_on_missing_key(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )

        backend = SpacesStateBackend(SpacesFakeConfig())
        assert backend.load() == {}

        mock_client.get_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="optibot/state.json",
        )

    @patch("src.state_backend.boto3.client")
    def test_save_and_load_round_trip(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        stored: dict[str, bytes] = {}

        def fake_put_object(**kwargs):
            stored["body"] = kwargs["Body"]

        mock_client.put_object.side_effect = fake_put_object
        mock_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: stored["body"])
        }

        backend = SpacesStateBackend(SpacesFakeConfig())
        state = _sample_state()
        backend.save(state)
        loaded = backend.load()

        assert loaded["article-a"].openai_file_id == "file-1"
        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "my-bucket"
        assert call_kwargs["Key"] == "optibot/state.json"
        assert call_kwargs["ContentType"] == "application/json"

    @patch("src.state_backend.boto3.client")
    def test_uses_correct_endpoint(self, mock_boto_client):
        SpacesStateBackend(SpacesFakeConfig(spaces_region="sgp1"))
        mock_boto_client.assert_called_once_with(
            "s3",
            endpoint_url="https://sgp1.digitaloceanspaces.com",
            aws_access_key_id="KEY",
            aws_secret_access_key="SECRET",
            region_name="sgp1",
        )
