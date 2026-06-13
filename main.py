"""OptiBot Mini-Clone — entry point.

Orchestrates: scrape → delta detection → OpenAI Vector Store upload.
"""

from __future__ import annotations

import logging
import sys

from src.config import load_config
from src.job_log import attach_log_buffer, persist_job_log
from src.scraper import ScrapeIncompleteError, run_scraper
from src.state import (
    build_next_state,
    detect_deltas,
    find_removed_slugs,
    load_state,
    persist_state,
)
from src.types import SyncResult
from src.uploader import remove_stale_articles, sync_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("main")


def run_job(cfg) -> int:
    try:
        articles = run_scraper(cfg)
    except ScrapeIncompleteError as exc:
        log.error("Scrape incomplete: %s", exc)
        return 1

    if not articles:
        log.warning("No articles scraped; nothing to upload.")
        return 0

    log.info("Scraped %d articles", len(articles))

    if cfg.min_articles > 0 and len(articles) < cfg.min_articles:
        log.error(
            "Scraped %d articles, below minimum of %d",
            len(articles),
            cfg.min_articles,
        )
        return 1

    prev_state = load_state(cfg)

    removed_slugs = find_removed_slugs(articles, prev_state)
    if removed_slugs:
        log.info("Detected %d removed article(s)", len(removed_slugs))
        remove_stale_articles(removed_slugs, prev_state, cfg)

    result = detect_deltas(articles, prev_state)

    log.info(
        "Delta — added: %d, updated: %d, skipped: %d",
        len(result.added),
        len(result.updated),
        len(result.skipped),
    )

    to_upload = result.added + result.updated
    sync_result = SyncResult()
    if to_upload:
        sync_result = sync_articles(to_upload, cfg, prev_state)
        log.info(
            "Upload — succeeded: %d, failed: %d",
            len(sync_result.succeeded),
            sync_result.failed,
        )
    else:
        log.info("Nothing to upload — all articles up to date.")

    next_state = build_next_state(articles, prev_state, result, sync_result.succeeded)
    persist_state(cfg, next_state)
    log.info("State persisted — done.")

    if sync_result.failed > 0:
        return 1

    return 0


def main() -> int:
    log_buffer = attach_log_buffer()
    cfg = None
    exit_code = 1

    try:
        cfg = load_config()
        exit_code = run_job(cfg)
    except RuntimeError as exc:
        log.error(exc)

    if cfg is not None:
        persist_job_log(cfg, log_buffer.getvalue())

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
