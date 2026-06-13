"""State persistence and delta detection via SHA256 hashing."""

from __future__ import annotations

import hashlib
import logging

from src.state_backend import get_state_backend
from src.types import Article, ArticleState, DeltaResult

log = logging.getLogger("state")


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_state(cfg) -> dict[str, ArticleState]:
    return get_state_backend(cfg).load()


def persist_state(cfg, state: dict[str, ArticleState]) -> None:
    get_state_backend(cfg).save(state)


def find_removed_slugs(
    articles: list[Article], prev_state: dict[str, ArticleState]
) -> list[str]:
    current_slugs = {a.slug for a in articles}
    return [slug for slug in prev_state if slug not in current_slugs]


def build_next_state(
    articles: list[Article],
    prev_state: dict[str, ArticleState],
    result: DeltaResult,
    succeeded: dict[str, str],
) -> dict[str, ArticleState]:
    """Build state reflecting upload outcomes — failed uploads keep previous hashes."""
    failed_slugs = {a.slug for a in result.added + result.updated} - set(succeeded)
    next_state: dict[str, ArticleState] = {}

    for article in articles:
        content_hash = compute_sha256(article.md_content)

        if article.slug in failed_slugs:
            if article.slug in prev_state:
                next_state[article.slug] = prev_state[article.slug]
            continue

        if article.slug in succeeded:
            next_state[article.slug] = ArticleState(
                slug=article.slug,
                sha256=content_hash,
                last_modified=article.updated_at,
                article_id=article.id,
                openai_file_id=succeeded[article.slug],
            )
            continue

        previous = prev_state.get(article.slug)
        next_state[article.slug] = ArticleState(
            slug=article.slug,
            sha256=content_hash,
            last_modified=article.updated_at,
            article_id=article.id,
            openai_file_id=previous.openai_file_id if previous else "",
        )

    return next_state


def detect_deltas(
    articles: list[Article], prev_state: dict[str, ArticleState]
) -> DeltaResult:
    result = DeltaResult()
    for article in articles:
        content_hash = compute_sha256(article.md_content)
        existing = prev_state.get(article.slug)
        if existing is None:
            result.added.append(article)
        elif existing.sha256 != content_hash:
            result.updated.append(article)
        else:
            result.skipped.append(article)
    return result
