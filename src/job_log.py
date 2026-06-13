"""Capture and persist per-run job logs for sharing."""

from __future__ import annotations

import logging
from io import StringIO

from src.spaces_client import put_text_object

log = logging.getLogger("job_log")


class LogBufferHandler(logging.Handler):
    """Accumulate formatted log lines in memory."""

    def __init__(self) -> None:
        super().__init__()
        self._buffer = StringIO()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)

    def getvalue(self) -> str:
        return self._buffer.getvalue()


def attach_log_buffer() -> LogBufferHandler:
    """Attach an in-memory handler to the root logger."""
    handler = LogBufferHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    return handler


def persist_job_log(cfg, text: str) -> None:
    """Write job log — always full replace, never append."""
    if cfg.job_log_backend == "off":
        return

    if cfg.job_log_backend == "local":
        with open(cfg.job_log_path, "w", encoding="utf-8") as f:
            f.write(text)
        log.info("Job log saved locally — %s", cfg.job_log_path)
        return

    if cfg.job_log_backend == "spaces":
        put_text_object(cfg, cfg.job_log_path, text, "text/plain")
        return

    log.warning("Unknown JOB_LOG_BACKEND '%s' — skipping job log upload", cfg.job_log_backend)
