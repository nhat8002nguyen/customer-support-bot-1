"""Tests for configuration loading."""

import os
from unittest.mock import patch

import pytest

from src.config import Config


class TestConfigValidation:
    def test_spaces_backend_requires_spaces_vars(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_VECTOR_STORE_ID": "vs_test",
                "STATE_BACKEND": "spaces",
                "SPACES_BUCKET": "",
                "SPACES_ACCESS_KEY_ID": "",
                "SPACES_SECRET_ACCESS_KEY": "",
            },
            clear=False,
        ):
            cfg = Config()
            with pytest.raises(RuntimeError, match="SPACES_BUCKET"):
                cfg.validate()

    def test_local_backend_default(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_VECTOR_STORE_ID": "vs_test",
            },
            clear=False,
        ):
            cfg = Config()
            cfg.validate()
            assert cfg.state_backend == "local"

    def test_spaces_region_defaults_to_sgp1(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.spaces_region == "sgp1"

    def test_job_log_spaces_requires_spaces_vars(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_VECTOR_STORE_ID": "vs_test",
                "JOB_LOG_BACKEND": "spaces",
                "SPACES_BUCKET": "",
            },
            clear=False,
        ):
            cfg = Config()
            with pytest.raises(RuntimeError, match="SPACES_BUCKET"):
                cfg.validate()

    def test_job_log_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.job_log_backend == "off"
            assert cfg.job_log_path == "optibot/job.log"

    def test_state_file_path_defaults_to_optibot(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config()
            assert cfg.state_file_path == "optibot/state.json"
