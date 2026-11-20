"""Create, change and delete custom recipes: Device.save_custom_recipe / delete_custom_recipe."""

from __future__ import annotations

import base64

import pytest
from cremalink.core.binary import crc16_ccitt
from cremalink.domain.device import Device
from tests.test_ecam452_cloud_datapoints import DEVICES, CloudLikeTransport

EMPTY_TLV = bytes.fromhex("01000002ff0f00000900000c001c0019000bff")
NAMES_PROP = "d054_custom_name_46"
RECIPE_PROP = "d245_rec_custom_6"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _blob(body: bytes) -> bytes:
    head = bytes([0xD0, len(body) + 3]) + body
    return head + crc16_ccitt(head)


def _entry(name: str, icon: int) -> bytes:
    return name.encode("utf-16-be").ljust(20, b"\x00") + bytes([icon])


class _Eletta(CloudLikeTransport):
    """Plays an Eletta: stores recipes and names, republishes them when asked to read."""

    def __init__(self, *, applies=True):
        self.applies = applies
        self.tlv = EMPTY_TLV
        self.names = {4: ("FlatWh. gr", 11), 5: ("kl. FlatWh", 0), 6: ("Custom 6", 0)}
        self.stamps: dict[str, int] = {}
        super().__init__({})
        self._publish_all()

    def _bump(self, name, raw):
        self.stamps[name] = self.stamps.get(name, 0) + 1
        self.properties[name] = _b64(raw)

    def _publish_all(self):
        self._publish_recipe()
        self._publish_names()

    def _publish_recipe(self):
        self._bump(RECIPE_PROP, _blob(bytes([0xA6, 0xF0, 1, 235]) + self.tlv))

    def _publish_names(self):
        body = bytes([0xAA, 0xF0, 4, 6]) + b"".join(
            _entry(*self.names[s]) for s in (4, 5, 6)
        )
        self._bump(NAMES_PROP, _blob(body))

    def get_property(self, name):
        entry = super().get_property(name)
        if entry is not None:
            entry["data_updated_at"] = str(self.stamps.get(name, 0))
        return entry

    def send_command(self, command, alternative_property=None):
        frame = base64.b64decode(command)
        result = super().send_command(command, alternative_property)
        if len(frame) < 5 or frame[0] != 0x0D:  # app id registration, not a machine frame
            return result
        frame = frame[: frame[1] + 1]  # the transport appends a counter and the app id
        op = frame[2]
        if op == 0x83 and self.applies and frame[4] == 235:
            operation = frame[-3] & 0x03
            if operation in (1, 3):
                self.tlv = frame[6:-3]
            elif operation == 0:
                self.tlv = EMPTY_TLV
                self.names[6] = ("", 0)
        elif op == 0xAB and self.applies and frame[4] == 6:
            self.names[6] = (frame[6:26].decode("utf-16-be").rstrip("\x00"), frame[26])
        elif op == 0xA6 and frame[5] == 235:
            self._publish_recipe()
        elif op == 0xAA:
            self._publish_names()
        return result


def _device(*, applies=True):
    machine = _Eletta(applies=applies)
    dev = Device.from_map(machine, device_map_path=str(DEVICES / "ECAM452.json"))
    dev.write_confirm_seconds = 5.0
    dev.recipe_confirm_seconds = 5.0
    dev.app_id_confirm_seconds = 0.0
    dev.app_id_confirm_own_seconds = 0.0
    dev.app_id_confirm_poll = 0.0
    dev.response_poll = 0
    dev.seed_catalog_from_properties(dict(machine.properties))
    machine.sent.clear()
    return dev, machine


HOT_WATER = {1: 0, 2: 255, 15: 50, 9: 0, 12: 0, 28: 1, 25: 1, 11: 255}


def test_save_creates_the_recipe_and_confirms_it():
    dev, machine = _device()
    assert (
        dev.save_custom_recipe(6, "TestWasser", 12, HOT_WATER, profile_slot=1) is True
    )
    assert machine.names[6] == ("TestWasser", 12)
    assert machine.tlv == bytes.fromhex("01000002ff0f00320900000c001c010bff")
    assert dev.custom_recipe_names()[235] == "TestWasser"
    assert dev.custom_recipe_icons()[235] == 12
    saves = [f[: f[1] + 1] for f, _ in machine.sent if f[2] == 0x83]
    assert len(saves) == 1 and saves[0][-3] == (1 << 2) | 1  # SAVE, nothing is poured


def test_save_and_brew_uses_prepare_and_save():
    dev, machine = _device()
    assert dev.save_custom_recipe(
        6, "TestWasser", 12, HOT_WATER, brew=True, profile_slot=1
    )
    brew = next(f[: f[1] + 1] for f, _ in machine.sent if f[2] == 0x83)
    assert brew[5] == 1  # START
    assert brew[-3] & 0x03 == 3


def test_an_ignored_write_is_reported():
    dev, machine = _device(applies=False)
    assert (
        dev.save_custom_recipe(6, "TestWasser", 12, HOT_WATER, profile_slot=1) is False
    )
    assert dev.custom_recipe_names().get(235) != "TestWasser"


def test_delete_empties_the_slot():
    dev, machine = _device()
    dev.save_custom_recipe(6, "TestWasser", 12, HOT_WATER, profile_slot=1)
    assert dev.delete_custom_recipe(6, profile_slot=1) is True
    assert machine.names[6] == ("", 0)
    assert (
        235 not in dev.custom_recipe_names()
        or dev.custom_recipe_names()[235] != "TestWasser"
    )


@pytest.mark.parametrize("slot", [0, 7])
def test_invalid_slots_are_refused_before_sending(slot):
    dev, machine = _device()
    with pytest.raises(ValueError):
        dev.save_custom_recipe(slot, "x", 1, {15: 50})
    with pytest.raises(ValueError):
        dev.delete_custom_recipe(slot)
    assert machine.sent == []


def test_invalid_name_is_refused_before_sending():
    dev, machine = _device()
    with pytest.raises(ValueError):
        dev.save_custom_recipe(6, "", 12, {15: 50})
    assert machine.sent == []


def test_a_place_emptied_elsewhere_disappears_on_the_next_seed():
    dev, machine = _device()
    dev.save_custom_recipe(6, "TestWasser", 12, HOT_WATER, profile_slot=1)
    assert dev.custom_recipe_names()[235] == "TestWasser"
    machine.names[6] = ("", 0)  # deleted in the app
    machine._publish_names()
    dev.seed_catalog_from_properties(dict(machine.properties))
    assert 235 not in dev.custom_recipe_names()
    assert 235 not in dev.custom_recipe_icons()


def test_delete_takes_the_drink_out_of_the_favourites_first():
    dev, machine = _device()
    dev._favorite_cache[1] = [2, 235, 8]
    written = []
    dev.set_favorite_beverages = (
        lambda ids, profile=None: written.append((ids, profile)) or True
    )
    assert dev.delete_custom_recipe(6, profile_slot=1) is True
    assert written == [([2, 8], 1)]


def test_delete_leaves_the_favourites_alone_when_the_drink_is_not_in_them():
    dev, machine = _device()
    dev._favorite_cache[1] = [2, 8]
    written = []
    dev.set_favorite_beverages = lambda ids, profile=None: written.append(ids) or True
    dev.delete_custom_recipe(6, profile_slot=1)
    assert written == []
