"""What the machine is doing while a drink is made, from its monitor status and action.

The machine keeps the status ``ready`` (7) while it makes coffee; the action byte says
which step it is in. The app maps status and action to its own texts (grinding, heating
water, pre-infusion, dispensing ...); this is the same mapping as phase keys, checked
against a month of monitor frames of an Eletta Explore (coffee: 4 → 6 → [10] → 11 → 13 →
14, hot water and tea: status 11 with actions 2 → 3 → 4 → 6).

Milk, steam, chocolate and cold drinks follow the app's table; they were not seen in
that month.
"""

from __future__ import annotations

#: All phases, in the order a drink goes through them.
PHASES = (
    "grinding",
    "heating_water",
    "pre_infusion",
    "preparing",
    "dispensing",
    "dispensing_milk",
    "hot_water",
    "steam",
    "finished",
)

_STATUS_READY = 7
_STATUS_STEAM = 5
_STATUS_MILK = 10
_STATUS_HOT_WATER = 11
_STATUS_CHOCOLATE = 16
_STATUS_MILK_ALT = 17


def drink_phase(status: int | None, action: int | None) -> str | None:
    """The phase of the drink being made, or ``None`` when no drink is being made.

    Statuses that name themselves (standby, waking up, rinsing, descaling ...) give
    ``None``: the status already says what happens.
    """
    if status is None or action is None:
        return None
    if status == _STATUS_READY:
        if action == 0:
            return None
        return {
            4: "grinding",
            7: "heating_water",
            8: "pre_infusion",
            11: "dispensing",
            13: "finished",
            14: "finished",
        }.get(action, "preparing")
    if status == _STATUS_HOT_WATER:
        return "hot_water"
    if status == _STATUS_STEAM:
        return {2: "steam", 4: "dispensing", 6: "finished"}.get(action, "steam")
    if status == _STATUS_MILK:
        return {1: "steam", 2: "grinding", 4: "dispensing_milk", 7: "grinding"}.get(
            action, "preparing"
        )
    if status == _STATUS_CHOCOLATE:
        return "steam" if action == 2 else "preparing"
    if status == _STATUS_MILK_ALT:
        return {1: "preparing", 2: "dispensing", 3: "finished"}.get(action, "preparing")
    return None
