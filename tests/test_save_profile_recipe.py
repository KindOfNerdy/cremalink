"""Keep changed values of a standard drink in the profile, like the app's save."""

from __future__ import annotations

import base64

import pytest
from cremalink.core.binary import crc16_ccitt
from cremalink.domain.device import Device
from cremalink.ecam.builder import beverage_type, build_save_recipe, verify_frame
from cremalink.ecam.machine_profiles import STRIKER
from tests.test_ecam452_cloud_datapoints import DEVICES, CloudLikeTransport


@pytest.mark.parametrize(
    "bev,kind",
    [
        (2, "hot"),
        (16, "hot"),
        (50, "cold"),
        (57, "cold"),
        (27, "cold"),
        (122, "cold"),
        (80, "to_go_hot"),
        (86, "to_go_hot"),
        (100, "to_go_cold"),
        (141, "to_go_cold"),
        (230, "hot"),
    ],
)
def test_beverage_type_like_the_app(bev, kind):
    assert beverage_type(bev) == kind


def test_without_cold_brew_27_and_140_are_hot():
    assert beverage_type(27, cold_brew=False) == "hot"
    assert beverage_type(140, cold_brew=False) == "hot"


def _tlv(frame: bytes) -> bytes:
    return frame[6:-3]


def test_hot_save_keeps_the_amounts_and_drops_param_8():
    frame = build_save_recipe(2, {1: 180, 2: 3, 8: 1, 27: 2}, STRIKER, profile_slot=1)
    assert verify_frame(frame)
    assert frame[5] == 0 and frame[-3] == (1 << 2) | 1
    assert _tlv(frame) == bytes.fromhex("0100b402031b02")


def test_cold_save_drops_coffee_milk_and_water_but_keeps_the_rest():
    frame = build_save_recipe(
        50,
        {1: 100, 9: 300, 15: 80, 8: 1, 27: 2, 31: 1},
        STRIKER,
        profile_slot=1,
        cold=True,
    )
    assert verify_frame(frame)
    assert _tlv(frame) == bytes.fromhex("08011b021f01")


def test_bean_drink_is_saved_without_the_bean_flag_and_strength():
    frame = build_save_recipe(200, {1: 40, 2: 3}, STRIKER, profile_slot=1)
    assert frame[5] == 0  # no 0x80
    assert _tlv(frame) == bytes.fromhex("010028")


def _blob(body: bytes) -> bytes:
    head = bytes([0xD0, len(body) + 3]) + body
    return head + crc16_ccitt(head)


class _Machine(CloudLikeTransport):
    """Stores saved recipes per drink and republishes them on a 0xA6 read."""

    def __init__(self, *, applies=True):
        self.applies = applies
        self.stamps: dict[str, int] = {}
        self.tlv = {2: bytes.fromhex("0100b40203"), 50: bytes.fromhex("1b01")}
        super().__init__({})
        for bev in self.tlv:
            self._publish(bev)

    def _name(self, bev):
        return f"d1{bev:02d}_1_rec_test_{bev}"

    def _publish(self, bev):
        name = self._name(bev)
        self.stamps[name] = self.stamps.get(name, 0) + 1
        self.properties[name] = base64.b64encode(
            _blob(bytes([0xA6, 0xF0, 1, bev]) + self.tlv[bev])
        ).decode()

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
        frame = frame[: frame[1] + 1]
        if frame[2] == 0x83 and self.applies and frame[-3] & 3 == 1:
            bev = frame[4]
            stored = dict(_pairs(self.tlv.get(bev, b"")))
            stored.update(_pairs(frame[6:-3]))
            self.tlv[bev] = b"".join(bytes([t]) + v for t, v in stored.items())
        elif frame[2] == 0xA6 and frame[5] in self.tlv:
            self._publish(frame[5])
        return result


def _pairs(tlv: bytes):
    i = 0
    while i < len(tlv):
        tag = tlv[i]
        width = 2 if tag in (1, 9, 15) else 1
        yield tag, tlv[i + 1 : i + 1 + width]
        i += 1 + width


def _device(**kw):
    machine = _Machine(**kw)
    dev = Device.from_map(machine, device_map_path=str(DEVICES / "ECAM452.json"))
    dev.write_confirm_seconds = 4.0
    dev.recipe_confirm_seconds = 4.0
    dev.app_id_confirm_seconds = 0.0
    dev.app_id_confirm_own_seconds = 0.0
    dev.app_id_confirm_poll = 0.0
    dev.response_poll = 0
    dev.seed_catalog_from_properties(dict(machine.properties))
    machine.sent.clear()
    return dev, machine


def test_save_profile_recipe_confirms_the_new_values():
    dev, machine = _device()
    assert dev.save_profile_recipe(2, {1: 150, 2: 4}, profile_slot=1) is True
    assert machine.tlv[2] == bytes.fromhex("0100960204")


def test_cold_drink_is_saved_without_amounts_and_still_confirmed():
    dev, machine = _device()
    assert dev.save_profile_recipe(50, {1: 120, 27: 3}, profile_slot=1) is True
    assert machine.tlv[50] == bytes.fromhex("1b03")


def test_an_ignored_save_is_reported():
    dev, _ = _device(applies=False)
    assert dev.save_profile_recipe(2, {1: 150}, profile_slot=1) is False


def test_custom_recipes_are_refused():
    dev, machine = _device()
    with pytest.raises(ValueError):
        dev.save_profile_recipe(230, {15: 50}, profile_slot=1)
    assert machine.sent == []


def test_save_without_confirm_returns_at_once_and_confirms_later():
    dev, machine = _device(applies=False)
    # Sent, not waited for: a brew may follow right away (like the app).
    assert dev.save_profile_recipe(2, {1: 150}, profile_slot=1, confirm=False) is True
    assert machine.sent
    assert dev.confirm_profile_recipe(2, {1: 150}, profile_slot=1) is False
    dev, machine = _device()
    assert dev.save_profile_recipe(2, {1: 150, 2: 4}, profile_slot=1, confirm=False) is True
    assert dev.confirm_profile_recipe(2, {1: 150, 2: 4}, profile_slot=1) is True
