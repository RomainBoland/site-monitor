import logging

import pytest

from site_monitor.checker import CheckResult, update_states
from site_monitor.state import State, TargetState, next_state

UNKNOWN, UP, DOWN = State.UNKNOWN, State.UP, State.DOWN


@pytest.mark.parametrize(
    "previous, check_up, expected, changed",
    [
        # From UNKNOWN: reaching a first conclusion is not a "change".
        (TargetState(UNKNOWN, 0), True, TargetState(UP, 0), False),
        (TargetState(UNKNOWN, 0), False, TargetState(UNKNOWN, 1), False),
        (TargetState(UNKNOWN, 2), False, TargetState(DOWN, 3), False),
        # From UP: failures below the threshold are only blips.
        (TargetState(UP, 0), False, TargetState(UP, 1), False),
        (TargetState(UP, 1), False, TargetState(UP, 2), False),
        (TargetState(UP, 2), False, TargetState(DOWN, 3), True),
        (TargetState(UP, 2), True, TargetState(UP, 0), False),  # success resets
        # From DOWN: one success is enough to recover.
        (TargetState(DOWN, 5), True, TargetState(UP, 0), True),
        (TargetState(DOWN, 5), False, TargetState(DOWN, 6), False),
    ],
)
def test_transitions_with_threshold_3(previous, check_up, expected, changed):
    assert next_state(previous, check_up, threshold=3) == (expected, changed)


def test_threshold_1_goes_down_on_first_failure():
    assert next_state(TargetState(UP, 0), False, threshold=1) == (
        TargetState(DOWN, 1),
        True,
    )


def test_realistic_sequence():
    # up, blip, up, then a real outage, then recovery.
    checks = [True, False, True, False, False, False, False, True]
    current = TargetState()
    states, changes = [], []
    for check_up in checks:
        current, changed = next_state(current, check_up, threshold=3)
        states.append(current.state)
        changes.append(changed)

    assert states == [UP, UP, UP, UP, UP, DOWN, DOWN, UP]
    assert changes == [False, False, False, False, False, True, False, True]


def result(target_id, up):
    return CheckResult(
        target_id=target_id,
        url=f"https://site{target_id}.example/",
        up=up,
        status_code=200 if up else 503,
        response_time=0.1,
        error=None,
        checked_at=0.0,
    )


def test_update_states_logs_down_and_recovery(caplog):
    states = {1: TargetState(UP, 2)}
    caplog.set_level(logging.INFO, logger="site_monitor.checker")

    update_states(states, [result(1, up=False)], threshold=3)
    assert states[1] == TargetState(DOWN, 3)
    assert any(
        r.levelno == logging.WARNING and "is DOWN" in r.getMessage()
        for r in caplog.records
    )

    caplog.clear()
    update_states(states, [result(1, up=True)], threshold=3)
    assert states[1] == TargetState(UP, 0)
    assert any("RECOVERED" in r.getMessage() for r in caplog.records)


def test_update_states_drops_deleted_targets():
    states = {1: TargetState(UP, 0), 2: TargetState(DOWN, 4)}

    update_states(states, [result(1, up=True)], threshold=3)  # target 2 was deleted

    assert list(states) == [1]
