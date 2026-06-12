"""Delete all files from the OpenAI account (files storage, not Vector Store).

Use this to fully purge all uploaded files before a fresh re-sync.
Run from the project root (or inside the Docker container) with:
    python scripts/delete_all_files.py

Requires OPENAI_API_KEY in the environment.
"""

from __future__ import annotations

import logging
import os
import sys

from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("delete-files")


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY is not set.")
        return 1

    client = OpenAI(api_key=api_key)

    # List all files with "assistants" purpose (our uploads)
    try:
        all_files = list(client.files.list(purpose="assistants"))
    except Exception as exc:
        log.error("Failed to list files: %s", exc)
        return 1

    if not all_files:
        log.info("No files found — nothing to delete.")
        return 0

    log.info("Found %d file(s) to delete ...", len(all_files))

    deleted_count = 0
    for f in all_files:
        try:
            client.files.delete(file_id=f.id)
            log.info("Deleted %s (%s)", f.id, f.filename)
            deleted_count += 1
        except Exception as exc:
            log.error("Failed to delete %s: %s", f.id, exc)

    log.info("Done — deleted %d / %d files", deleted_count, len(all_files))
    return 0 if deleted_count == len(all_files) else 1


if __name__ == "__main__":
    sys.exit(main())
