"""Periodic availability checks of the registered targets."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

import httpx2

from site_monitor import db
from site_monitor.ssrf import UnsafeURLError, check_url_is_public
from site_monitor.state import State, TargetState, next_state

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    target_id: int
    url: str
    up: bool
    status_code: int | None  # None when no HTTP response was received
    response_time: float | None  # seconds until the response headers arrived
    error: str | None
    checked_at: float  # Unix timestamp


@dataclass
class MonitorData:
    """Everything the checker produces, read by /metrics. Lives in memory only."""

    results: dict[int, CheckResult] = field(default_factory=dict)  # latest per target
    states: dict[int, TargetState] = field(default_factory=dict)  # per target
    checks_total: dict[str, int] = field(
        default_factory=lambda: {"success": 0, "failure": 0}
    )
    state_changes_total: dict[str, int] = field(
        default_factory=lambda: {"up": 0, "down": 0}
    )


@dataclass
class CheckerSettings:
    interval: float
    timeout: float
    concurrency: int
    failure_threshold: int


def load_settings() -> CheckerSettings:
    # Invalid values raise at startup: better to fail fast than to run misconfigured.
    settings = CheckerSettings(
        interval=float(os.environ.get("CHECK_INTERVAL_SECONDS", "30")),
        timeout=float(os.environ.get("CHECK_TIMEOUT_SECONDS", "10")),
        concurrency=int(os.environ.get("CHECK_CONCURRENCY", "10")),
        failure_threshold=int(os.environ.get("FAILURE_THRESHOLD", "3")),
    )
    # e.g. CHECK_CONCURRENCY=0 would make the checker wait forever on its semaphore.
    if settings.interval <= 0 or settings.timeout <= 0:
        raise ValueError("CHECK_INTERVAL_SECONDS and CHECK_TIMEOUT_SECONDS must be > 0")
    if settings.concurrency < 1 or settings.failure_threshold < 1:
        raise ValueError("CHECK_CONCURRENCY and FAILURE_THRESHOLD must be >= 1")
    return settings


async def check_target(
    client: httpx2.AsyncClient, target_id: int, url: str
) -> CheckResult:
    def result(up, status_code=None, response_time=None, error=None):
        return CheckResult(
            target_id, url, up, status_code, response_time, error, time.time()
        )

    # Re-check SSRF before every request: DNS may have changed since registration.
    # getaddrinfo blocks, so it runs in a thread to keep the event loop free.
    try:
        await asyncio.to_thread(check_url_is_public, url)
    except UnsafeURLError as exc:
        return result(up=False, error=f"blocked: {exc}")

    start = time.perf_counter()
    try:
        # stream() returns as soon as the headers arrive and the body is never
        # downloaded, so a huge page cannot exhaust our memory.
        async with client.stream("GET", url) as response:
            elapsed = time.perf_counter() - start
            status = response.status_code
    except httpx2.HTTPError as exc:
        # Timeouts, DNS failures, refused connections, TLS errors...
        return result(up=False, error=type(exc).__name__)

    # Redirects are not followed (SSRF), so a 3xx still means the server answered.
    return result(up=status < 400, status_code=status, response_time=elapsed)


async def run_checks(
    client: httpx2.AsyncClient, targets: list[dict], concurrency: int
) -> list[CheckResult]:
    # The semaphore caps how many requests are in flight at the same time.
    semaphore = asyncio.Semaphore(concurrency)

    async def limited(target):
        async with semaphore:
            return await check_target(client, target["id"], target["url"])

    return await asyncio.gather(*(limited(t) for t in targets))


def _load_targets() -> list[dict]:
    conn = db.connect(db.get_database_path())
    try:
        return db.list_targets(conn)
    finally:
        conn.close()


def update_states(
    states: dict[int, TargetState], checked: list[CheckResult], threshold: int
) -> list[State]:
    """Apply one round of results to the states, in place, and log state changes.

    Returns the new state of every target that changed (UP or DOWN).
    """
    new_states = {}
    changes = []
    for r in checked:
        previous = states.get(r.target_id, TargetState())
        new, changed = next_state(previous, r.up, threshold)
        new_states[r.target_id] = new
        if changed:
            changes.append(new.state)
        if changed and new.state == State.DOWN:
            logger.warning(
                "Target %d %s is DOWN after %d consecutive failures (last: %s)",
                r.target_id,
                r.url,
                new.consecutive_failures,
                r.error or f"HTTP {r.status_code}",
            )
        elif changed:
            logger.info("Target %d %s RECOVERED (UP)", r.target_id, r.url)
    # Replace everything, so deleted targets disappear from the states.
    states.clear()
    states.update(new_states)
    return changes


def record_round(data: MonitorData, checked: list[CheckResult], threshold: int) -> None:
    """Store one round of results in `data`: latest results, states and counters."""
    # Replace everything, so deleted targets disappear from the results.
    data.results.clear()
    data.results.update({r.target_id: r for r in checked})
    for r in checked:
        data.checks_total["success" if r.up else "failure"] += 1
    for new_state in update_states(data.states, checked, threshold):
        data.state_changes_total[new_state.value] += 1


async def checker_loop(settings: CheckerSettings, data: MonitorData) -> None:
    """Check every target, record the results, sleep, repeat. Runs until cancelled."""
    timeout = httpx2.Timeout(settings.timeout)
    async with httpx2.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            try:
                targets = await asyncio.to_thread(_load_targets)
                checked = await run_checks(client, targets, settings.concurrency)
                record_round(data, checked, settings.failure_threshold)
                down = sum(s.state == State.DOWN for s in data.states.values())
                logger.info("Checked %d targets, %d DOWN", len(checked), down)
            except Exception:
                # One failed round (e.g. database locked) must not kill the loop forever.
                # Cancellation is not an Exception, so shutdown still works.
                logger.exception("Check round failed")
            await asyncio.sleep(settings.interval)
