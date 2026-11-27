"""Expose the checker's data in the Prometheus text format."""

from prometheus_client import generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector, CollectorRegistry

from site_monitor.checker import MonitorData
from site_monitor.state import State


class MonitorCollector(Collector):
    """Builds the metrics from MonitorData at scrape time.

    Reading the data on each scrape (instead of updating global Gauge objects)
    means a deleted target disappears from /metrics immediately.
    """

    def __init__(self, data: MonitorData):
        self.data = data

    def collect(self):
        # Labels must have bounded values: target_id/url are bounded by the
        # number of targets. Never put error messages or timestamps in labels.
        labels = ["target_id", "url"]
        up = GaugeMetricFamily(
            "site_monitor_target_up",
            "1 if the target is UP, 0 if DOWN (after consecutive failures). "
            "Absent while the state is unknown.",
            labels=labels,
        )
        response_time = GaugeMetricFamily(
            "site_monitor_response_time_seconds",
            "Time until the response headers arrived, for the latest check.",
            labels=labels,
        )
        http_status = GaugeMetricFamily(
            "site_monitor_http_status",
            "HTTP status code of the latest check. Absent if no response.",
            labels=labels,
        )

        for target_id, target_state in self.data.states.items():
            result = self.data.results.get(target_id)
            if result is None:
                continue
            values = [str(target_id), result.url]
            if target_state.state != State.UNKNOWN:
                up.add_metric(values, 1 if target_state.state == State.UP else 0)
            if result.response_time is not None:
                response_time.add_metric(values, result.response_time)
            if result.status_code is not None:
                http_status.add_metric(values, result.status_code)

        # CounterMetricFamily appends "_total" to the name by itself.
        checks = CounterMetricFamily(
            "site_monitor_checks",
            "Number of checks performed, by result.",
            labels=["result"],
        )
        for result_name, count in self.data.checks_total.items():
            checks.add_metric([result_name], count)

        changes = CounterMetricFamily(
            "site_monitor_state_changes",
            "Number of UP<->DOWN state changes, by new state.",
            labels=["state"],
        )
        for state_name, count in self.data.state_changes_total.items():
            changes.add_metric([state_name], count)

        yield from (up, response_time, http_status, checks, changes)


def make_registry(data: MonitorData) -> CollectorRegistry:
    # A dedicated registry (not the library's global one) keeps tests isolated.
    registry = CollectorRegistry()
    registry.register(MonitorCollector(data))
    return registry


def render(registry: CollectorRegistry) -> bytes:
    return generate_latest(registry)
