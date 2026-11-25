# 007 — Checker: httpx2, async, background task in the FastAPI lifespan

- Status: accepted
- Date: 2026-11-25

## Context

Every N seconds the service must request each registered target and record whether it is up, its HTTP status and its response time. Many targets can be slow at the same time, the SSRF check must run again before each request (decision 006), and everything runs in one container on a small VPS.

While preparing this step, PyPI showed that `httpx` has had no release since December 2024 (still "Beta"), while `httpx2` (Pydantic organization) is actively released and marked "Production/Stable". The project already used `httpx2` for tests (decision 002). The full history between the two projects was not verified.

## Options considered

HTTP client:

| Option | Pros | Cons |
|---|---|---|
| **httpx2** | Sync and async; timeouts on by default; no automatic redirects; already in the project | Less name recognition than requests |
| requests | Best known | Sync only; no default timeout; follows redirects by default |
| aiohttp | Fast, mature async | Async only; more verbose; new dependency |

Concurrency model: **async (`asyncio`)** vs sync with a thread pool.

Scheduling:

| Option | Pros | Cons |
|---|---|---|
| **Background task in FastAPI `lifespan`** | No dependency; one process, one container | API and checker share a process; running 2 API replicas would double the checks |
| Separate worker container | Isolation; scales separately | Two containers sharing one SQLite file; more setup |
| APScheduler / Celery + Redis | Cron syntax, retries, distribution | New dependencies (and a broker for Celery); overkill |

## Decision

- `httpx2` moves from a dev dependency to a runtime dependency. One shared `AsyncClient` with `follow_redirects=False` and a configurable timeout.
- `checker_loop` runs as an `asyncio` task created in the FastAPI `lifespan`, and is cancelled cleanly on shutdown.
- Each round: load targets, check them concurrently (`asyncio.gather`), limited by an `asyncio.Semaphore`, then sleep for the interval.
- **Per check:**
  - re-run `check_url_is_public` in a thread (`asyncio.to_thread`, because DNS resolution blocks);
  - open the response as a **stream** and never read the body (we only need the status, and a huge page cannot exhaust memory);
  - measure time-to-headers with `time.perf_counter()`.
- **"Up"** means an HTTP response with status < 400. 3xx counts as up because redirects are not followed. Timeouts, network/TLS errors, 4xx, 5xx and SSRF-blocked URLs count as down for that check.
- Latest results are kept **in memory** (`app.state.results`), not in SQLite: Prometheus (step 9) will be the history store.
- A failed round (e.g. database locked) is logged and the loop continues. `CancelledError` is not an `Exception`, so shutdown still works.
- Settings come from `CHECK_INTERVAL_SECONDS` (30), `CHECK_TIMEOUT_SECONDS` (10) and `CHECK_CONCURRENCY` (10). Invalid values make startup fail (fail fast).
- Logging is configured with `logging.basicConfig` at INFO to stderr. Without it, uvicorn's setup dropped our INFO logs. httpx2's per-request logs are raised to WARNING to avoid one line per target per round.

## Consequences

- Total round time is roughly the slowest target (bounded by the timeout), not the sum of all targets.
- After a restart, results are empty until the first round completes (at most one interval).
- Only one API process may run (no `--workers > 1`, no replicas), or targets are checked several times. To scale the API, the checker would move to its own worker container.
- Tests use `httpx2.MockTransport` and the fake DNS, so the suite never touches the network. A real smoke test (python.org homepage up, a 404 page down) confirmed the behaviour end to end.

## I would choose differently if...

- the API needed several replicas: separate checker worker (one instance) and a shared database such as PostgreSQL;
- checks needed complex schedules per target (e.g. cron expressions): a scheduler library such as APScheduler.
