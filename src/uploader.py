"""OpenAI Vector Store uploader — uploads Markdown files and syncs to a Vector Store."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from openai import APIConnectionError, APIError, OpenAI

from src.types import Article, ArticleState, SyncResult

log = logging.getLogger("uploader")

POLL_INTERVAL_S = 1.0


def _verify_vector_store(client: OpenAI, vector_store_id: str) -> str:
    """Verify the configured vector store exists and is accessible."""
    if not vector_store_id:
        raise RuntimeError("OPENAI_VECTOR_STORE_ID is required")

    try:
        client.vector_stores.retrieve(vector_store_id=vector_store_id)
        return vector_store_id
    except (APIError, APIConnectionError) as exc:
        raise RuntimeError(
            f"Vector store {vector_store_id} not accessible: {exc}"
        ) from exc


def _delete_openai_file(
    client: OpenAI, vector_store_id: str, file_id: str
) -> None:
    """Detach a file from the vector store and delete it from the account."""
    if not file_id:
        return

    try:
        client.vector_stores.files.delete(
            vector_store_id=vector_store_id, file_id=file_id
        )
        log.info("Detached %s from vector store", file_id)
    except (APIError, APIConnectionError) as exc:
        log.warning("Could not detach %s from vector store: %s", file_id, exc)

    try:
        client.files.delete(file_id)
        log.info("Deleted file %s from OpenAI account", file_id)
    except (APIError, APIConnectionError) as exc:
        log.warning("Could not delete file %s: %s", file_id, exc)


def upload_file(client: OpenAI, file_path: str) -> str | None:
    """Upload a single Markdown file to OpenAI and return its file ID."""
    try:
        with open(file_path, "rb") as f:
            response = client.files.create(file=f, purpose="assistants")
        log.info("Uploaded %s → file_id=%s", Path(file_path).name, response.id)
        return response.id
    except (APIError, APIConnectionError) as exc:
        log.error("Failed to upload %s: %s", file_path, exc)
        return None


def attach_file_to_vector_store(
    client: OpenAI,
    vector_store_id: str,
    file_id: str,
    poll_timeout_s: float,
) -> bool:
    """Attach an uploaded file to a Vector Store, waiting for completion."""
    try:
        vf = client.vector_stores.files.create(
            vector_store_id=vector_store_id, file_id=file_id
        )
        deadline = time.monotonic() + poll_timeout_s
        while vf.status in ("in_progress", "queued"):
            if time.monotonic() > deadline:
                log.warning("Timed out waiting for file %s to attach", file_id)
                return False
            time.sleep(POLL_INTERVAL_S)
            vf = client.vector_stores.files.retrieve(
                vector_store_id=vector_store_id, file_id=file_id
            )

        if vf.status == "completed":
            log.info(
                "File %s attached and processed (%d bytes)",
                file_id,
                vf.usage_bytes,
            )
            return True

        log.error("File %s failed with status '%s'", file_id, vf.status)
        return False
    except (APIError, APIConnectionError) as exc:
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
            fc.total,
            fc.completed,
            fc.in_progress,
            fc.failed,
            vs.usage_bytes,
        )
    except (APIError, APIConnectionError) as exc:
        log.warning("Could not retrieve vector store summary: %s", exc)


def remove_stale_articles(
    removed_slugs: list[str],
    prev_state: dict[str, ArticleState],
    cfg,
) -> int:
    """Delete vector-store files for articles removed from Zendesk."""
    if not removed_slugs:
        return 0

    client = OpenAI(api_key=cfg.openai_api_key)
    vector_store_id = _verify_vector_store(client, cfg.openai_vector_store_id)
    removed_count = 0

    for slug in removed_slugs:
        previous = prev_state.get(slug)
        if not previous or not previous.openai_file_id:
            log.info("No OpenAI file tracked for removed article %s", slug)
            continue

        _delete_openai_file(client, vector_store_id, previous.openai_file_id)
        removed_count += 1
        log.info("Removed stale article %s (file_id=%s)", slug, previous.openai_file_id)

    return removed_count


def sync_articles(
    articles: list[Article],
    cfg,
    prev_state: dict[str, ArticleState] | None = None,
) -> SyncResult:
    """Upload Markdown files to OpenAI and attach them to the configured Vector Store."""
    if not articles:
        return SyncResult()

    prev_state = prev_state or {}
    client = OpenAI(api_key=cfg.openai_api_key)
    vector_store_id = _verify_vector_store(client, cfg.openai_vector_store_id)

    succeeded: dict[str, str] = {}
    failed = 0

    for article in articles:
        filepath = os.path.join(cfg.data_dir, f"{article.slug}.md")

        if not os.path.exists(filepath):
            log.warning("File not found (deleted after scrape?): %s", filepath)
            failed += 1
            continue

        previous = prev_state.get(article.slug)
        if previous and previous.openai_file_id:
            _delete_openai_file(client, vector_store_id, previous.openai_file_id)

        file_id = upload_file(client, filepath)
        if file_id is None:
            failed += 1
            continue

        ok = attach_file_to_vector_store(
            client,
            vector_store_id,
            file_id,
            cfg.poll_timeout_s,
        )
        if ok:
            succeeded[article.slug] = file_id
        else:
            _delete_openai_file(client, vector_store_id, file_id)
            failed += 1

    _log_vector_store_summary(client, vector_store_id)

    log.info(
        "Sync complete — total: %d, succeeded: %d, failed: %d, vector_store: %s",
        len(articles),
        len(succeeded),
        failed,
        vector_store_id,
    )

    return SyncResult(succeeded=succeeded, failed=failed)
