# Phase 15E — Bulk Queue Reliability, Recovery & Production Worker Hardening

Phase 15E hardens the PostgreSQL bulk queue for long-running and large batches
without redesigning the queue or the verification pipeline. All processing still
goes through `BulkQueueWorker` / `QueueJobRepository`; the queue stays
PostgreSQL-backed with row-level `FOR UPDATE SKIP LOCKED` claiming and the unique
`document_id` job index.

## 1. Worker execution: separate from the HTTP request lifecycle

Two deployment modes, no queue redesign:

- **In-process (development, default).** `POST /applications/{id}/processing/start`
  and `POST /applications/{id}/processing/retry` return immediately and schedule
  a bounded in-process drain through FastAPI `BackgroundTasks` — the response is
  never blocked by processing.
- **Dedicated worker processes (production).** `python -m app.bulk_queue
  [--workers N]` runs `BulkQueueWorker.loop_forever()` in a separate process (or
  several). Workers poll the queue every `bulk_queue_poll_interval` seconds,
  claim jobs atomically, and recover crashed workers' jobs automatically. Set
  `BULK_QUEUE_BACKGROUND_DRAIN=false` to stop the API process from draining the
  queue inside request handling; the explicit ops endpoint
  `POST /queue/workers/drain` remains available either way.

## 2. Worker crash recovery

- Every `run_until_empty` iteration runs `recover_stale_processing` before
  claiming, so recovery needs no manual intervention.
- A PROCESSING job whose worker crashed is detected once its `started_at` (the
  liveness lease) is older than `bulk_queue_stale_after_seconds`.
- Recovered jobs return to `QUEUED` (attempt budget not exhausted) or `FAILED`
  (budget exhausted), per the existing retry policy; worker lease, `started_at`,
  `retry_at` are cleared and the document status is reset (`UPLOADED` /
  `FAILED`) so a document is never permanently stuck in `PROCESSING`.
- Crashed attempts deliberately do not consume the retry budget: a job whose
  worker keeps crashing is requeued again rather than silently dropped, so
  infrastructure failures never burn the document's retries. The attempt budget
  only applies to genuine processing failures.
- **Heartbeat.** While a job is being processed the worker refreshes `started_at`
  every `max(1, stale_after_seconds // 3)` seconds from a separate session, so a
  live but slow OCR run is never falsely declared stale and reprocessed.
- Completed jobs are never touched: recovery and claiming only select
  `QUEUED` / `RETRY_WAITING` / stale `PROCESSING` jobs.

## 3. Retry reliability

- Transient failures move a job to `RETRY_WAITING` and it is re-claimed
  automatically once `retry_at` passes.
- Backoff is exponential: retry `n` waits `bulk_queue_retry_backoff_seconds *
  2^(n-1)` (e.g. 30 s, 60 s, 120 s with the default base).
- `bulk_queue_max_attempts` caps the budget; exhaustion permanently fails the
  job (`FAILED`), stores `last_error`, and marks the document failed.
- Retrying a failed document (`retry_failed_for_application`) only resets
  existing FAILED job rows — no new rows, so no duplicate active jobs, and
  successful documents are never retried.

## 4. Concurrency

- `claim_next` uses `SELECT ... FOR UPDATE SKIP LOCKED` inside the transaction,
  so two workers — threads or OS processes — can never claim the same job.
- Verified by `test_multiple_worker_processes_claim_disjoint_jobs`, which runs
  three real OS processes against the same PostgreSQL queue and proves every
  document was claimed exactly once, and by the existing
  `test_two_workers_cannot_claim_same_job` (separate DB sessions).

## 5. Resource protection (configurable limits)

| Setting | Default | Protects |
| --- | --- | --- |
| `bulk_queue_workers` | 2 (max 16) | CPU, RAM, OCR/AI concurrency per drain |
| `bulk_queue_max_attempts` | 3 (max 10) | AI/API retry spend |
| `bulk_queue_poll_interval` | 1.0 s | idle DB chatter of dedicated workers |
| `bulk_queue_stale_after_seconds` | 900 s | recovery cadence |
| `database_pool_size` | 5 | DB connections / memory (engine pool) |
| `database_max_overflow` | 10 | DB connections under burst |

The combined database pool is validated at startup to be at least
`bulk_queue_workers + 2` so an in-process drain (worker claim sessions plus the
request session) can never exhaust connections.

OCR/extraction/business-rule logic is unchanged.

## 6. Large-batch benchmark (real PostgreSQL, 10 ms mock processor)

Controlled processor: 10 ms per document, no OCR or AI calls. Runs through the
real `finance_verification` database with `drain_queue()`.

| Docs | Workers | Time (s) | Docs/min | Avg queue wait (s) | Completed | Failed | Retries |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 1 | 0.4316 | 1390.20 | 0.2152 | 10 | 0 | 0 |
| 10 | 2 | 0.2403 | 2496.95 | 0.1131 | 10 | 0 | 0 |
| 10 | 3 | 0.2762 | 2172.08 | 0.1263 | 10 | 0 | 0 |
| 40 | 1 | 1.8719 | 1282.09 | 0.8930 | 40 | 0 | 0 |
| 40 | 2 | 1.1971 | 2004.91 | 0.7000 | 40 | 0 | 0 |
| 40 | 3 | 0.8841 | 2714.77 | 0.4338 | 40 | 0 | 0 |
| 80 | 1 | 3.5703 | 1344.41 | 1.7988 | 80 | 0 | 0 |
| 80 | 2 | 2.4631 | 1948.79 | 1.1501 | 80 | 0 | 0 |
| 80 | 3 | 2.3098 | 2078.10 | 1.2484 | 80 | 0 | 0 |
| 160 | 1 | 7.2973 | 1315.56 | 3.6775 | 160 | 0 | 0 |
| 160 | 2 | 4.0311 | 2381.46 | 2.0229 | 160 | 0 | 0 |
| 160 | 3 | 4.4214 | 2171.28 | 2.4352 | 160 | 0 | 0 |

Every batch completed with zero failures and zero retries; the 160-document runs
finished in ~4-7 s. Two workers beat one (≈2x), and three add little beyond two
at these sizes — the 10 ms mock workload is dominated by claim/commit overhead,
so worker scaling only pays off for real, slower OCR work.

### Stale-job crash-recovery benchmark

160 jobs force-claimed by simulated crashed workers (one-hour-old `started_at`):

| Stale jobs | Recovered | Recovery time (s) | Recovery rate (jobs/s) |
| ---: | ---: | ---: | ---: |
| 160 | 160 | 0.0543 | 2946.72 |

## 7. Verification

- `pytest -q`: **613 passed** (602 pre-existing + 11 new reliability tests).
- `alembic check`: **No new upgrade operations detected** (no schema change;
  the heartbeat reuses `started_at` as the liveness lease).

## 8. Remaining issues / notes

- Recovery is heartbeat-assisted but still timeout-based: a worker that is
  completely stuck (e.g. blocked native call) is recovered after
  `bulk_queue_stale_after_seconds`; the heartbeat makes false positives
  practically impossible for normally progressing runs.
- `bulk_queue_background_drain` defaults to true for convenience; production
  should set it to false and run dedicated `python -m app.bulk_queue`
  processes, otherwise every API worker process that receives a start/retry
  request also drains (safe — row locks prevent double processing — but
  wasteful).
- Database pool limits are per-process; scale them with the number of deployed
  worker processes. Within one process, each queue worker holds a claim session
  for the whole duration of a job, so pool sizing must account for
  `bulk_queue_workers` (enforced by the startup validation above).
- Benchmark throughput reflects queue mechanics only (10 ms mock documents);
  real OCR runs are far slower and will change scaling characteristics.
