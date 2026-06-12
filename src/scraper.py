"""Zendesk scraper — fetches articles from the Help Center API and converts to Markdown."""

from __future__ import annotations

import logging

from src.types import Article

log = logging.getLogger("scraper")


def run_scraper(cfg) -> list[Article]:
    """Fetch articles from Zendesk Help Center and save as Markdown files.

    Returns the list of Article objects (with .md files already on disk).
    """
    # TODO: implement in Phase 2
    log.warning("Scraper not yet implemented — returning empty list.")
    return []
