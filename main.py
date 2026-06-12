"""OptiBot Mini-Clone — entry point.

Orchestrates: scrape → delta detection → OpenAI Vector Store upload.
"""

from __future__ import annotations

import logging
import sys

from src.config import load_config
from src.scraper import run_scraper
from src.state import detect_deltas, load_state, save_state
from src.uploader import sync_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("main")


def main() -> int:
    try:
        cfg = load_config()
    except RuntimeError as exc:
        log.error(exc)
        return 1

    # 1. Scrape Zendesk articles → Markdown files
    articles = run_scraper(cfg)
    if not articles:
        log.warning("No articles scraped; nothing to upload.")
        return 0

    log.info("Scraped %d articles", len(articles))

    # 2. Detect delta against previous state
    prev_state = load_state(cfg.state_file_path)
    result = detect_deltas(articles, prev_state)

    log.info(
        "Delta — added: %d, updated: %d, skipped: %d",
        len(result.added),
        len(result.updated),
        len(result.skipped),
    )

    # 3. Upload only new/updated files to OpenAI Vector Store
    to_upload = result.added + result.updated
    if to_upload:
        uploaded, failed = sync_articles(to_upload, cfg)
        log.info("Upload — succeeded: %d, failed: %d", uploaded, failed)
    else:
        log.info("Nothing to upload — all articles up to date.")

    # 4. Persist state hash for next run
    save_state(cfg.state_file_path, articles)
    log.info("State persisted — done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
