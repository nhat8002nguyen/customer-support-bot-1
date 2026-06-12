"""OpenAI Vector Store uploader — uploads Markdown files and syncs to a Vector Store."""

from __future__ import annotations

import logging

from src.types import Article

log = logging.getLogger("uploader")


def sync_articles(articles: list[Article], cfg) -> tuple[int, int]:
    """Upload Markdown files to OpenAI and attach them to the configured Vector Store.

    Returns (succeeded_count, failed_count).
    """
    # TODO: implement in Phase 4
    log.warning("Uploader not yet implemented — returning 0/0.")
    return 0, 0
