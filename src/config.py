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
        default_factory=lambda: os.environ.get("STATE_FILE_PATH", "state.json")
    )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_vector_store_id:
            missing.append("OPENAI_VECTOR_STORE_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"See .env.sample for reference."
            )


def load_config() -> Config:
    cfg = Config()
    cfg.validate()
    return cfg
