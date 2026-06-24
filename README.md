# OptiBot Mini-Clone

A daily scheduled scraper-uploader that ingests articles from [support.optisigns.com](https://support.optisigns.com) (Zendesk Help Center), converts them to clean Markdown, and syncs new/updated articles to an OpenAI Vector Store for use with a custom GPT Assistant.

## Quick Start

```bash
# 1. Clone and install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configure environment
cp .env.sample .env
# Edit .env: set OPENAI_API_KEY and OPENAI_VECTOR_STORE_ID

# 3. Run once (scrape → delta → upload)
python main.py
```

## How It Works

```
Zendesk API ──▶ Scraper ──▶ data/articles/*.md ──▶ Delta Detection ──▶ OpenAI Vector Store
                 (up to 399)              (SHA256 hashing)     (new/updated only)
```

1. **Scrape** — Fetches all non-draft articles from the Zendesk Help Center API (paginated, with retries). Converts HTML to clean Markdown via `BeautifulSoup` + `markdownify`. Strips nav, ads, and extraneous elements. Saves each article as `data/articles/<slug>.md` with YAML frontmatter.

2. **Delta Detection** — Computes SHA256 of each article's full file content (frontmatter + body) and compares against saved `state.json`. Only new or changed articles proceed to upload. Articles removed from Zendesk are deleted from the vector store.

3. **Upload** — Uploads new/updated Markdown files to OpenAI via the Files API, replaces previous file IDs on update, then attaches them to the configured Vector Store. Polls for processing completion and logs file/chunk counts. Failed uploads are retried on the next run; state is only updated for successful uploads.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_VECTOR_STORE_ID` | Yes | — | Target Vector Store ID |
| `ZENDESK_BASE_URL` | No | `https://support.optisigns.com` | Zendesk Help Center base URL |
| `DATA_DIR` | No | `data/articles` | Directory for Markdown files |
| `STATE_FILE_PATH` | No | `optibot/state.json` | Local path or Spaces object key |
| `STATE_BACKEND` | No | `local` | `local` (filesystem) or `spaces` (DO Spaces) |
| `SPACES_ACCESS_KEY_ID` | When `spaces` | — | Spaces access key |
| `SPACES_SECRET_ACCESS_KEY` | When `spaces` | — | Spaces secret key |
| `SPACES_BUCKET` | When `spaces` | — | Bucket name |
| `SPACES_REGION` | No | `sgp1` | DO region (`sgp1` Singapore recommended for SE Asia) |
| `JOB_LOG_BACKEND` | No | `off` | `off`, `local`, or `spaces` — where to store latest run log |
| `JOB_LOG_PATH` | No | `optibot/job.log` | Local file path or Spaces object key |
| `MAX_PAGES` | No | `0` (unlimited) | Limit Zendesk pages to fetch (useful for dev) |
| `MIN_ARTICLES` | No | `0` (no check) | Minimum scraped articles required for success |
| `FETCH_RETRIES` | No | `3` | Retries per Zendesk API page on transient errors |
| `POLL_TIMEOUT_S` | No | `180` | Seconds to wait for vector-store file processing |

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

## Docker

```bash
docker build -t optibot-mini .
docker run --rm \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_VECTOR_STORE_ID=vs_... \
  optibot-mini
```

The container runs once and exits **0 on full success**, **1 on config/scrape/upload failures**.

> **State persistence on DigitalOcean:** App Platform has no persistent volumes — container filesystem is wiped each run. For production, set `STATE_BACKEND=spaces` and configure Spaces env vars so `state.json` survives across scheduled job runs. Local dev uses `STATE_BACKEND=local` (default).

## DigitalOcean Deployment

1. Create a **DigitalOcean App Platform** resource.
2. Select **GitHub** as the source and point to this repository.
3. Set **Type** to **Scheduled Job** (or Background Worker) with command `python main.py`.
4. Configure **Environment Variables**:
   - `OPENAI_API_KEY`
   - `OPENAI_VECTOR_STORE_ID`
   - `STATE_BACKEND=spaces`
   - `STATE_FILE_PATH=optibot/state.json`
   - `SPACES_ACCESS_KEY_ID`
   - `SPACES_SECRET_ACCESS_KEY`
   - `SPACES_BUCKET`
   - `SPACES_REGION=sgp1`
   - `JOB_LOG_BACKEND=spaces`
   - `JOB_LOG_PATH=optibot/job.log`
   - `MAX_PAGES=0`
5. Set **Schedule** to daily (e.g., `0 6 * * *`).
6. Deploy and monitor logs at your DO App Platform dashboard.

### DigitalOcean Spaces setup

1. Create a **Space** in **Singapore (`sgp1`)** — closest DO region to Southeast Asia.
2. Generate **Spaces access keys** (API → Spaces Keys).
3. Use the same `sgp1` region for your App Platform app when possible (lower latency).
4. First run uploads all articles (`added: N`); second run should log `skipped: N`.

### Sharing job logs

Each run **replaces** `job.log` in your Space (never appends). To share with others:

1. In the DO Spaces console, open `optibot/job.log` from the latest run.
2. Or enable **CDN** / **public file listing** on the Space and share the object URL.
3. Local smoke test:
   ```bash
   JOB_LOG_BACKEND=spaces JOB_LOG_PATH=optibot/job-test.log python main.py
   ```

### Deployment Proof

References from a successful scheduled run on App Platform (`sea-turtle-app`, cron `0 2 * * *`):

- [Job invocation — SUCCESS status](images/DO-job-status-1.png)
- [Runtime logs — scrape → upload → sync complete](images/DO-job-status-2.png)
- [Vector Store — uploaded articles (OpenAI dashboard)](images/OpenAI-vector-store.png)
- [Latest job log (DO Spaces)](https://sgp1.digitaloceanspaces.com/optibot-mini/optibot/job.log?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=DO00ZXNKEBU4RZKC4DB9%2F20260622%2Fsgp1%2Fs3%2Faws4_request&X-Amz-Date=20260622T043957Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=3d32b0b42439b6f69506337a2630789cbc68dd79756e40b7cedd752962023b36)
- [Latest state file (DO Spaces)](https://sgp1.digitaloceanspaces.com/optibot-mini/optibot/state.json?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=DO00ZXNKEBU4RZKC4DB9%2F20260624%2Fsgp1%2Fs3%2Faws4_request&X-Amz-Date=20260624T084548Z&X-Amz-Expires=604800&X-Amz-SignedHeaders=host&X-Amz-Signature=0878542e2780d48882d490bcdc8b1ddf283f8c96805de9077193b9f6ccfd3aa4)

## OpenAI Assistant Setup

1. Go to [OpenAI Playground](https://platform.openai.com/playground/assistants).
2. Create a new Assistant with the following **System Prompt** (verbatim):

   > You are OptiBot, the customer-support bot for OptiSigns.com.
   > - Tone: helpful, factual, concise.
   > - Only answer using the uploaded docs.
   > - Max 5 bullet points; else link to the doc.
   > - Cite up to 3 "Article URL:" lines per reply.

3. Attach the Vector Store (the one configured via `OPENAI_VECTOR_STORE_ID`).
4. Test with: **"How do I add a YouTube video?"**

### Proof

- [Playground answer — "How do I add a YouTube video?"](images/OpenAI-playground-output.png)

## Project Structure

```
├── main.py              # Entry point (scrape → delta → upload)
├── Dockerfile           # Multi-stage Docker build
├── requirements.txt     # Production Python dependencies
├── requirements-dev.txt # Dev/test dependencies (includes pytest)
├── .env.sample          # Environment variable template
├── src/
│   ├── config.py        # Typed config from environment
│   ├── types.py         # Article, ArticleState, DeltaResult
│   ├── scraper.py       # Zendesk API client + HTML→Markdown
│   ├── state.py         # Delta detection via SHA256
│   ├── state_backend.py # Local + DO Spaces state persistence
│   ├── spaces_client.py # Shared DO Spaces S3 client helpers
│   ├── job_log.py       # Per-run log capture and upload
│   └── uploader.py      # OpenAI Vector Store upload
├── data/articles/       # Generated Markdown files (gitignored)
└── optibot/             # State + job log (gitignored when local)
    ├── state.json       # Delta state
    └── job.log          # Latest run log (when JOB_LOG_BACKEND=local)
```
