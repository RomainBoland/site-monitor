"""Periodic availability checks of the registered targets."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass

import httpx2

from site_monitor import db
from site_monitor.ssrf import UnsafeURLError, check_url_is_public

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
class CheckerSettings:
    interval: float
    timeout: float
    concurrency: int


def load_settings() -> CheckerSettings:
    # Invalid values raise at startup: better to fail fast than to run misconfigured.
    return CheckerSettings(
        interval=float(os.environ.get("CHECK_INTERVAL_SECONDS", "30")),
        timeout=float(os.environ.get("CHECK_TIMEOUT_SECONDS", "10")),
        concurrency=int(os.environ.get("CHECK_CONCURRENCY", "10")),
    )


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


async def checker_loop(
    settings: CheckerSettings, results: dict[int, CheckResult]
) -> None:
    """Check every target, store the latest results, sleep, repeat. Runs until cancelled."""
    timeout = httpx2.Timeout(settings.timeout)
    async with httpx2.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            try:
                targets = await asyncio.to_thread(_load_targets)
                checked = await run_checks(client, targets, settings.concurrency)
                # Replace everything, so deleted targets disappear from the results.
                results.clear()
                results.update({r.target_id: r for r in checked})
                down = sum(not r.up for r in checked)
                logger.info("Checked %d targets, %d down", len(checked), down)
            except Exception:
                # One failed round (e.g. database locked) must not kill the loop forever.
                # Cancellation is not an Exception, so shutdown still works.
                logger.exception("Check round failed")
            await asyncio.sleep(settings.interval)
