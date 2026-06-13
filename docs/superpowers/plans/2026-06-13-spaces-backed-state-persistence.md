# Spaces-Backed State Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `state.json` to DigitalOcean Spaces (S3-compatible) so scheduled App Platform jobs retain delta hashes across ephemeral container runs.

**Architecture:** Introduce a small `StateBackend` protocol with two implementations: `LocalStateBackend` (current file behavior, default for local dev) and `SpacesStateBackend` (boto3 S3 client pointed at `https://{region}.digitaloceanspaces.com`). `load_state(cfg)` and `persist_state(cfg, state)` delegate to the backend selected by `STATE_BACKEND`. No changes to delta detection logic.

**Tech Stack:** Python 3.12, boto3, existing `Config` dataclass, pytest + `unittest.mock` (no moto — keep dev deps light).

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/state_backend.py` | `StateBackend` protocol, `LocalStateBackend`, `SpacesStateBackend`, `get_state_backend(cfg)` |
| `src/config.py` | New Spaces env vars + validation when `STATE_BACKEND=spaces` |
| `src/state.py` | Serialization helpers; `load_state`/`persist_state` take `Config` instead of path |
| `main.py` | Pass `cfg` to `load_state`/`persist_state` |
| `tests/test_state_backend.py` | Unit tests for both backends (local tmp dir + mocked boto3) |
| `tests/test_state.py` | Update round-trip test to use `FakeConfig` |
| `requirements.txt` | Add `boto3` |
| `.env.sample` | Document Spaces vars |
| `README.md` | Replace volume guidance with Spaces setup for DO |

---

### Task 1: Add boto3 dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add boto3 pin**

```text
boto3>=1.34,<2
```

Append to `requirements.txt` after `python-dotenv`.

- [ ] **Step 2: Verify install**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements.txt && python -c 'import boto3; print(boto3.__version__)'"`

Expected: version string printed, exit 0.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add boto3 for Spaces state persistence"
```

---

### Task 2: Local state backend (extract from state.py)

**Files:**
- Create: `src/state_backend.py`
- Create: `tests/test_state_backend.py`
- Modify: `src/state.py` (import serialization only — backend comes in Task 4)

- [ ] **Step 1: Write failing test for LocalStateBackend**

Create `tests/test_state_backend.py`:

```python
"""Tests for state persistence backends."""

import json
from dataclasses import dataclass

from src.state_backend import LocalStateBackend
from src.types import ArticleState


@dataclass(frozen=True)
class FakeConfig:
    state_file_path: str = "state.json"


def _sample_state() -> dict[str, ArticleState]:
    return {
        "article-a": ArticleState(
            slug="article-a",
            sha256="abc123",
            last_modified="2026-01-01T00:00:00Z",
            article_id=42,
            openai_file_id="file-1",
        )
    }


class TestLocalStateBackend:
    def test_load_returns_empty_when_missing(self, tmp_path):
        cfg = FakeConfig(state_file_path=str(tmp_path / "missing.json"))
        backend = LocalStateBackend(cfg)
        assert backend.load() == {}

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "state.json"
        cfg = FakeConfig(state_file_path=str(path))
        backend = LocalStateBackend(cfg)
        state = _sample_state()

        backend.save(state)
        loaded = backend.load()

        assert loaded["article-a"].openai_file_id == "file-1"
        assert loaded["article-a"].article_id == 42
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["article-a"]["openai_file_id"] == "file-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_state_backend.py::TestLocalStateBackend -v"`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.state_backend'`

- [ ] **Step 3: Implement LocalStateBackend**

Create `src/state_backend.py`:

```python
"""State persistence backends — local filesystem and DO Spaces."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Protocol

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_state_backend.py::TestLocalStateBackend -v"`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/state_backend.py tests/test_state_backend.py
git commit -m "feat: add LocalStateBackend for state persistence"
```

---

### Task 3: Spaces state backend

**Files:**
- Modify: `src/state_backend.py`
- Modify: `tests/test_state_backend.py`

- [ ] **Step 1: Write failing tests for SpacesStateBackend**

Append to `tests/test_state_backend.py`:

```python
from unittest.mock import MagicMock, patch

from src.state_backend import SpacesStateBackend


@dataclass(frozen=True)
class SpacesFakeConfig:
    state_file_path: str = "optibot/state.json"
    spaces_access_key_id: str = "KEY"
    spaces_secret_access_key: str = "SECRET"
    spaces_bucket: str = "my-bucket"
    spaces_region: str = "nyc3"


class TestSpacesStateBackend:
    @patch("src.state_backend.boto3.client")
    def test_load_returns_empty_on_missing_key(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )

        backend = SpacesStateBackend(SpacesFakeConfig())
        assert backend.load() == {}

        mock_client.get_object.assert_called_once_with(
            Bucket="my-bucket",
            Key="optibot/state.json",
        )

    @patch("src.state_backend.boto3.client")
    def test_save_and_load_round_trip(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        stored: dict[str, bytes] = {}

        def fake_put_object(**kwargs):
            stored["body"] = kwargs["Body"]

        mock_client.put_object.side_effect = fake_put_object
        mock_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: stored["body"])
        }

        backend = SpacesStateBackend(SpacesFakeConfig())
        state = _sample_state()
        backend.save(state)
        loaded = backend.load()

        assert loaded["article-a"].openai_file_id == "file-1"
        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "my-bucket"
        assert call_kwargs["Key"] == "optibot/state.json"
        assert call_kwargs["ContentType"] == "application/json"

    @patch("src.state_backend.boto3.client")
    def test_uses_correct_endpoint(self, mock_boto_client):
        SpacesStateBackend(SpacesFakeConfig(spaces_region="sfo3"))
        mock_boto_client.assert_called_once_with(
            "s3",
            endpoint_url="https://sfo3.digitaloceanspaces.com",
            aws_access_key_id="KEY",
            aws_secret_access_key="SECRET",
            region_name="sfo3",
        )
```

Add import at top of test file: `from botocore.exceptions import ClientError`

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_state_backend.py::TestSpacesStateBackend -v"`

Expected: FAIL — `SpacesStateBackend` not defined

- [ ] **Step 3: Implement SpacesStateBackend and factory**

Append to `src/state_backend.py`:

```python
import boto3


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
```

Move `import boto3` to top of file with other imports (single import block).

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_state_backend.py -v"`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/state_backend.py tests/test_state_backend.py
git commit -m "feat: add SpacesStateBackend for DO Spaces persistence"
```

---

### Task 4: Config fields and validation

**Files:**
- Modify: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config.py`:

```python
"""Tests for configuration loading."""

import os
from unittest.mock import patch

import pytest

from src.config import Config, load_config


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_config.py -v"`

Expected: FAIL — `state_backend` attribute missing

- [ ] **Step 3: Add config fields**

Modify `src/config.py` — add fields after `state_file_path`:

```python
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
        default_factory=lambda: os.environ.get("SPACES_REGION", "nyc3")
    )
```

Extend `validate()`:

```python
        if self.state_backend not in ("local", "spaces"):
            raise RuntimeError(
                f"Invalid STATE_BACKEND '{self.state_backend}'. "
                "Must be 'local' or 'spaces'."
            )
        if self.state_backend == "spaces":
            for var_name, value in [
                ("SPACES_ACCESS_KEY_ID", self.spaces_access_key_id),
                ("SPACES_SECRET_ACCESS_KEY", self.spaces_secret_access_key),
                ("SPACES_BUCKET", self.spaces_bucket),
            ]:
                if not value:
                    missing.append(var_name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_config.py -v"`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add Spaces config vars and validation"
```

---

### Task 5: Wire state.py and main.py to backends

**Files:**
- Modify: `src/state.py`
- Modify: `main.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write failing test for cfg-based load/persist**

Replace `test_persist_and_load_state_round_trip` in `tests/test_state.py`:

```python
    def test_persist_and_load_state_round_trip(self, tmp_path):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class FakeConfig:
            state_backend: str = "local"
            state_file_path: str = str(tmp_path / "state.json")

        cfg = FakeConfig()
        state = _make_state("a", "hello", file_id="file-1", article_id=42)
        persist_state(cfg, state)
        loaded = load_state(cfg)
        assert loaded["a"].openai_file_id == "file-1"
```

Update `load_state` / `persist_state` signatures first (Step 3) before running.

- [ ] **Step 2: Refactor state.py**

Replace `load_state` and `persist_state` in `src/state.py`:

```python
from src.state_backend import get_state_backend, serialize_state


def load_state(cfg) -> dict[str, ArticleState]:
    return get_state_backend(cfg).load()


def persist_state(cfg, state: dict[str, ArticleState]) -> None:
    get_state_backend(cfg).save(state)
```

Remove duplicate `_serialize_state`, `load_state(path)`, `persist_state(path)` implementations and unused imports (`tempfile`, `os` if no longer needed). Keep `deserialize` logic only in `state_backend.py`.

Remove `_serialize_state` from `state.py` entirely — serialization lives in `state_backend.py`.

- [ ] **Step 3: Update main.py**

Change lines 58 and 87:

```python
    prev_state = load_state(cfg)
    ...
    persist_state(cfg, next_state)
```

- [ ] **Step 4: Run full test suite**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q"`

Expected: all tests pass (count will be ~34 with new config tests)

- [ ] **Step 5: Commit**

```bash
git add src/state.py main.py tests/test_state.py
git commit -m "feat: route state load/save through configurable backend"
```

---

### Task 6: Documentation and env sample

**Files:**
- Modify: `.env.sample`
- Modify: `README.md`

- [ ] **Step 1: Update .env.sample**

Append after `STATE_FILE_PATH`:

```bash
# State backend: "local" (filesystem) or "spaces" (DO Spaces)
STATE_BACKEND=local

# DigitalOcean Spaces (required when STATE_BACKEND=spaces)
# STATE_FILE_PATH doubles as the object key, e.g. optibot/state.json
SPACES_ACCESS_KEY_ID=
SPACES_SECRET_ACCESS_KEY=
SPACES_BUCKET=
SPACES_REGION=nyc3
```

- [ ] **Step 2: Update README.md**

**Configuration table** — add rows:

| `STATE_BACKEND` | No | `local` | `local` or `spaces` |
| `SPACES_ACCESS_KEY_ID` | When spaces | — | Spaces access key |
| `SPACES_SECRET_ACCESS_KEY` | When spaces | — | Spaces secret key |
| `SPACES_BUCKET` | When spaces | — | Bucket name |
| `SPACES_REGION` | No | `nyc3` | DO region (`nyc3`, `sfo3`, etc.) |

**Replace** the "State persistence" note and DO step 6 (volume mount) with:

```markdown
> **State persistence on DigitalOcean:** App Platform has no persistent volumes. Set `STATE_BACKEND=spaces` and configure Spaces env vars so `state.json` survives across scheduled job runs.

### DigitalOcean Spaces setup

1. Create a **Space** in the same region as your app (e.g. `nyc3`).
2. Generate **Spaces access keys** (API → Spaces Keys).
3. On your App Platform worker/job, set environment variables:
   - `STATE_BACKEND=spaces`
   - `STATE_FILE_PATH=optibot/state.json`
   - `SPACES_ACCESS_KEY_ID`
   - `SPACES_SECRET_ACCESS_KEY`
   - `SPACES_BUCKET`
   - `SPACES_REGION=nyc3`
4. First run uploads all articles; second run should log `skipped: N`.
```

- [ ] **Step 3: Commit**

```bash
git add .env.sample README.md
git commit -m "docs: document Spaces-backed state for DO App Platform"
```

---

### Task 7: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q"`

Expected: all tests pass, 0 failures

- [ ] **Step 2: Verify Docker production build**

Run: `docker build -t optibot-mini .`

Expected: build succeeds

- [ ] **Step 3: Verify local mode still works**

Run: `docker run --rm -e OPENAI_API_KEY=test -e OPENAI_VECTOR_STORE_ID=vs_test optibot-mini -c "from src.config import Config; c=Config(); print(c.state_backend)"`

Expected: prints `local`

- [ ] **Step 4: Manual Spaces smoke test (optional, requires real credentials)**

```bash
export STATE_BACKEND=spaces
export STATE_FILE_PATH=optibot/state.json
export SPACES_ACCESS_KEY_ID=...
export SPACES_SECRET_ACCESS_KEY=...
export SPACES_BUCKET=...
export SPACES_REGION=nyc3
python -c "
from src.config import Config
from src.state import load_state, persist_state
from src.types import ArticleState
cfg = Config(); cfg.validate()
persist_state(cfg, {'test': ArticleState(slug='test', sha256='x', last_modified='now')})
print('loaded', load_state(cfg))
"
```

Expected: `loaded` dict with `test` key

---

## Self-Review Checklist

| Requirement | Task |
|---|---|
| Local dev unchanged (default `local`) | Task 2, 5 |
| Spaces backend via boto3 | Task 3 |
| Config validation for spaces | Task 4 |
| `main.py` uses new API | Task 5 |
| Tests with mocked boto3 | Task 3 |
| README + `.env.sample` | Task 6 |
| No volume references | Task 6 |

---

## DO Deployment Checklist (post-implementation)

1. Create Space + access keys in DO console
2. Set `STATE_BACKEND=spaces` on the scheduled job
3. Set `STATE_FILE_PATH=optibot/state.json`
4. Set `MAX_PAGES=0` for full scrape
5. Deploy; confirm first run `added: N`, second run `skipped: N`
6. Optionally run `reset_vector_store.py` + `delete_all_files.py` once before first Spaces-backed run to clear duplicates
