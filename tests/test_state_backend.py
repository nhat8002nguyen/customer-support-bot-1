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
    @patch("src.state_backend.make_spaces_client")
    def test_load_returns_empty_on_missing_key(self, mock_make_client):
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client
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

    @patch("src.state_backend.put_text_object")
    @patch("src.state_backend.make_spaces_client")
    def test_save_and_load_round_trip(self, mock_make_client, mock_put_text):
        mock_client = MagicMock()
        mock_make_client.return_value = mock_client
        stored: dict[str, str] = {}

        def fake_put_text(cfg, key, body, content_type):
            stored["body"] = body

        mock_put_text.side_effect = fake_put_text
        mock_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: stored["body"].encode("utf-8"))
        }

        backend = SpacesStateBackend(SpacesFakeConfig())
        state = _sample_state()
        backend.save(state)
        loaded = backend.load()

        assert loaded["article-a"].openai_file_id == "file-1"
        mock_put_text.assert_called_once()
        call_args = mock_put_text.call_args
        assert call_args[0][1] == "optibot/state.json"
        assert call_args[0][3] == "application/json"

    @patch("src.state_backend.make_spaces_client")
    def test_uses_correct_endpoint(self, mock_make_client):
        SpacesStateBackend(SpacesFakeConfig(spaces_region="sgp1"))
        mock_make_client.assert_called_once()
        cfg = mock_make_client.call_args[0][0]
        assert cfg.spaces_region == "sgp1"
