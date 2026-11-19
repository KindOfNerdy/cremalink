"""Custom recipes from ingredients, pinned against recipes the app made on a real Eletta."""

import pytest
from cremalink.ecam.custom_recipe import (
    Ingredients,
    compose_custom_recipe,
    describe_custom_recipe,
)

# Stored recipes of an Eletta Explore (read from its cloud datapoints d240-d245).
LATTE_XL = {1: 55, 2: 3, 15: 0, 9: 500, 12: 0, 28: 2, 25: 1, 11: 1}
HOT_WATER = {1: 0, 2: 255, 15: 55, 9: 0, 12: 0, 28: 1, 25: 1, 11: 255}
FLAT_WHITE = {1: 55, 2: 5, 15: 0, 9: 480, 12: 1, 28: 2, 25: 1, 11: 1}


def test_hot_water_matches_the_machine_recipes():
    assert compose_custom_recipe(Ingredients(water=55)) == HOT_WATER


def test_coffee_with_milk_matches_the_machine_recipes():
    assert (
        compose_custom_recipe(Ingredients(coffee=55, taste=3, milk=500, froth=1))
        == LATTE_XL
    )
    flat = Ingredients(coffee=55, taste=5, milk=480, froth=1, milk_first=True)
    assert compose_custom_recipe(flat) == FLAT_WHITE


def test_coffee_alone_needs_no_accessory():
    assert compose_custom_recipe(Ingredients(coffee=40))[28] == 0


def test_coffee_and_water_like_an_americano_needs_no_accessory():
    assert compose_custom_recipe(Ingredients(coffee=40, water=100))[28] == 0


@pytest.mark.parametrize("values", [LATTE_XL, HOT_WATER, FLAT_WHITE])
def test_describe_is_the_reverse(values):
    assert compose_custom_recipe(describe_custom_recipe(values)) == values


@pytest.mark.parametrize(
    "ingredients",
    [
        Ingredients(),
        Ingredients(coffee=19),
        Ingredients(coffee=181),
        Ingredients(water=49),
        Ingredients(water=301),
        Ingredients(milk=49),
        Ingredients(milk=1081),
        Ingredients(coffee=50, taste=6),
        Ingredients(milk=100, froth=3),
    ],
)
def test_out_of_range_or_empty_is_refused(ingredients):
    with pytest.raises(ValueError):
        compose_custom_recipe(ingredients)


def test_milk_first_without_milk_is_ignored():
    assert compose_custom_recipe(Ingredients(water=60, milk_first=True))[12] == 0
