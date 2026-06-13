# Job Log Upload to DO Spaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the full stdout-equivalent log output of each scheduled job run and overwrite a shared `job.log` object in DigitalOcean Spaces so stakeholders can review the latest run without DO console access.

**Architecture:** Attach a `logging.Handler` backed by an in-memory buffer at process start. On exit (success or failure), if `JOB_LOG_BACKEND=spaces`, `put_object` the buffer to `JOB_LOG_PATH` (default `optibot/job.log`) — full replace, never append. Extract a shared Spaces client helper from `state_backend.py` to avoid duplicating boto3 setup. `state.json` and `job.log` are separate keys in the same bucket.

**Tech Stack:** Python 3.12 stdlib `logging`, existing `boto3` Spaces integration, pytest + `unittest.mock`.

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/spaces_client.py` | Shared `make_spaces_client(cfg)` and `put_text_object(cfg, key, body, content_type)` |
| `src/job_log.py` | `LogBufferHandler`, `attach_log_buffer()`, `persist_job_log(cfg, text)` |
| `src/state_backend.py` | Refactor `SpacesStateBackend` to use `spaces_client` |
| `src/config.py` | Add `job_log_backend`, `job_log_path`; validate when `spaces` |
| `main.py` | Wrap job in try/finally; capture logs from start; upload on exit |
| `tests/test_job_log.py` | Buffer capture, local overwrite, mocked Spaces upload |
| `tests/test_main.py` | Assert `persist_job_log` called in finally |
| `.env.sample` / `README.md` | Document new env vars and sharing note |

---

### Task 1: Shared Spaces client helper

**Files:**
- Create: `src/spaces_client.py`
- Modify: `src/state_backend.py`
- Create: `tests/test_spaces_client.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_spaces_client.py`:

```python
"""Tests for shared DigitalOcean Spaces client helpers."""

from unittest.mock import MagicMock, patch

from src.spaces_client import make_spaces_client, put_text_object


@dataclass(frozen=True)
class SpacesCfg:
    spaces_access_key_id: str = "KEY"
    spaces_secret_access_key: str = "SECRET"
    spaces_bucket: str = "my-bucket"
    spaces_region: str = "sgp1"


# Add: from dataclasses import dataclass at top


@patch("src.spaces_client.boto3.client")
def test_make_spaces_client_uses_sgp1_endpoint(mock_boto_client):
    make_spaces_client(SpacesCfg())
    mock_boto_client.assert_called_once_with(
        "s3",
        endpoint_url="https://sgp1.digitaloceanspaces.com",
        aws_access_key_id="KEY",
        aws_secret_access_key="SECRET",
        region_name="sgp1",
    )


@patch("src.spaces_client.make_spaces_client")
def test_put_text_object_replaces_entire_object(mock_make_client):
    mock_client = MagicMock()
    mock_make_client.return_value = mock_client
    cfg = SpacesCfg()

    put_text_object(cfg, "optibot/job.log", "line1\nline2\n", "text/plain")

    mock_client.put_object.assert_called_once_with(
        Bucket="my-bucket",
        Key="optibot/job.log",
        Body=b"line1\nline2\n",
        ContentType="text/plain",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_spaces_client.py -v"`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.spaces_client'`

- [ ] **Step 3: Implement spaces_client.py**

Create `src/spaces_client.py`:

```python
"""Shared DigitalOcean Spaces (S3-compatible) helpers."""

from __future__ import annotations

import logging

import boto3

log = logging.getLogger("spaces_client")


def make_spaces_client(cfg):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg.spaces_region}.digitaloceanspaces.com",
        aws_access_key_id=cfg.spaces_access_key_id,
        aws_secret_access_key=cfg.spaces_secret_access_key,
        region_name=cfg.spaces_region,
    )


def put_text_object(cfg, key: str, body: str, content_type: str = "text/plain") -> None:
    client = make_spaces_client(cfg)
    client.put_object(
        Bucket=cfg.spaces_bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )
    log.info("Uploaded to Spaces — s3://%s/%s (%d bytes)", cfg.spaces_bucket, key, len(body))
```

- [ ] **Step 4: Refactor SpacesStateBackend to use helper**

In `src/state_backend.py`, replace inline `boto3.client(...)` in `SpacesStateBackend.__init__` with `self._client = make_spaces_client(cfg)`.

Replace `save()` body upload with:

```python
from src.spaces_client import make_spaces_client, put_text_object

# in save():
put_text_object(
    self._cfg,
    self._key,
    json.dumps(serialize_state(state), indent=2),
    "application/json",
)
```

Store `self._cfg = cfg` in `__init__` and remove direct `put_object` call. Keep `get_object` on `self._client` for `load()`.

- [ ] **Step 5: Run tests**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_spaces_client.py tests/test_state_backend.py -v"`

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/spaces_client.py src/state_backend.py tests/test_spaces_client.py
git commit -m "refactor: extract shared Spaces client helper"
```

---

### Task 2: Job log capture and persistence

**Files:**
- Create: `src/job_log.py`
- Create: `tests/test_job_log.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_log.py`:

```python
"""Tests for job log capture and persistence."""

import logging
from dataclasses import dataclass
from io import StringIO
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_job_log.py -v"`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.job_log'`

- [ ] **Step 3: Implement job_log.py**

Create `src/job_log.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_job_log.py -v"`

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/job_log.py tests/test_job_log.py
git commit -m "feat: add job log capture and Spaces upload"
```

---

### Task 3: Config fields for job log

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_config.py::TestConfigValidation::test_job_log_defaults -v"`

Expected: FAIL — `job_log_backend` missing

- [ ] **Step 3: Add config fields and validation**

In `src/config.py`, after `spaces_region`:

```python
    job_log_backend: str = field(
        default_factory=lambda: os.environ.get("JOB_LOG_BACKEND", "off").lower()
    )
    job_log_path: str = field(
        default_factory=lambda: os.environ.get("JOB_LOG_PATH", "optibot/job.log")
    )
```

Extend `validate()` — after `state_backend` checks, add:

```python
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
```

Remove the duplicate `if self.state_backend == "spaces"` block (merged into `needs_spaces`).

- [ ] **Step 4: Run config tests**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/test_config.py -v"`

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add JOB_LOG_BACKEND and JOB_LOG_PATH config"
```

---

### Task 4: Wire main.py with try/finally upload

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_main.py`:

```python
@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
@patch("main.persist_state")
@patch("main.sync_articles")
@patch("main.detect_deltas")
@patch("main.find_removed_slugs")
@patch("main.load_state")
@patch("main.run_scraper")
@patch("main.load_config")
def test_main_uploads_job_log_on_exit(
    mock_load_config,
    mock_run_scraper,
    mock_load_state,
    mock_find_removed,
    mock_detect_deltas,
    mock_sync_articles,
    mock_persist_state,
    mock_attach_buffer,
    mock_persist_job_log,
):
    mock_buffer = MagicMock()
    mock_buffer.getvalue.return_value = "log lines"
    mock_attach_buffer.return_value = mock_buffer

    mock_cfg = MagicMock(
        min_articles=0,
        job_log_backend="spaces",
    )
    mock_load_config.return_value = mock_cfg
    mock_run_scraper.return_value = [_article("a")]
    mock_load_state.return_value = {}
    mock_find_removed.return_value = []
    mock_detect_deltas.return_value = DeltaResult(added=[_article("a")])
    mock_sync_articles.return_value = SyncResult(succeeded={"a": "file-1"}, failed=0)

    assert main_module.main() == 0
    mock_persist_job_log.assert_called_once_with(mock_cfg, "log lines")
```

- [ ] **Step 2: Refactor main.py**

Replace `main.py` with:

```python
"""OptiBot Mini-Clone — entry point.

Orchestrates: scrape → delta detection → OpenAI Vector Store upload.
"""

from __future__ import annotations

import logging
import sys

from src.config import load_config
from src.job_log import attach_log_buffer, persist_job_log
from src.scraper import ScrapeIncompleteError, run_scraper
from src.state import (
    build_next_state,
    detect_deltas,
    find_removed_slugs,
    load_state,
    persist_state,
)
from src.types import SyncResult
from src.uploader import remove_stale_articles, sync_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("main")


def run_job(cfg) -> int:
    try:
        articles = run_scraper(cfg)
    except ScrapeIncompleteError as exc:
        log.error("Scrape incomplete: %s", exc)
        return 1

    if not articles:
        log.warning("No articles scraped; nothing to upload.")
        return 0

    log.info("Scraped %d articles", len(articles))

    if cfg.min_articles > 0 and len(articles) < cfg.min_articles:
        log.error(
            "Scraped %d articles, below minimum of %d",
            len(articles),
            cfg.min_articles,
        )
        return 1

    prev_state = load_state(cfg)

    removed_slugs = find_removed_slugs(articles, prev_state)
    if removed_slugs:
        log.info("Detected %d removed article(s)", len(removed_slugs))
        remove_stale_articles(removed_slugs, prev_state, cfg)

    result = detect_deltas(articles, prev_state)

    log.info(
        "Delta — added: %d, updated: %d, skipped: %d",
        len(result.added),
        len(result.updated),
        len(result.skipped),
    )

    to_upload = result.added + result.updated
    sync_result = SyncResult()
    if to_upload:
        sync_result = sync_articles(to_upload, cfg, prev_state)
        log.info(
            "Upload — succeeded: %d, failed: %d",
            len(sync_result.succeeded),
            sync_result.failed,
        )
    else:
        log.info("Nothing to upload — all articles up to date.")

    next_state = build_next_state(articles, prev_state, result, sync_result.succeeded)
    persist_state(cfg, next_state)
    log.info("State persisted — done.")

    if sync_result.failed > 0:
        return 1

    return 0


def main() -> int:
    log_buffer = attach_log_buffer()
    cfg = None
    exit_code = 1

    try:
        cfg = load_config()
        exit_code = run_job(cfg)
    except RuntimeError as exc:
        log.error(exc)

    if cfg is not None:
        persist_job_log(cfg, log_buffer.getvalue())

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Update existing test_main mocks**

Existing tests patch `main.load_config` and call `main()` — they will now also call `attach_log_buffer` and possibly `persist_job_log`. Add `@patch("main.attach_log_buffer")` and `@patch("main.persist_job_log")` to existing tests, or patch them once in a `autouse` fixture. Minimal fix: add to each existing test:

```python
@patch("main.persist_job_log")
@patch("main.attach_log_buffer")
```

with `mock_attach.return_value = MagicMock(getvalue=MagicMock(return_value=""))`.

- [ ] **Step 4: Run full test suite**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q"`

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: upload job log to Spaces on every run"
```

---

### Task 5: Documentation and env sample

**Files:**
- Modify: `.env.sample`
- Modify: `README.md`

- [ ] **Step 1: Update .env.sample**

Append after `SPACES_REGION=sgp1`:

```bash
# Job log sharing (off = disabled, local = file, spaces = DO Spaces)
JOB_LOG_BACKEND=off
JOB_LOG_PATH=optibot/job.log
```

- [ ] **Step 2: Update README.md**

Add to configuration table:

| `JOB_LOG_BACKEND` | No | `off` | `off`, `local`, or `spaces` — where to store latest run log |
| `JOB_LOG_PATH` | No | `optibot/job.log` | Local file path or Spaces object key |

Add to DO deployment env vars list:

```
   - `JOB_LOG_BACKEND=spaces`
   - `JOB_LOG_PATH=optibot/job.log`
```

Add subsection **Sharing job logs**:

```markdown
### Sharing job logs

Each run **replaces** `job.log` in your Space (never appends). To share with others:

1. In the DO Spaces console, open `optibot/job.log` from the latest run.
2. Or enable **CDN** / **public file listing** on the Space and share the object URL.
3. Local smoke test:
   ```bash
   JOB_LOG_BACKEND=spaces JOB_LOG_PATH=optibot/job-test.log python main.py
   ```
```

Remove any implication that `job.log` and `state.json` are the same file.

- [ ] **Step 3: Commit**

```bash
git add .env.sample README.md
git commit -m "docs: document job log upload to Spaces"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Run full test suite**

Run: `docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim bash -c "pip install -q -r requirements-dev.txt && python -m pytest tests/ -q"`

Expected: 0 failures

- [ ] **Step 2: Local job log smoke test**

```bash
cd /Users/nhatnguyen/Workspaces/interview-test/optisigns
source venv/bin/activate
set -a && source .env && set +a
export JOB_LOG_BACKEND=local
export JOB_LOG_PATH=/tmp/optibot-job-test.log
python -c "
import logging
from src.config import Config
from src.job_log import attach_log_buffer, persist_job_log
logging.basicConfig(level=logging.INFO)
buf = attach_log_buffer()
logging.getLogger('smoke').info('test line')
cfg = Config()
persist_job_log(cfg, buf.getvalue())
print(open('/tmp/optibot-job-test.log').read())
"
```

Expected: output contains `test line`

- [ ] **Step 3: Spaces job log smoke test (with real credentials)**

```bash
export JOB_LOG_BACKEND=spaces
export JOB_LOG_PATH=optibot/job-test.log
python main.py   # or short-circuit test with python -c similar to state smoke test
```

Verify `optibot/job-test.log` appears in DO Spaces console with latest run content only.

- [ ] **Step 4: Docker build**

Run: `docker build -t optibot-mini .`

Expected: success

---

## Self-Review Checklist

| Requirement | Task |
|---|---|
| Logs captured every run | Task 4 (`attach_log_buffer` at start) |
| Stored in DO Spaces | Task 2 (`persist_job_log` spaces branch) |
| Separate from `state.json` | `JOB_LOG_PATH` vs `STATE_FILE_PATH` |
| Replace not append | Task 2 (`open("w")` + `put_object` full body) |
| Shared Spaces client (DRY) | Task 1 |
| Default `sgp1` region | Reuses existing `SPACES_REGION` |
| Local dev default off | Task 3 (`JOB_LOG_BACKEND=off`) |
| Tests | Tasks 1–4 |
| Docs | Task 5 |

---

## DO Production Env (complete set)

```env
STATE_BACKEND=spaces
STATE_FILE_PATH=optibot/state.json
JOB_LOG_BACKEND=spaces
JOB_LOG_PATH=optibot/job.log
SPACES_ACCESS_KEY_ID=...
SPACES_SECRET_ACCESS_KEY=...
SPACES_BUCKET=...
SPACES_REGION=sgp1
MAX_PAGES=0
```

After two runs, Spaces bucket contains:
- `optibot/state.json` — delta hashes (updated incrementally)
- `optibot/job.log` — **latest run only** (full replace each time)
