"""Tests for scraper helpers."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.scraper import (
    ScrapeIncompleteError,
    _build_frontmatter,
    fetch_all_articles,
)
from src.types import Article


def _article(title: str) -> Article:
    return Article(
        id=1,
        title=title,
        slug="test-slug",
        body_html="",
        md_content="",
        updated_at="2026-01-01T00:00:00Z",
        html_url="https://support.optisigns.com/hc/en-us/articles/1-test",
    )


class TestFrontmatter:
    def test_escapes_quotes_in_title(self):
        frontmatter = _build_frontmatter(_article('Say "hello"'))
        assert 'title: "Say \\"hello\\""' in frontmatter


class TestFetchArticles:
    @patch("src.scraper.time.sleep")
    @patch("src.scraper.requests.Session")
    def test_retries_before_failing(self, mock_session_cls, mock_sleep):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = requests.ConnectionError("network down")

        with pytest.raises(ScrapeIncompleteError):
            fetch_all_articles("https://support.optisigns.com", retries=3)

        assert mock_session.get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.scraper.time.sleep")
    @patch("src.scraper.requests.Session")
    def test_succeeds_after_transient_failure(self, mock_session_cls, mock_sleep):
        success = MagicMock()
        success.raise_for_status.return_value = None
        success.json.return_value = {
            "articles": [
                {
                    "id": 1,
                    "draft": False,
                    "html_url": "https://x/a/1-t",
                    "body": "<p>x</p>",
                    "title": "T",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
            "next_page": None,
        }

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = [requests.ConnectionError("flaky"), success]

        articles = fetch_all_articles("https://support.optisigns.com", retries=3)
        assert len(articles) == 1
        assert mock_session.get.call_count == 2
