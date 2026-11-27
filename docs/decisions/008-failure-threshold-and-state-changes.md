# 008 — Consecutive-failure threshold and state-change detection, in memory

- Status: accepted
- Date: 2026-11-27

## Context

A single failed check (a timeout, a dropped packet) is common on the internet and does not mean a site is down. Treating every failure as an outage causes alert fatigue. The service must report a target DOWN only after N consecutive failures, and detect state changes (UP→DOWN, DOWN→UP), which future alerts will be built on.

## Options considered

Where the state lives:

| Option | Pros | Cons |
|---|---|---|
| **In memory** | No schema change; no database writes every round; consistent with decision 007 | After a restart, targets start UNKNOWN; a site already down needs N rounds to be DOWN again |
| SQLite columns | Survives restarts | Hand-written migration (`ALTER TABLE`); one write per target per round competing with API writes |

When a DOWN target becomes UP again:

| Option | Pros | Cons |
|---|---|---|
| **After 1 success** | Simple; recovery reported immediately; what most uptime tools do | A flapping site produces many events |
| After M successes (hysteresis) | Damps flapping | A second setting to tune; recovery reported late |

## Decision

- **States:** `UNKNOWN`, `UP` and `DOWN` (`site_monitor/state.py`), stored in memory in `app.state.states`, next to the latest results.
- **Transition rules,** in one pure function `next_state(previous, check_up, threshold)`:
  - a success means `UP` and resets the failure counter;
  - a failure increments the counter; the state becomes `DOWN` when the counter reaches `FAILURE_THRESHOLD` (default 3), otherwise the previous state is kept.
- **A "state change" is only UP↔DOWN.** Leaving `UNKNOWN` is not a change, so a restart cannot produce a fake "recovered" event.
- **Changes are logged:** WARNING for DOWN (with the failure count and last error), INFO for recovery. In step 9 they become metrics.
- **Settings validation was added for every checker variable:** interval and timeout must be > 0, concurrency and threshold must be ≥ 1, and invalid values stop the startup. This fixes a gap from step 7: `CHECK_CONCURRENCY=0` created `Semaphore(0)` and made the checker hang silently forever.

## Consequences

- With the defaults (30 s interval, threshold 3), an outage is reported 60–90 s after it starts. Lowering the threshold makes detection faster but noisier.
- After a restart, a site that is already down is reported DOWN after N rounds, but without a "change" event. An outage that started before the restart is therefore not announced as new. Alerts based on the current state (`up == 0` in Prometheus) still see it.
- A site that is new and broken from the start goes UNKNOWN→DOWN without a change event, for the same reason.
- The state machine is exhaustively tested without network, clock or database. Deliberately introducing an off-by-one (`>` instead of `>=`) or removing the UNKNOWN rule makes the tests fail.
- Prometheus alert rules can also debounce (`for: 90s`). Both layers can coexist: the app exposes a stable state, and Prometheus decides when to page.

## I would choose differently if...

- the app sent notifications itself (email, chat): the state would be persisted, so restarts neither lose nor duplicate events;
- monitored sites were known to flap often: recovery would require M consecutive successes (hysteresis).
