# 009 — Prometheus metrics with prometheus_client, Gauges for per-target values

- Status: accepted
- Date: 2026-11-27

## Context

Prometheus will scrape (pull) `GET /metrics` every 15–30 s and store the values as time series, which Grafana graphs and alert rules use. The service must expose each target's state, latest response time and status, plus global counters, in the Prometheus text format.

## Options considered

Library:

| Option | Pros | Cons |
|---|---|---|
| **prometheus_client** | Official Prometheus library; zero dependencies; output maps directly to what Prometheus stores | Prometheus-only |
| OpenTelemetry SDK + Prometheus exporter | Vendor-neutral; metrics + traces + logs; backend can change without code changes | 4+ packages, including prometheus_client itself; many concepts; exporter in beta (0.66b2) |
| Hand-written text format | No dependency | Escaping and format details to get right by hand |

Response time type:

| Option | Pros | Cons |
|---|---|---|
| **Gauge (latest check)** | 1 time series per target; easy to read | Spikes between scrapes can be missed; no percentiles |
| Histogram | Percentiles (p95/p99), no lost samples | ~12 series per target (buckets); bucket tuning; harder queries |

Note: prometheus_client has always been versioned 0.x and labelled "Beta" on PyPI, despite being the official and ubiquitous library (0.26.0 here).

## Decision

`prometheus-client` as a runtime dependency. Metrics:

| Metric | Type | Labels |
|---|---|---|
| `site_monitor_target_up` | Gauge: 1 UP, 0 DOWN, absent while UNKNOWN | `target_id`, `url` |
| `site_monitor_response_time_seconds` | Gauge (latest check; absent if no response) | `target_id`, `url` |
| `site_monitor_http_status` | Gauge (latest status; absent if no response) | `target_id`, `url` |
| `site_monitor_checks_total` | Counter | `result` = success/failure |
| `site_monitor_state_changes_total` | Counter | `state` = up/down |

Implementation choices:

- A custom **collector** builds the metrics from `MonitorData` at scrape time, instead of updating global `Gauge` objects. A deleted target disappears immediately, with no stale series to remove by hand.
- A dedicated `CollectorRegistry` (not the library's global one) keeps tests isolated.
- The checker's shared data (results, states, counters) is grouped in one `MonitorData` dataclass instead of separate arguments.
- `/metrics` is an `async def` endpoint, so it runs on the event loop like the checker. `record_round()` contains no `await`, so a scrape can never read half-updated data. A sync endpoint would run in a worker thread and could hit "dictionary changed size during iteration".
- UNKNOWN is exported as *absent*, not 0: a 0 after every restart would fire false "site down" alerts.
- Label values are bounded (`target_id`, `url`, fixed enums). Error messages and timestamps are never used as labels, to avoid cardinality explosion.
- The `site_monitor_` prefix avoids clashing with Prometheus's built-in `up` metric.

## Consequences

- The main alert rule for the future is `site_monitor_target_up == 0`, optionally with `for:` for extra debouncing.
- Counters reset to 0 on restart. That is expected: Prometheus's `rate()` and `increase()` handle resets.
- `/metrics` is unauthenticated. Before deployment it must not be reachable from the internet (only from Prometheus on the internal Docker network), or it should sit behind the proxy with access control.
- Metrics live in the single checker process. Multiple workers or replicas would each expose different data (see decision 007).
- Tests parse the output with prometheus_client's own parser, which also proves the format is valid.

## I would choose differently if...

- the organisation used several observability backends or needed distributed tracing: OpenTelemetry;
- per-site latency percentiles became a requirement, or checks ran much more often than scrapes: a Histogram for response time.
