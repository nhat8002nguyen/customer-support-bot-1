"""State persistence and delta detection via SHA256 hashing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from src.types import Article, ArticleState, DeltaResult

log = logging.getLogger("state")


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_state(path: str) -> dict[str, ArticleState]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        raw: dict[str, dict[str, Any]] = json.load(f)
    return {k: ArticleState(**v) for k, v in raw.items()}


def save_state(path: str, articles: list[Article]) -> None:
    state = {
        a.slug: ArticleState(
            slug=a.slug,
            sha256=compute_sha256(a.body_html),
            last_modified=a.updated_at,
        )
        for a in articles
    }
    serializable = {k: {"slug": v.slug, "sha256": v.sha256, "last_modified": v.last_modified} for k, v in state.items()}
    with open(path, "w") as f:
        json.dump(serializable, f, indent=2)


def detect_deltas(
    articles: list[Article], prev_state: dict[str, ArticleState]
) -> DeltaResult:
    result = DeltaResult()
    for a in articles:
        h = compute_sha256(a.body_html)
        existing = prev_state.get(a.slug)
        if existing is None:
            result.added.append(a)
        elif existing.sha256 != h:
            result.updated.append(a)
        else:
            result.skipped.append(a)
    return result
