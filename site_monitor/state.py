"""Per-target state machine: DOWN only after N consecutive failures, UP after one success."""

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    UNKNOWN = "unknown"  # no conclusion yet (new target, or just after a restart)
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class TargetState:
    state: State = State.UNKNOWN
    consecutive_failures: int = 0


def next_state(
    previous: TargetState, check_up: bool, threshold: int
) -> tuple[TargetState, bool]:
    """Return the new state and whether it is a state change (UP <-> DOWN).

    Leaving UNKNOWN is not a change: after a restart, a site that is still up
    must not trigger a fake "recovered" event.
    """
    if check_up:
        new = TargetState(State.UP, 0)
    else:
        failures = previous.consecutive_failures + 1
        # Below the threshold, keep the previous conclusion (a blip is not an outage).
        state = State.DOWN if failures >= threshold else previous.state
        new = TargetState(state, failures)

    changed = previous.state != State.UNKNOWN and new.state != previous.state
    return new, changed
