"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )
    openai_vector_store_id: str = field(
        default_factory=lambda: os.environ.get("OPENAI_VECTOR_STORE_ID", "")
    )
    zendesk_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ZENDESK_BASE_URL", "https://support.optisigns.com"
        )
    )
    data_dir: str = field(
        default_factory=lambda: os.environ.get("DATA_DIR", "data/articles")
    )
    state_file_path: str = field(
        default_factory=lambda: os.environ.get("STATE_FILE_PATH", "optibot/state.json")
    )
    state_backend: str = field(
        default_factory=lambda: os.environ.get("STATE_BACKEND", "local").lower()
    )
    spaces_access_key_id: str = field(
        default_factory=lambda: os.environ.get("SPACES_ACCESS_KEY_ID", "")
    )
    spaces_secret_access_key: str = field(
        default_factory=lambda: os.environ.get("SPACES_SECRET_ACCESS_KEY", "")
    )
    spaces_bucket: str = field(
        default_factory=lambda: os.environ.get("SPACES_BUCKET", "")
    )
    spaces_region: str = field(
        default_factory=lambda: os.environ.get("SPACES_REGION", "sgp1")
    )
    job_log_backend: str = field(
        default_factory=lambda: os.environ.get("JOB_LOG_BACKEND", "off").lower()
    )
    job_log_path: str = field(
        default_factory=lambda: os.environ.get("JOB_LOG_PATH", "optibot/job.log")
    )
    max_pages: int = field(
        default_factory=lambda: int(os.environ.get("MAX_PAGES", "0"))
    )
    min_articles: int = field(
        default_factory=lambda: int(os.environ.get("MIN_ARTICLES", "0"))
    )
    fetch_retries: int = field(
        default_factory=lambda: int(os.environ.get("FETCH_RETRIES", "3"))
    )
    poll_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("POLL_TIMEOUT_S", "180"))
    )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_vector_store_id:
            missing.append("OPENAI_VECTOR_STORE_ID")
        if self.state_backend not in ("local", "spaces"):
            raise RuntimeError(
                f"Invalid STATE_BACKEND '{self.state_backend}'. "
                "Must be 'local' or 'spaces'."
            )
        if self.job_log_backend not in ("off", "local", "spaces"):
            raise RuntimeError(
                f"Invalid JOB_LOG_BACKEND '{self.job_log_backend}'. "
                "Must be 'off', 'local', or 'spaces'."
            )
        needs_spaces = self.state_backend == "spaces" or self.job_log_backend == "spaces"
        if needs_spaces:
            for var_name, value in [
                ("SPACES_ACCESS_KEY_ID", self.spaces_access_key_id),
                ("SPACES_SECRET_ACCESS_KEY", self.spaces_secret_access_key),
                ("SPACES_BUCKET", self.spaces_bucket),
            ]:
                if not value:
                    missing.append(var_name)
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"See .env.sample for reference."
            )


def load_config() -> Config:
    cfg = Config()
    cfg.validate()
    return cfg
