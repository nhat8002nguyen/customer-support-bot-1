"""Remove all files from the configured OpenAI Vector Store.

Use this to wipe the vector store clean before a full re-sync.
Run from the project root (or inside the Docker container) with:
    python scripts/reset_vector_store.py

Requires OPENAI_API_KEY and OPENAI_VECTOR_STORE_ID in the environment.
"""

from __future__ import annotations

import logging
import os
import sys

# Ensure the project root (parent of scripts/) is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

from src.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("reset")


def main() -> int:
    try:
        cfg = load_config()
    except RuntimeError as exc:
        log.error(exc)
        return 1

    client = OpenAI(api_key=cfg.openai_api_key)
    vs_id = cfg.openai_vector_store_id

    if not vs_id:
        log.error("OPENAI_VECTOR_STORE_ID is not set — nothing to clean.")
        return 1

    # Verify the vector store exists
    try:
        vs = client.vector_stores.retrieve(vector_store_id=vs_id)
        log.info("Vector store %s found (%d files before reset)", vs_id, vs.file_counts.total)
    except Exception as exc:
        log.error("Vector store %s not accessible: %s", vs_id, exc)
        return 1

    # List all files in the vector store
    try:
        vs_files = list(client.vector_stores.files.list(vector_store_id=vs_id))
    except Exception as exc:
        log.error("Failed to list files in vector store: %s", exc)
        return 1

    if not vs_files:
        log.info("Vector store is already empty — nothing to delete.")
        return 0

    log.info("Found %d file(s) in vector store — deleting ...", len(vs_files))

    deleted_count = 0
    for vf in vs_files:
        try:
            client.vector_stores.files.delete(vector_store_id=vs_id, file_id=vf.id)
            log.info("Deleted %s from vector store", vf.id)
            deleted_count += 1
        except Exception as exc:
            log.error("Failed to delete %s: %s", vf.id, exc)

    log.info("Done — removed %d / %d files from vector store %s", deleted_count, len(vs_files), vs_id)
    return 0 if deleted_count == len(vs_files) else 1


if __name__ == "__main__":
    sys.exit(main())
