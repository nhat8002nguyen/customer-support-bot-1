"""State persistence and delta detection via SHA256 hashing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from typing import Any

from src.types import Article, ArticleState, DeltaResult

log = logging.getLogger("state")


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_state(path: str) -> dict[str, ArticleState]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw: dict[str, dict[str, Any]] = json.load(f)
    return {
        k: ArticleState(
            slug=v.get("slug", k),
            sha256=v["sha256"],
            last_modified=v["last_modified"],
            article_id=v.get("article_id", 0),
            openai_file_id=v.get("openai_file_id", ""),
        )
        for k, v in raw.items()
    }


def _serialize_state(state: dict[str, ArticleState]) -> dict[str, dict[str, Any]]:
    return {
        k: {
            "slug": v.slug,
            "sha256": v.sha256,
            "last_modified": v.last_modified,
            "article_id": v.article_id,
            "openai_file_id": v.openai_file_id,
        }
        for k, v in state.items()
    }


def persist_state(path: str, state: dict[str, ArticleState]) -> None:
    """Atomically write state to disk."""
    serializable = _serialize_state(state)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


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
