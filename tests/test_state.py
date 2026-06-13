"""Tests for delta detection in the state module."""

import json

from src.state import (
    build_next_state,
    compute_sha256,
    detect_deltas,
    find_removed_slugs,
    load_state,
    persist_state,
)
from src.types import Article, ArticleState, DeltaResult


def _make_article(slug: str, content: str = "content", article_id: int = 1) -> Article:
    return Article(
        id=article_id,
        title=slug.replace("-", " ").title(),
        slug=slug,
        body_html="",
        md_content=content,
        updated_at="2026-01-01T00:00:00Z",
        html_url=f"https://support.optisigns.com/hc/en-us/articles/1-{slug}",
    )


def _make_state(
    slug: str,
    content: str = "content",
    file_id: str = "",
    article_id: int = 1,
) -> dict[str, ArticleState]:
    return {
        slug: ArticleState(
            slug=slug,
            sha256=compute_sha256(content),
            last_modified="2026-01-01T00:00:00Z",
            article_id=article_id,
            openai_file_id=file_id,
        )
    }


class TestDeltaDetection:
    def test_all_added_when_no_previous_state(self):
        articles = [_make_article("a"), _make_article("b")]
        result = detect_deltas(articles, {})
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


class TestStatePersistence:
    def test_build_next_state_keeps_previous_hash_on_failed_upload(self):
        articles = [_make_article("a", "new content")]
        prev = _make_state("a", "old content", file_id="file-old")
        result = DeltaResult(updated=articles)
        next_state = build_next_state(articles, prev, result, succeeded={})

        assert next_state["a"].sha256 == prev["a"].sha256
        assert next_state["a"].openai_file_id == "file-old"

    def test_build_next_state_records_successful_upload(self):
        articles = [_make_article("a", "new content")]
        prev = _make_state("a", "old content", file_id="file-old")
        result = DeltaResult(updated=articles)
        next_state = build_next_state(
            articles, prev, result, succeeded={"a": "file-new"}
        )

        assert next_state["a"].sha256 == compute_sha256("new content")
        assert next_state["a"].openai_file_id == "file-new"

    def test_find_removed_slugs(self):
        articles = [_make_article("a"), _make_article("b")]
        prev = _make_state("a") | _make_state("b") | _make_state("c")
        removed = find_removed_slugs(articles, prev)
        assert removed == ["c"]

    def test_persist_and_load_state_round_trip(self, tmp_path):
        path = tmp_path / "state.json"
        state = _make_state("a", "hello", file_id="file-1", article_id=42)
        persist_state(str(path), state)

        loaded = load_state(str(path))
        assert loaded["a"].openai_file_id == "file-1"
        assert loaded["a"].article_id == 42

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "openai_file_id" in raw["a"]
