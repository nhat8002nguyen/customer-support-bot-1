"""Tests for the OpenAI Vector Store uploader (with mocked OpenAI SDK)."""

from unittest.mock import MagicMock, patch

from src.types import Article, ArticleState
from src.uploader import remove_stale_articles, sync_articles


def _fake_cfg(
    api_key="sk-test",
    vs_id="vs_test123",
    d_dir="data/articles",
    timeout_s=60.0,
):
    class FakeConfig:
        openai_api_key = api_key
        openai_vector_store_id = vs_id
        data_dir = d_dir
        poll_timeout_s = timeout_s

    return FakeConfig()


@patch("src.uploader.OpenAI")
def test_sync_articles_no_articles(mock_openai):
    cfg = _fake_cfg()
    result = sync_articles([], cfg)
    assert result.succeeded == {}
    assert result.failed == 0
    mock_openai.assert_not_called()


@patch("src.uploader.OpenAI")
def test_sync_articles_file_not_found(mock_openai, tmp_path):
    cfg = _fake_cfg(d_dir=str(tmp_path))
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

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
    result = sync_articles(articles, cfg)
    assert result.succeeded == {}
    assert result.failed == 1


@patch("src.uploader.OpenAI")
def test_sync_upload_success(mock_openai, tmp_path):
    (tmp_path / "test-article.md").write_text("# Test", encoding="utf-8")

    mock_client = MagicMock()

    mock_file = MagicMock()
    mock_file.id = "file-abc123"
    mock_client.files.create.return_value = mock_file

    mock_vf = MagicMock()
    mock_vf.status = "completed"
    mock_vf.usage_bytes = 42
    mock_client.vector_stores.files.create.return_value = mock_vf
    mock_client.vector_stores.files.retrieve.return_value = mock_vf

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

    result = sync_articles(articles, cfg)
    assert result.succeeded == {"test-article": "file-abc123"}
    assert result.failed == 0
    mock_client.files.create.assert_called_once()
    mock_client.vector_stores.files.create.assert_called_once()


@patch("src.uploader.OpenAI")
def test_sync_deletes_previous_file_on_update(mock_openai, tmp_path):
    (tmp_path / "test-article.md").write_text("# Test", encoding="utf-8")

    mock_client = MagicMock()
    mock_file = MagicMock()
    mock_file.id = "file-new"
    mock_client.files.create.return_value = mock_file

    mock_vf = MagicMock()
    mock_vf.status = "completed"
    mock_vf.usage_bytes = 42
    mock_client.vector_stores.files.create.return_value = mock_vf
    mock_client.vector_stores.files.retrieve.return_value = mock_vf

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
    prev_state = {
        "test-article": ArticleState(
            slug="test-article",
            sha256="old",
            last_modified="2026-01-01T00:00:00Z",
            openai_file_id="file-old",
        )
    }

    sync_articles(articles, cfg, prev_state)

    mock_client.vector_stores.files.delete.assert_called_once_with(
        vector_store_id="vs_test123",
        file_id="file-old",
    )
    mock_client.files.delete.assert_called_once_with("file-old")


@patch("src.uploader.OpenAI")
def test_sync_deletes_orphan_when_attach_fails(mock_openai, tmp_path):
    (tmp_path / "test-article.md").write_text("# Test", encoding="utf-8")

    mock_client = MagicMock()
    mock_file = MagicMock()
    mock_file.id = "file-orphan"
    mock_client.files.create.return_value = mock_file

    mock_vf = MagicMock()
    mock_vf.status = "failed"
    mock_client.vector_stores.files.create.return_value = mock_vf
    mock_client.vector_stores.files.retrieve.return_value = mock_vf
    mock_client.vector_stores.retrieve.return_value = MagicMock(
        file_counts=MagicMock(total=0, completed=0, in_progress=0, failed=0),
        usage_bytes=0,
    )
    mock_openai.return_value = mock_client

    cfg = _fake_cfg(d_dir=str(tmp_path), timeout_s=0.1)
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

    result = sync_articles(articles, cfg)
    assert result.failed == 1
    mock_client.files.delete.assert_called_with("file-orphan")


@patch("src.uploader.OpenAI")
def test_remove_stale_articles(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    cfg = _fake_cfg()
    prev_state = {
        "gone-article": ArticleState(
            slug="gone-article",
            sha256="abc",
            last_modified="2026-01-01T00:00:00Z",
            openai_file_id="file-gone",
        )
    }

    removed = remove_stale_articles(["gone-article"], prev_state, cfg)
    assert removed == 1
    mock_client.vector_stores.files.delete.assert_called_once_with(
        vector_store_id="vs_test123",
        file_id="file-gone",
    )
