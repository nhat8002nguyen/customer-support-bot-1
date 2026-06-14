# OptiBot — Production-Grade Evolution

This document outlines how the current **Approach A** (scheduled ephemeral job with externalized state) would evolve into a production-grade system serving large numbers of users efficiently.

---

## Current Architecture (Approach A — as implemented)

```
Zendesk API  ──▶  Scraper  ──▶  Delta Detection  ──▶  OpenAI Upload
                    │                  │                    │
                    ▼                  ▼                    ▼
            data/articles/*.md   optibot/state.json   OpenAI Vector Store
            (ephemeral, local)   (DO Spaces or local)   (managed by OpenAI)
                                        │
                                        ▼
                              optibot/job.log
                              (DO Spaces or local)
```

**What “stateless” means today**

| Layer | Stateless? | Notes |
|-------|------------|-------|
| **Compute** | Yes | DO App Platform scheduled job: container starts, runs `python main.py`, exits. No long-lived process. |
| **Delta state** | No | SHA256 hashes and OpenAI file IDs persist in `optibot/state.json` via `STATE_BACKEND=spaces` (production) or local file (dev). |
| **Job logs** | No | Latest run log is replaced in `optibot/job.log` via `JOB_LOG_BACKEND=spaces` (production). |
| **Article Markdown** | Ephemeral | Written to `data/articles/` inside the container; not uploaded to Spaces today. |

So the system is **not fully stateless** — it is an **ephemeral worker with externalized operational state** in DO Spaces. That fixes the original “state lost on restart” problem without changing the cron + full-scrape shape.

**Already implemented (not future work)**

- Delta uploads only (`added` / `updated` / `skipped` via SHA256)
- State persistence to DO Spaces (`STATE_BACKEND=spaces`, `STATE_FILE_PATH=optibot/state.json`)
- Shared Spaces client (`src/spaces_client.py`) for state and job log uploads
- Per-run job log capture and full replace upload to Spaces (`JOB_LOG_BACKEND=spaces`, `JOB_LOG_PATH=optibot/job.log`)
- Zendesk page fetch retries; failed OpenAI uploads retried on next run; state updated only for successful uploads
- Removed Zendesk articles deleted from the vector store

**Remaining limitations at scale**

- **Full re-scrape every run** — O(n) Zendesk API work even when nothing changed (delta only skips OpenAI upload, not scrape)
- **No concurrent-run coordination** — two overlapping scheduled jobs could race on Spaces `put_object` for state/log (last writer wins)
- **No durable scrape artifact store** — Markdown lives on ephemeral container disk, not S3/Spaces
- **No queue or DLQ** — mid-batch OpenAI rate limits leave failed items for the next cron, with no dead-letter inspection
- **No per-article lifecycle DB** — no audit trail, dashboards, or alerting beyond the latest `job.log` blob

---

## Target Architecture (Event-Driven)

```
                         ┌──────────────────┐
                         │  Zendesk Webhook  │  (or periodic poll with If-Modified-Since)
                         └────────┬─────────┘
                                  │ POST article update
                                  ▼
                         ┌──────────────────┐
                         │   SQS Queue      │  (at-least-once delivery)
                         │  (or RabbitMQ)   │
                         └────────┬─────────┘
                                  │ dequeue
                          ┌───────▼────────┐
                          │  Scraper Worker  │  (auto-scaling, 1–20 instances)
                          │  (AWS Lambda /   │
                          │   DO Worker)     │
                          └───────┬────────┘
                                  │ writes Markdown
                                  ▼
                         ┌──────────────────┐
                         │   S3 / DO Spaces  │  (immutable object store)
                         └────────┬─────────┘
                                  │ S3 event notification
                                  ▼
                         ┌──────────────────┐
                         │   Upload Worker   │  (auto-scaling, rate-limited)
                         │  (AWS Lambda /   │
                         │   DO Worker)     │
                         └───────┬────────┘
                                  │ OpenAI API (throttled)
                                  ▼
                         ┌──────────────────┐
                         │  PostgreSQL       │  (article state machine)
                         │  (managed DB)     │
                         └──────────────────┘
```

### Component Breakdown

| Component | Production Choice | Why |
|-----------|-----------------|-----|
| **Trigger** | Zendesk webhook + SQS | Zero work when nothing changes. Webhook pushes only updated article IDs. |
| **Scraper** | AWS Lambda / DO Functions | Stateless compute, auto-scaling. Scrapes only the article that changed. |
| **Object Store** | S3 / DO Spaces | Cheaper than DB blobs. Immutable versioned objects. Easy to audit/replay. *(State + job log already use Spaces; article Markdown not yet.)* |
| **Uploader** | Lambda + SQS (separate queue) | Decouples scrape speed from OpenAI rate limits. Uploader pulls from queue at controlled pace. |
| **Database** | PostgreSQL (RDS / DO Managed DB) | Full audit trail: every article's state machine (`pending → scraped → uploaded → failed`). Enables dashboards, alerting. *(Replaces JSON blob in Spaces for operational queries.)* |
| **Dead-Letter Queue** | SQS DLQ | Failed uploads go to DLQ for manual inspection / retry, never silently dropped. |

### Key Production Concerns Addressed

#### 1. Cost / Resource Efficiency
- **Webhook-driven** = zero compute when no articles change (vs. O(n) re-scrape every cron tick)
- **Auto-scaling workers** = pay only for what you use during bursts (e.g., bulk import of 399 articles)
- **Object storage** for Markdown is ~$0.02/GB/month vs. DB storage

#### 2. Reliability
- **SQS at-least-once delivery** — no article update goes unprocessed
- **Dead-letter queue** — failed uploads captured for manual retry
- **Exponential backoff** for OpenAI 429 responses (rate-limit handling)

#### 3. Scalability
- **Scraper workers** scale independently from **uploader workers**
- 1 article change or 1000 — same architecture, just different queue depth
- Workers remain stateless; durable state lives in DB + object store (same pattern as today's Spaces-backed JSON, but queryable and concurrency-safe)

#### 4. Observability
- **PostgreSQL audit trail**: `article_id`, `version`, `status`, `error_message`, `timestamps`
- **CloudWatch / DO Metrics**: queue depth, worker count, error rates
- **Alerting**: PagerDuty/Slack on DLQ non-empty or upload failure rate > threshold
- *(Today: latest run log in `optibot/job.log` — useful for sharing, not structured metrics.)*

#### 5. OpenAI Rate-Limit Handling
- **Separate upload queue** decouples scrape speed from upload speed
- Uploader pulls at a configurable rate: e.g., max 5 files/minute
- Batch uploads where possible (OpenAI supports batch file creation)

---

## Migration Path (Current → Production)

Steps already completed are marked ✓.

1. ✓ **Externalize delta state** — `state.json` in DO Spaces (`STATE_BACKEND=spaces`).
2. ✓ **Share run logs** — `job.log` full replace in DO Spaces (`JOB_LOG_BACKEND=spaces`).
3. **Add database** — PostgreSQL for article state machine and audit trail; dual-write from Spaces JSON during transition.
4. **Persist article Markdown to object store** — Write `data/articles/*.md` to Spaces/S3 (not only state + log).
5. **Add webhook receiver** — Small endpoint that accepts Zendesk webhook pushes and enqueues article IDs.
6. **Add SQS queue** — Replace direct function calls with queue-based dispatch.
7. **Split scraper from uploader** — Two separate deployable units with independent scaling.
8. **Remove full cron scrape** — Webhook-only + periodic reconciliation (e.g., weekly full-scan as safety net).

---

## Alternative: Multi-Vector-Store Strategy

For enterprise customers who need isolated knowledge bases (per region, per product line):

```
Zendesk Webhook
    │
    ├──▶ Scraper  ──▶ S3 (bucket A) ──▶ OpenAI VS A
    │
    └──▶ Scraper  ──▶ S3 (bucket B) ──▶ OpenAI VS B
```

A simple routing table in PostgreSQL maps article section/category → Vector Store ID.

---

## Challenges & Risks

| Challenge | Mitigation |
|-----------|------------|
| Zendesk API rate limits (500 req/min) | Queue-based throttling + token bucket |
| OpenAI file upload rate limits | Configurable upload pace, batch retries |
| Stale articles (Zendesk article deleted) | Weekly full reconciliation sync *(delete-on-remove already implemented)* |
| Cost of embedding 399+ articles repeatedly | Delta upload only *(already implemented)* |
| Overlapping cron runs racing on Spaces state | DB with optimistic locking, or SQS single-consumer pattern |
