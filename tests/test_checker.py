import asyncio
import contextlib
import sqlite3

import httpx2
import pytest

from site_monitor import checker


def run_check(handler, url="https://example.com/"):
    """Run check_target against a fake transport: no real network involved."""

    async def main():
        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            return await checker.check_target(client, 1, url)

    return asyncio.run(main())


def test_200_is_up(fake_dns):
    result = run_check(lambda request: httpx2.Response(200))

    assert result.up is True
    assert result.status_code == 200
    assert result.response_time is not None and result.response_time >= 0
    assert result.error is None


@pytest.mark.parametrize("status", [404, 500, 503])
def test_error_status_is_down(fake_dns, status):
    result = run_check(lambda request: httpx2.Response(status))

    assert result.up is False
    assert result.status_code == status


def test_redirect_is_up_and_not_followed(fake_dns):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx2.Response(301, headers={"Location": "http://127.0.0.1/"})

    result = run_check(handler)

    assert result.up is True
    assert result.status_code == 301
    assert requested == ["https://example.com/"]  # the internal URL was never requested


@pytest.mark.parametrize(
    "exc", [httpx2.ConnectTimeout, httpx2.ReadTimeout, httpx2.ConnectError]
)
def test_network_errors_are_down(fake_dns, exc):
    def handler(request):
        raise exc("simulated", request=request)

    result = run_check(handler)

    assert result.up is False
    assert result.status_code is None
    assert result.error == exc.__name__


def test_ssrf_is_rechecked_before_each_request(fake_dns):
    # internal.example resolves to 10.0.0.5 in the fake DNS (e.g. DNS changed
    # after registration). No request may be sent.
    requested = []

    def handler(request):
        requested.append(request)
        return httpx2.Response(200)

    result = run_check(handler, url="https://internal.example/")

    assert result.up is False
    assert result.error.startswith("blocked:")
    assert requested == []


def test_concurrency_is_limited(fake_dns):
    in_flight = 0
    max_in_flight = 0

    async def handler(request):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx2.Response(200)

    targets = [{"id": i, "url": "https://example.com/"} for i in range(10)]

    async def main():
        transport = httpx2.MockTransport(handler)
        async with httpx2.AsyncClient(transport=transport) as client:
            return await checker.run_checks(client, targets, concurrency=3)

    results = asyncio.run(main())

    assert len(results) == 10
    assert all(r.up for r in results)
    assert max_in_flight == 3


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("CHECK_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("CHECK_CONCURRENCY", "4")

    settings = checker.load_settings()

    assert (settings.interval, settings.timeout, settings.concurrency) == (5, 2.5, 4)


def test_loop_survives_a_failed_round(monkeypatch):
    calls = 0

    def flaky_load_targets():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return []

    monkeypatch.setattr(checker, "_load_targets", flaky_load_targets)
    settings = checker.CheckerSettings(interval=0.01, timeout=1, concurrency=1)

    async def main():
        task = asyncio.create_task(checker.checker_loop(settings, {}))
        while calls < 3:
            await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(main(), timeout=2))

    assert calls >= 3  # the loop kept going after the first round failed
