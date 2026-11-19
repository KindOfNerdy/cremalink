"""Custom recipes built from ingredients, the way the Coffee Link app builds them.

The app does not copy a drink into a custom place. It starts from the place's own
limits and lets you switch ingredients on: coffee, milk, water (plus strength, froth
and "milk first"). The machine's own recipes show how the parameters follow from that:
the *accessory* (param 28) is 2 with milk, 1 for hot water without coffee and 0 otherwise.
(``tests/test_custom_recipe.py`` pins this against the recipes of a real machine.)

Raw units as on the wire: coffee and water in ml, milk in tenths of a second.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: ``(minimum, maximum)`` of the ingredients of a custom place, from the machine's
#: factory descriptor of recipes 230-235 (identical for all six places).
COFFEE_ML = (20, 180)
WATER_ML = (50, 300)
MILK_TENTHS = (50, 1080)
TASTE = (0, 5)
FROTH = (0, 2)

#: Wire value of an unused strength/froth (what the machine stores without coffee/milk).
UNUSED = 255

#: Default when an ingredient is switched on: the app uses the descriptor's default but
#: not less than the minimum, which for the custom places is the minimum.
DEFAULT_TASTE = 3
DEFAULT_FROTH = 1


@dataclass(frozen=True)
class Ingredients:
    """What a custom recipe consists of (0 / ``False`` = not used)."""

    coffee: int = 0
    taste: int | None = None
    milk: int = 0
    froth: int | None = None
    milk_first: bool = False
    water: int = 0


def compose_custom_recipe(ingredients: Ingredients) -> dict[int, int]:
    """Recipe parameters ``{param id: raw value}`` for ``ingredients``.

    Raises ``ValueError`` when nothing is switched on or an amount is outside the
    custom place's limits. The key order is the one the machine accepted in live tests.
    """
    i = ingredients
    for name, value, (low, high) in (
        ("coffee", i.coffee, COFFEE_ML),
        ("water", i.water, WATER_ML),
        ("milk", i.milk, MILK_TENTHS),
    ):
        if value and not low <= value <= high:
            raise ValueError(
                f"{name} must be {low}-{high} (or 0 for none), got {value}"
            )
    if not (i.coffee or i.milk or i.water):
        raise ValueError("switch on at least one of coffee, milk and water")
    taste = (DEFAULT_TASTE if i.taste is None else i.taste) if i.coffee else UNUSED
    froth = (DEFAULT_FROTH if i.froth is None else i.froth) if i.milk else UNUSED
    if i.coffee and not TASTE[0] <= taste <= TASTE[1]:
        raise ValueError(f"strength must be {TASTE[0]}-{TASTE[1]}, got {taste}")
    if i.milk and not FROTH[0] <= froth <= FROTH[1]:
        raise ValueError(f"froth must be {FROTH[0]}-{FROTH[1]}, got {froth}")
    accessory = 2 if i.milk else 1 if (i.water and not i.coffee) else 0
    return {
        1: i.coffee,
        2: taste,
        15: i.water,
        9: i.milk,
        12: int(bool(i.milk_first and i.milk)),
        28: accessory,
        25: 1,
        11: froth,
    }


def describe_custom_recipe(values: Mapping[int, int]) -> Ingredients:
    """The ingredients of a stored recipe (the reverse of :func:`compose_custom_recipe`)."""
    coffee = int(values.get(1, 0) or 0)
    milk = int(values.get(9, 0) or 0)
    taste = values.get(2)
    froth = values.get(11)
    return Ingredients(
        coffee=coffee,
        taste=None if not coffee or taste in (None, UNUSED) else int(taste),
        milk=milk,
        froth=None if not milk or froth in (None, UNUSED) else int(froth),
        milk_first=bool(values.get(12, 0)) and bool(milk),
        water=int(values.get(15, 0) or 0),
    )
