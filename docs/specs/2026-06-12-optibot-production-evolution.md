# OptiBot — Production-Grade Evolution

This document outlines how the current **Approach A** (stateless daily cron job) would evolve into a production-grade system serving large numbers of users efficiently.

---

## Current Architecture (Approach A — as implemented)

```
Zendesk API  ──▶  Scraper  ──▶  Delta Detection  ──▶  OpenAI Upload
                    │                  │
                    ▼                  ▼
            data/articles/*.md    state.json
```

**Limitations at scale:**
- Full re-scrape every run — O(n) work even when nothing changed
- `state.json` is local to the container — lost on restart, no multi-instance coordination
- No retry mechanism — if OpenAI API rate-limits mid-batch, progress is lost
- No observability into individual article lifecycle

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
| **Scraper** | AWS Lambda / DO Functions | Stateless, auto-scaling, sub-second cold starts. Scrapes only the article that changed. |
| **Object Store** | S3 / DO Spaces | Cheaper than DB blobs. Immutable versioned objects. Easy to audit/replay. |
| **Uploader** | Lambda + SQS (separate queue) | Decouples scrape speed from OpenAI rate limits. Uploader pulls from queue at controlled pace. |
| **Database** | PostgreSQL (RDS / DO Managed DB) | Full audit trail: every article's state machine (`pending → scraped → uploaded → failed`). Enables dashboards, alerting. |
| **Dead-Letter Queue** | SQS DLQ | Failed uploads go to DLQ for manual inspection / retry, never silently dropped. |

### Key Production Concerns Addressed

#### 1. Cost / Resource Efficiency
- **Webhook-driven** = zero compute when no articles change (vs. O(n) re-scrape daily)
- **Auto-scaling workers** = pay only for what you use during bursts (e.g., bulk import of 399 articles)
- **Object storage** for Markdown is ~$0.02/GB/month vs. DB storage

#### 2. Reliability
- **SQS at-least-once delivery** — no article update goes unprocessed
- **Dead-letter queue** — failed uploads captured for manual retry
- **Exponential backoff** for OpenAI 429 responses (rate-limit handling)

#### 3. Scalability
- **Scraper workers** scale independently from **uploader workers**
- 1 article change or 1000 — same architecture, just different queue depth
- No shared state: each worker is stateless, making horizontal scaling trivial

#### 4. Observability
- **PostgreSQL audit trail**: `article_id`, `version`, `status`, `error_message`, `timestamps`
- **CloudWatch / DO Metrics**: queue depth, worker count, error rates
- **Alerting**: PagerDuty/Slack on DLQ non-empty or upload failure rate > threshold

#### 5. OpenAI Rate-Limit Handling
- **Separate upload queue** decouples scrape speed from upload speed
- Uploader pulls at a configurable rate: e.g., max 5 files/minute
- Batch uploads where possible (OpenAI supports batch file creation)

---

## Migration Path (Approach A → Production)

1. **Add database** — Replace `state.json` with PostgreSQL table. Dual-write during transition.
2. **Add webhook receiver** — Small endpoint that accepts Zendesk webhook pushes and enqueues article IDs.
3. **Add SQS queue** — Replace direct function calls with queue-based dispatch.
4. **Split scraper from uploader** — Two separate deployable units with independent scaling.
5. **Add object storage** — Write Markdown to S3/Spaces instead of local filesystem.
6. **Remove cron job** — Switch from daily full-scrape to webhook-only + periodic reconciliation (e.g., weekly full-scan as safety net).

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
| Stale articles (Zendesk article deleted) | Weekly full reconciliation sync |
| Cost of embedding 399+ articles repeatedly | Only upload deltas (already implemented) |
