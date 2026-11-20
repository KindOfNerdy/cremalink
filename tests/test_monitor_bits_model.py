"""Switch bits that mean something else on a model (device map ``switch_names``)."""

import base64
from datetime import datetime
from pathlib import Path

from cremalink.domain.device import Device
from cremalink.ecam.monitor_bits import SWITCH_BITS, switch_bits
from cremalink.parsing.monitor.model import MonitorSnapshot
from cremalink.parsing.monitor.view import MonitorView

DEVICES = Path(__file__).resolve().parents[1] / "cremalink" / "devices"

# Eletta Explore, live 20.11.: cold milk carafe on clean (accessory 7, switch bit 15).
COLD_CLEAN = "d012750f07808000000c03170000000000e3486b000516"


def _view(hex_frame, bits=None):
    raw = bytes.fromhex(hex_frame)
    snapshot = MonitorSnapshot(
        raw=raw, raw_b64=base64.b64encode(raw).decode(), received_at=datetime.now()
    )
    return MonitorView(snapshot, switch_bits=bits)


def test_documented_table_without_names():
    assert switch_bits() == dict(sorted(SWITCH_BITS.items()))


def test_model_names_replace_and_add_bits():
    table = switch_bits({"9": "milk_carafe_hot_clean", "15": "milk_carafe_cold_clean"})
    assert table[9].key == "milk_carafe_hot_clean"
    assert table[15].label == "Milk carafe cold clean"
    assert table[4] == SWITCH_BITS[4]


def test_view_decodes_with_the_model_table():
    bits = switch_bits({"15": "milk_carafe_cold_clean"})
    assert _view(COLD_CLEAN, bits).switch_states()["milk_carafe_cold_clean"] is True
    assert "milk_carafe_cold_clean" not in _view(COLD_CLEAN).switch_states()


def test_eletta_map_names_the_carafes():
    device = Device.from_map(None, device_map_path=str(DEVICES / "ECAM452.json"))
    keys = {bit.key for bit in device.switch_bits.values()}
    assert {"milk_carafe_hot", "milk_carafe_hot_clean", "milk_carafe_cold", "milk_carafe_cold_clean"} <= keys
    assert "choco_tank_present" not in keys
