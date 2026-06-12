"""Tests for the OpenAI Vector Store uploader (with mocked OpenAI SDK)."""

from unittest.mock import MagicMock, patch

from src.types import Article
from src.uploader import sync_articles


def _fake_cfg(api_key="sk-test", vs_id="vs_test123", d_dir="data/articles"):
    class FakeConfig:
        openai_api_key = api_key
        openai_vector_store_id = vs_id
        data_dir = d_dir

    return FakeConfig()


@patch("src.uploader.OpenAI")
def test_sync_articles_no_articles(mock_openai):
    """sync_articles with empty list should return (0, 0) without calling OpenAI."""
    cfg = _fake_cfg()
    result = sync_articles([], cfg)
    assert result == (0, 0)
    mock_openai.assert_not_called()


@patch("src.uploader.OpenAI")
def test_sync_articles_file_not_found(mock_openai, tmp_path):
    """sync_articles should handle files that don't exist on disk."""
    cfg = _fake_cfg(d_dir=str(tmp_path))
    articles = [
        Article(
            id=1,
            title="Test",
            slug="test-article",
            body_html="",
            md_content="# Test",
            updated_at="2026-01-01T00:00:00Z",
            html_url="https://support.optisigns.com/hc/en-us/articles/1-test",
        )
    ]
    succeeded, failed = sync_articles(articles, cfg)
    assert succeeded == 0
    assert failed == 1  # file doesn't exist


@patch("src.uploader.OpenAI")
def test_sync_upload_success(mock_openai, tmp_path):
    """sync_articles with existing file and mock API should succeed."""
    # Write a test .md file
    (tmp_path / "test-article.md").write_text("# Test", encoding="utf-8")

    # Mock the OpenAI SDK chain
    mock_client = MagicMock()

    # Mock file creation response
    mock_file = MagicMock()
    mock_file.id = "file-abc123"
    mock_client.files.create.return_value = mock_file

    # Mock vector store file creation + polling
    mock_vf = MagicMock()
    mock_vf.status = "completed"
    mock_vf.usage_bytes = 42
    mock_client.vector_stores.files.create.return_value = mock_vf
    mock_client.vector_stores.files.retrieve.return_value = mock_vf

    # Mock vector store retrieve for summary
    mock_vs = MagicMock()
    mock_vs.file_counts.total = 1
    mock_vs.file_counts.completed = 1
    mock_vs.file_counts.in_progress = 0
    mock_vs.file_counts.failed = 0
    mock_vs.usage_bytes = 42
    mock_client.vector_stores.retrieve.return_value = mock_vs

    mock_openai.return_value = mock_client

    cfg = _fake_cfg(d_dir=str(tmp_path))
    articles = [
        Article(
            id=1,
            title="Test",
            slug="test-article",
            body_html="",
            md_content="# Test",
            updated_at="2026-01-01T00:00:00Z",
            html_url="https://support.optisigns.com/hc/en-us/articles/1-test",
        )
    ]

    succeeded, failed = sync_articles(articles, cfg)
    assert succeeded == 1
    assert failed == 0

    # Verify the upload chain was called
    mock_client.files.create.assert_called_once()
    mock_client.vector_stores.files.create.assert_called_once()
