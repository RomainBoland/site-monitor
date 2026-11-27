import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from site_monitor import checker, metrics
from site_monitor.checker import CheckResult, MonitorData, record_round
from site_monitor.main import app
from site_monitor.state import State, TargetState


def result(target_id, up, status_code=200, response_time=0.25):
    return CheckResult(
        target_id=target_id,
        url=f"https://site{target_id}.example/",
        up=up,
        status_code=status_code,
        response_time=response_time,
        error=None if status_code else "ConnectTimeout",
        checked_at=0.0,
    )


def scrape(data: MonitorData) -> dict:
    """Render the metrics and parse them back: {(sample name, labels): value}."""
    text = metrics.render(metrics.make_registry(data)).decode()
    samples = {}
    for family in text_string_to_metric_families(text):
        for s in family.samples:
            samples[(s.name, tuple(sorted(s.labels.items())))] = s.value
    return samples


def target_labels(target_id):
    return (("target_id", str(target_id)), ("url", f"https://site{target_id}.example/"))


def test_up_down_and_unknown_targets():
    data = MonitorData(
        results={
            1: result(1, up=True),
            2: result(2, up=False, status_code=503),
            3: result(3, up=False, status_code=None, response_time=None),
        },
        states={
            1: TargetState(State.UP, 0),
            2: TargetState(State.DOWN, 3),
            3: TargetState(State.UNKNOWN, 1),
        },
    )

    samples = scrape(data)

    assert samples[("site_monitor_target_up", target_labels(1))] == 1
    assert samples[("site_monitor_target_up", target_labels(2))] == 0
    # Unknown state: no "up" value at all, rather than a misleading 0 or 1.
    assert ("site_monitor_target_up", target_labels(3)) not in samples
    assert samples[("site_monitor_http_status", target_labels(2))] == 503
    assert samples[("site_monitor_response_time_seconds", target_labels(1))] == 0.25
    # No HTTP response (timeout): no status and no response time.
    assert ("site_monitor_http_status", target_labels(3)) not in samples
    assert ("site_monitor_response_time_seconds", target_labels(3)) not in samples


def test_counters_follow_recorded_rounds():
    data = MonitorData()

    record_round(data, [result(1, up=True)], threshold=2)  # UNKNOWN -> UP
    record_round(data, [result(1, up=False)], threshold=2)  # blip, still UP
    record_round(data, [result(1, up=False)], threshold=2)  # UP -> DOWN
    record_round(data, [result(1, up=True)], threshold=2)  # DOWN -> UP

    samples = scrape(data)
    assert samples[("site_monitor_checks_total", (("result", "success"),))] == 2
    assert samples[("site_monitor_checks_total", (("result", "failure"),))] == 2
    assert samples[("site_monitor_state_changes_total", (("state", "down"),))] == 1
    assert samples[("site_monitor_state_changes_total", (("state", "up"),))] == 1


def test_deleted_target_disappears_from_metrics():
    data = MonitorData()
    record_round(data, [result(1, up=True), result(2, up=True)], threshold=3)
    record_round(data, [result(1, up=True)], threshold=3)  # target 2 was deleted

    samples = scrape(data)

    assert ("site_monitor_target_up", target_labels(1)) in samples
    assert ("site_monitor_target_up", target_labels(2)) not in samples


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))

    async def no_checker(settings, data):
        pass

    monkeypatch.setattr(checker, "checker_loop", no_checker)
    with TestClient(app) as client:
        yield client


def test_metrics_endpoint(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    families = {f.name for f in text_string_to_metric_families(response.text)}
    assert {"site_monitor_checks", "site_monitor_state_changes"} <= families
