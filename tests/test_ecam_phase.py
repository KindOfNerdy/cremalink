"""Drink phase from the monitor's status and action (observed on an Eletta Explore)."""

import pytest
from cremalink.ecam.phase import PHASES, drink_phase


def _run(status, actions):
    return [drink_phase(status, a) for a in actions]


def test_coffee_sequence_as_observed():
    """65 coffees in a month: 4 → 6 → [10] → 11 → 13 → 14."""
    assert _run(7, [4, 6, 11, 13, 14]) == [
        "grinding",
        "preparing",
        "dispensing",
        "finished",
        "finished",
    ]
    assert _run(7, [4, 6, 10, 11, 13, 14])[2] == "preparing"


def test_hot_water_and_tea_sequence_as_observed():
    """37 runs: status 11 with actions 2 → 3 → 4 → 6."""
    assert set(_run(11, [2, 3, 4, 6])) == {"hot_water"}


def test_ready_and_idle_give_no_phase():
    assert drink_phase(7, 0) is None


@pytest.mark.parametrize("status", [0, 1, 2, 4, 8, 12, 14, 29])
def test_statuses_that_name_themselves_give_no_phase(status):
    assert drink_phase(status, 5) is None


def test_steps_with_an_app_text():
    assert drink_phase(7, 7) == "heating_water"
    assert drink_phase(7, 8) == "pre_infusion"
    assert drink_phase(5, 2) == "steam"
    assert drink_phase(5, 4) == "dispensing"
    assert drink_phase(10, 4) == "dispensing_milk"
    assert drink_phase(10, 2) == "grinding"
    assert drink_phase(17, 2) == "dispensing"


def test_unknown_values_are_none_or_generic():
    assert drink_phase(None, 4) is None
    assert drink_phase(7, None) is None
    assert drink_phase(7, 99) == "preparing"


def test_every_phase_is_a_known_key():
    seen = {drink_phase(s, a) for s in (5, 7, 10, 11, 16, 17) for a in range(0, 20)}
    assert seen - {None} <= set(PHASES)


def test_monitor_view_exposes_the_phase():
    import base64
    from datetime import datetime

    from cremalink.parsing.monitor.model import MonitorSnapshot
    from cremalink.parsing.monitor.view import MonitorView

    # a real frame (Eletta Explore, 20.10.): status 7 (ready), action 11 (dispensing), progress 22
    raw = bytes.fromhex("d012750f0107000000070b160100000000ed906ad6f23b")
    snap = MonitorSnapshot(
        raw=raw, raw_b64=base64.b64encode(raw).decode(), received_at=datetime.now()
    )
    view = MonitorView(snap, {})
    assert (view.status_code, view.action_code, view.progress_percent) == (7, 11, 22)
    assert view.drink_phase == "dispensing"
