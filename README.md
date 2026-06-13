# OptiBot Mini-Clone

A daily scheduled scraper-uploader that ingests articles from [support.optisigns.com](https://support.optisigns.com) (Zendesk Help Center), converts them to clean Markdown, and syncs new/updated articles to an OpenAI Vector Store for use with a custom GPT Assistant.

## Quick Start

```bash
# 1. Clone and install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.sample .env
# Edit .env: set OPENAI_API_KEY and OPENAI_VECTOR_STORE_ID

# 3. Run once (scrape → delta → upload)
python main.py
```

## How It Works

```
Zendesk API ──▶ Scraper ──▶ data/articles/*.md ──▶ Delta Detection ──▶ OpenAI Vector Store
                      (399 articles)           (SHA256 hashing)     (new/updated only)
```

1. **Scrape** — Fetches all non-draft articles from the Zendesk Help Center API (paginated). Converts HTML to clean Markdown via `BeautifulSoup` + `markdownify`. Strips nav, ads, and extraneous elements. Saves each article as `data/articles/<slug>.md` with YAML frontmatter.

2. **Delta Detection** — Computes SHA256 of each article's Markdown content and compares against saved `state.json`. Only new or changed articles proceed to upload.

3. **Upload** — Uploads new/updated Markdown files to OpenAI via the Files API, then attaches them to the configured Vector Store. Polls for processing completion and logs file/chunk counts.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_VECTOR_STORE_ID` | Yes | — | Target Vector Store ID |
| `ZENDESK_BASE_URL` | No | `https://support.optisigns.com` | Zendesk Help Center base URL |
| `DATA_DIR` | No | `data/articles` | Directory for Markdown files |
| `STATE_FILE_PATH` | No | `state.json` | Delta state persistence file |

## Docker

```bash
docker build -t optibot-mini .
docker run --rm \
  -e OPENAI_API_KEY=sk-... \
  -e OPENAI_VECTOR_STORE_ID=vs_... \
  optibot-mini
```

The container runs once and exits 0 on success.

## DigitalOcean Deployment

1. Create a **DigitalOcean App Platform** resource.
2. Select **GitHub** as the source and point to this repository.
3. Set **Type** to **Background Worker** with command `python main.py`.
4. Configure **Environment Variables**:
   - `OPENAI_API_KEY`
   - `OPENAI_VECTOR_STORE_ID`
5. Set **Schedule** to daily (e.g., `0 6 * * *`).
6. Deploy and monitor logs at your DO App Platform dashboard.

### Deployment Proof

References from a successful scheduled run on App Platform (`sea-turtle-app`, cron `0 */4 * * *`):

- [Job invocation — SUCCESS status](images/DO-job-status-1.png)
- [Runtime logs — scrape → upload → sync complete](images/DO-job-status-2.png)
- [Vector Store — uploaded articles (OpenAI dashboard)](images/OpenAI-vector-store.png)
- [Full job log export](logs/DO-job-log.log)

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

- [Playground answer — "How do I add a YouTube video?"](images/OpenAI-playground-ans.png)

## Project Structure

```
├── main.py              # Entry point (scrape → delta → upload)
├── Dockerfile           # Multi-stage Docker build
├── requirements.txt     # Python dependencies
├── .env.sample          # Environment variable template
├── src/
│   ├── config.py        # Typed config from environment
│   ├── types.py         # Article, ArticleState, DeltaResult
│   ├── scraper.py       # Zendesk API client + HTML→Markdown
│   ├── state.py         # Delta detection via SHA256
│   └── uploader.py      # OpenAI Vector Store upload
├── data/articles/       # Generated Markdown files (gitignored)
└── state.json           # Delta state (gitignored)
```
