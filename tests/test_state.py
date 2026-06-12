"""Tests for delta detection in the state module."""

from src.state import compute_sha256, detect_deltas
from src.types import Article, ArticleState, DeltaResult


def _make_article(slug: str, content: str = "content") -> Article:
    return Article(
        id=1,
        title=slug.replace("-", " ").title(),
        slug=slug,
        body_html="",
        md_content=content,
        updated_at="2026-01-01T00:00:00Z",
        html_url=f"https://support.optisigns.com/hc/en-us/articles/1-{slug}",
    )


def _make_state(slug: str, content: str = "content") -> dict[str, ArticleState]:
    return {
        slug: ArticleState(
            slug=slug,
            sha256=compute_sha256(content),
            last_modified="2026-01-01T00:00:00Z",
        )
    }


class TestDeltaDetection:
    def test_all_added_when_no_previous_state(self):
        articles = [_make_article("a"), _make_article("b")]
        prev = {}
        result = detect_deltas(articles, prev)
        assert len(result.added) == 2
        assert len(result.updated) == 0
        assert len(result.skipped) == 0

    def test_all_skipped_when_nothing_changed(self):
        articles = [_make_article("a", "hello"), _make_article("b", "world")]
        prev = _make_state("a", "hello") | _make_state("b", "world")
        result = detect_deltas(articles, prev)
        assert len(result.added) == 0
        assert len(result.updated) == 0
        assert len(result.skipped) == 2

    def test_updated_when_hash_differs(self):
        articles = [_make_article("a", "new content")]
        prev = _make_state("a", "old content")
        result = detect_deltas(articles, prev)
        assert len(result.added) == 0
        assert len(result.updated) == 1
        assert len(result.skipped) == 0

    def test_mixed_delta(self):
        articles = [
            _make_article("a", "same"),
            _make_article("b", "changed"),
            _make_article("c", "brand new"),
        ]
        prev = _make_state("a", "same") | _make_state("b", "old")
        result = detect_deltas(articles, prev)
        assert len(result.added) == 1
        assert result.added[0].slug == "c"
        assert len(result.updated) == 1
        assert result.updated[0].slug == "b"
        assert len(result.skipped) == 1
        assert result.skipped[0].slug == "a"
