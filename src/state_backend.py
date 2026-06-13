"""State persistence backends — local filesystem and DO Spaces."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from src.types import ArticleState

log = logging.getLogger("state_backend")


def deserialize_state(raw: dict[str, dict[str, Any]]) -> dict[str, ArticleState]:
    return {
        k: ArticleState(
            slug=v.get("slug", k),
            sha256=v["sha256"],
            last_modified=v["last_modified"],
            article_id=v.get("article_id", 0),
            openai_file_id=v.get("openai_file_id", ""),
        )
        for k, v in raw.items()
    }


def serialize_state(state: dict[str, ArticleState]) -> dict[str, dict[str, Any]]:
    return {
        k: {
            "slug": v.slug,
            "sha256": v.sha256,
            "last_modified": v.last_modified,
            "article_id": v.article_id,
            "openai_file_id": v.openai_file_id,
        }
        for k, v in state.items()
    }


class StateBackend(Protocol):
    def load(self) -> dict[str, ArticleState]: ...
    def save(self, state: dict[str, ArticleState]) -> None: ...


class LocalStateBackend:
    def __init__(self, cfg) -> None:
        self._path = cfg.state_file_path

    def load(self) -> dict[str, ArticleState]:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, encoding="utf-8") as f:
            raw: dict[str, dict[str, Any]] = json.load(f)
        return deserialize_state(raw)

    def save(self, state: dict[str, ArticleState]) -> None:
        serializable = serialize_state(state)
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


class SpacesStateBackend:
    def __init__(self, cfg) -> None:
        self._bucket = cfg.spaces_bucket
        self._key = cfg.state_file_path
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{cfg.spaces_region}.digitaloceanspaces.com",
            aws_access_key_id=cfg.spaces_access_key_id,
            aws_secret_access_key=cfg.spaces_secret_access_key,
            region_name=cfg.spaces_region,
        )

    def load(self) -> dict[str, ArticleState]:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key)
            raw = json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return {}
            raise
        return deserialize_state(raw)

    def save(self, state: dict[str, ArticleState]) -> None:
        body = json.dumps(serialize_state(state), indent=2).encode("utf-8")
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key,
            Body=body,
            ContentType="application/json",
        )
        log.info("State saved to Spaces — s3://%s/%s", self._bucket, self._key)


def get_state_backend(cfg) -> StateBackend:
    if cfg.state_backend == "spaces":
        return SpacesStateBackend(cfg)
    return LocalStateBackend(cfg)
