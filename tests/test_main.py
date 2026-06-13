"""Tests for main.py orchestration."""

from unittest.mock import MagicMock, patch

import main as main_module
from src.types import Article, DeltaResult, SyncResult


def _article(slug: str, content: str = "body") -> Article:
    return Article(
        id=1,
        title=slug,
        slug=slug,
        body_html="",
        md_content=content,
        updated_at="2026-01-01T00:00:00Z",
        html_url=f"https://support.optisigns.com/hc/en-us/articles/1-{slug}",
    )


def _mock_log_buffer(mock_attach_buffer):
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = ""
    mock_attach_buffer.return_value = mock_buffer
    return mock_buffer


@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.persist_state")
@patch("main.sync_articles")
@patch("main.detect_deltas")
@patch("main.find_removed_slugs")
@patch("main.load_state")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_uploads_job_log_on_exit(
    mock_load_config,
    mock_run_scraper,
    mock_load_state,
    mock_find_removed,
    mock_detect_deltas,
    mock_sync_articles,
    mock_persist_state,
    mock_attach_buffer,
    mock_persist_job_log,
):
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = "log lines"
    mock_attach_buffer.return_value = mock_buffer

    mock_cfg = MagicMock(
        min_articles=0,
        job_log_backend="spaces",
    )
    mock_load_config.return_value = mock_cfg
    mock_run_scraper.return_value = [_article("a")]
    mock_load_state.return_value = {}
    mock_find_removed.return_value = []
    mock_detect_deltas.return_value = DeltaResult(added=[_article("a")])
    mock_sync_articles.return_value = SyncResult(succeeded={"a": "file-1"}, failed=0)

    assert main_module.main() == 0
    mock_persist_job_log.assert_called_once_with(mock_cfg, "log lines")


@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.persist_state")
@patch("main.sync_articles")
@patch("main.detect_deltas")
@patch("main.find_removed_slugs")
@patch("main.load_state")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_returns_1_when_uploads_fail(
    mock_load_config,
    mock_run_scraper,
    mock_load_state,
    mock_find_removed,
    mock_detect_deltas,
    mock_sync_articles,
    mock_persist_state,
    mock_attach_buffer,
    mock_persist_job_log,
):
    _mock_log_buffer(mock_attach_buffer)
    mock_load_config.return_value = MagicMock(min_articles=0, state_file_path="state.json")
    mock_run_scraper.return_value = [_article("a")]
    mock_load_state.return_value = {}
    mock_find_removed.return_value = []
    mock_detect_deltas.return_value = DeltaResult(added=[_article("a")])
    mock_sync_articles.return_value = SyncResult(succeeded={}, failed=1)

    assert main_module.main() == 1
    mock_persist_state.assert_called_once()


@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.persist_state")
@patch("main.sync_articles")
@patch("main.detect_deltas")
@patch("main.find_removed_slugs")
@patch("main.load_state")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_returns_0_when_uploads_succeed(
    mock_load_config,
    mock_run_scraper,
    mock_load_state,
    mock_find_removed,
    mock_detect_deltas,
    mock_sync_articles,
    mock_persist_state,
    mock_attach_buffer,
    mock_persist_job_log,
):
    _mock_log_buffer(mock_attach_buffer)
    mock_load_config.return_value = MagicMock(min_articles=0, state_file_path="state.json")
    mock_run_scraper.return_value = [_article("a")]
    mock_load_state.return_value = {}
    mock_find_removed.return_value = []
    mock_detect_deltas.return_value = DeltaResult(added=[_article("a")])
    mock_sync_articles.return_value = SyncResult(succeeded={"a": "file-1"}, failed=0)

    assert main_module.main() == 0


@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_returns_1_on_incomplete_scrape(
    mock_load_config,
    mock_run_scraper,
    mock_attach_buffer,
    mock_persist_job_log,
):
    from src.scraper import ScrapeIncompleteError

    _mock_log_buffer(mock_attach_buffer)
    mock_cfg = MagicMock(min_articles=0)
    mock_load_config.return_value = mock_cfg
    mock_run_scraper.side_effect = ScrapeIncompleteError("network down")

    assert main_module.main() == 1
    mock_persist_job_log.assert_called_once_with(mock_cfg, "")


@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_returns_1_when_below_min_articles(
    mock_load_config,
    mock_run_scraper,
    mock_attach_buffer,
    mock_persist_job_log,
):
    _mock_log_buffer(mock_attach_buffer)
    mock_cfg = MagicMock(min_articles=30)
    mock_load_config.return_value = mock_cfg
    mock_run_scraper.return_value = [_article("a")]

    assert main_module.main() == 1
    mock_persist_job_log.assert_called_once_with(mock_cfg, "")
