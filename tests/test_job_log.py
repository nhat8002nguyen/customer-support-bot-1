"""Tests for job log capture and persistence."""

import logging
from dataclasses import dataclass
from unittest.mock import patch

from src.job_log import LogBufferHandler, attach_log_buffer, persist_job_log


@dataclass(frozen=True)
class LocalJobLogCfg:
    job_log_backend: str = "local"
    job_log_path: str = "job.log"


@dataclass(frozen=True)
class SpacesJobLogCfg:
    job_log_backend: str = "spaces"
    job_log_path: str = "optibot/job.log"
    spaces_access_key_id: str = "KEY"
    spaces_secret_access_key: str = "SECRET"
    spaces_bucket: str = "my-bucket"
    spaces_region: str = "sgp1"


class TestLogBufferHandler:
    def test_captures_log_records(self):
        handler = LogBufferHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger = logging.getLogger("test.capture")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("hello")
        logger.warning("world")

        assert "INFO hello" in handler.getvalue()
        assert "WARNING world" in handler.getvalue()


class TestAttachLogBuffer:
    def test_returns_handler_on_root_logger(self):
        handler = attach_log_buffer()
        root = logging.getLogger()
        assert handler in root.handlers


class TestPersistJobLog:
    def test_off_backend_is_noop(self):
        @dataclass(frozen=True)
        class OffCfg:
            job_log_backend: str = "off"
            job_log_path: str = "job.log"

        persist_job_log(OffCfg(), "should not write")

    def test_local_backend_overwrites_file(self, tmp_path):
        path = tmp_path / "job.log"
        path.write_text("old run\n", encoding="utf-8")
        cfg = LocalJobLogCfg(job_log_path=str(path))

        persist_job_log(cfg, "new run line 1\nnew run line 2\n")

        assert path.read_text(encoding="utf-8") == "new run line 1\nnew run line 2\n"

    @patch("src.job_log.put_text_object")
    def test_spaces_backend_replaces_object(self, mock_put):
        cfg = SpacesJobLogCfg()
        persist_job_log(cfg, "2026-06-13 run complete\n")

        mock_put.assert_called_once_with(
            cfg,
            "optibot/job.log",
            "2026-06-13 run complete\n",
            "text/plain",
        )
