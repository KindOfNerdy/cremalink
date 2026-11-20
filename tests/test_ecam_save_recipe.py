"""Frames that save or delete a recipe and write the name of a custom recipe."""

import pytest
from cremalink.core.binary import crc16_ccitt
from cremalink.ecam.builder import (
    OPERATION_DELETE,
    OPERATION_PREPARE,
    OPERATION_SAVE,
    build_brew_params,
    build_delete_recipe,
    build_recipe_name_write,
    build_save_recipe,
    verify_frame,
)
from cremalink.ecam.machine_profiles import STRIKER

#: The stored recipe of the custom recipe "wärmen" (slot 3), read from an Eletta Explore.
WARMEN = {1: 0, 2: 255, 15: 50, 9: 0, 12: 0, 28: 1, 25: 1, 11: 255}


def test_save_recipe_frame():
    frame = build_save_recipe(235, WARMEN, STRIKER, profile_slot=1)
    assert verify_frame(frame)
    # 0D len 83 F0 <bev> <action 0> <TLVs> <(profile<<2)|SAVE>
    assert frame[:6] == bytes([0x0D, frame[1], 0x83, 0xF0, 235, 0])
    assert frame[-3] == (1 << 2) | OPERATION_SAVE == 0x05
    # E0 drops tag 25, wide tags (1, 9, 15) have two bytes
    tlv = frame[6:-3]
    assert tlv == bytes.fromhex("01000002ff0f00320900000c001c010bff")


def test_a_normal_brew_uses_the_prepare_operation():
    frame = build_brew_params(
        1, 1, {15: 100}, STRIKER, profile_slot=1, operation=OPERATION_PREPARE
    )
    assert frame[-3] == 0x06


def test_delete_recipe_frame():
    frame = build_delete_recipe(235, STRIKER, profile_slot=1)
    assert verify_frame(frame)
    assert frame[-3] == (1 << 2) | OPERATION_DELETE == 0x04
    assert frame[2:5] == bytes([0x83, 0xF0, 235])


def test_name_frame_matches_the_published_layout():
    """The machine publishes names as ``d0 .. aa f0 <first> <last> <20 B name + icon> ...``."""
    frame = build_recipe_name_write(6, "TestWasser", 18, STRIKER)
    assert verify_frame(frame)
    assert frame[:6] == bytes([0x0D, 0x1C, 0xAB, 0xF0, 0x06, 0x06])
    assert frame[6:26].decode("utf-16-be") == "TestWasser"
    assert frame[26] == 18
    assert len(frame) == 0x1C + 1


def test_short_names_are_zero_padded():
    frame = build_recipe_name_write(3, "wärmen", 18, STRIKER)
    assert frame[6:26] == "wärmen".encode("utf-16-be").ljust(20, b"\x00")


@pytest.mark.parametrize(
    "slot,name,icon",
    [(0, "x", 1), (7, "x", 1), (1, "", 1), (1, "elfzeichenn", 1), (1, "x", 256)],
)
def test_invalid_name_arguments(slot, name, icon):
    with pytest.raises(ValueError):
        build_recipe_name_write(slot, name, icon, STRIKER)


def test_bad_profile_slot_is_refused():
    with pytest.raises(ValueError):
        build_save_recipe(235, WARMEN, STRIKER, profile_slot=0)
    with pytest.raises(ValueError):
        build_delete_recipe(235, STRIKER, profile_slot=0)


def test_crc_is_the_ccitt_of_the_frame():
    frame = build_recipe_name_write(6, "TestWasser", 18, STRIKER)
    assert frame[-2:] == crc16_ccitt(frame[:-2])
