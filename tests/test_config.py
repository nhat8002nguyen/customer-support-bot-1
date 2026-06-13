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
