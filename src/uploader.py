"""OpenAI Vector Store uploader — uploads Markdown files and syncs to a Vector Store."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from openai import OpenAI

from src.types import Article

log = logging.getLogger("uploader")

POLL_INTERVAL_S = 1.0
POLL_TIMEOUT_S = 60.0


def _get_or_create_vector_store(client: OpenAI, vector_store_id: str) -> str:
    """Return existing vector store ID or create a new one."""
    if vector_store_id:
        # Verify it exists
        try:
            client.vector_stores.retrieve(vector_store_id=vector_store_id)
            return vector_store_id
        except Exception as exc:
            log.warning("Vector store %s not found (%s); creating one.", vector_store_id, exc)
    return vector_store_id


def upload_file(client: OpenAI, file_path: str) -> str | None:
    """Upload a single Markdown file to OpenAI and return its file ID."""
    try:
        with open(file_path, "rb") as f:
            response = client.files.create(file=f, purpose="assistants")
        log.info("Uploaded %s → file_id=%s", Path(file_path).name, response.id)
        return response.id
    except Exception as exc:
        log.error("Failed to upload %s: %s", file_path, exc)
        return None


def attach_file_to_vector_store(
    client: OpenAI, vector_store_id: str, file_id: str
) -> bool:
    """Attach an uploaded file to a Vector Store, waiting for completion."""
    try:
        vf = client.vector_stores.files.create(
            vector_store_id=vector_store_id, file_id=file_id
        )
        # Poll until processing completes
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while vf.status in ("in_progress", "queued"):
            if time.monotonic() > deadline:
                log.warning("Timed out waiting for file %s to attach", file_id)
                return False
            time.sleep(POLL_INTERVAL_S)
            vf = client.vector_stores.files.retrieve(
                vector_store_id=vector_store_id, file_id=file_id
            )

        if vf.status == "completed":
            log.info("File %s attached and processed (%d bytes)", file_id, vf.usage_bytes)
            return True
        else:
            log.error("File %s failed with status '%s'", file_id, vf.status)
            return False
    except Exception as exc:
        log.error("Failed to attach file %s: %s", file_id, exc)
        return False


def _log_vector_store_summary(client: OpenAI, vector_store_id: str) -> None:
    """Log the number of files and chunks in the vector store after sync."""
    try:
        vs = client.vector_stores.retrieve(vector_store_id=vector_store_id)
        fc = vs.file_counts
        log.info(
            "Vector Store summary — files: %d (completed: %d, in_progress: %d, failed: %d), "
            "usage_bytes: %d",
            fc.total, fc.completed, fc.in_progress, fc.failed,
            vs.usage_bytes,
        )
    except Exception as exc:
        log.warning("Could not retrieve vector store summary: %s", exc)


def sync_articles(articles: list[Article], cfg) -> tuple[int, int]:
    """Upload Markdown files to OpenAI and attach them to the configured Vector Store.

    Returns (succeeded_count, failed_count).
    """
    if not articles:
        return 0, 0

    client = OpenAI(api_key=cfg.openai_api_key)
    vector_store_id = _get_or_create_vector_store(client, cfg.openai_vector_store_id)

    succeeded = 0
    failed = 0

    for article in articles:
        filepath = os.path.join(cfg.data_dir, f"{article.slug}.md")

        if not os.path.exists(filepath):
            log.warning("File not found (deleted after scrape?): %s", filepath)
            failed += 1
            continue

        file_id = upload_file(client, filepath)
        if file_id is None:
            failed += 1
            continue

        ok = attach_file_to_vector_store(client, vector_store_id, file_id)
        if ok:
            succeeded += 1
        else:
            failed += 1

    # Log final vector store summary (files & chunks)
    _log_vector_store_summary(client, vector_store_id)

    log.info(
        "Sync complete — total: %d, succeeded: %d, failed: %d, vector_store: %s",
        len(articles),
        succeeded,
        failed,
        vector_store_id,
    )

    return succeeded, failed
