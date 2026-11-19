"""Favourite drinks per profile (``0xAC``) from a cloud snapshot."""

from __future__ import annotations

import base64

from cremalink.ecam import catalog as ecam_catalog

from tests.test_ecam452_recipe_catalog import _device, _snapshot

# As an Eletta publishes it: profile 1, eleven drinks, one zero padding byte.
D265 = bytes.fromhex("d012acf001080a10e8e6e7e90416ea0200342a")
# Profile 2 has no favourites: all zero padding.
D266 = bytes.fromhex("d012acf0020000000000000000000000009ec1")
FAVORITES_1 = [8, 10, 16, 232, 230, 231, 233, 4, 22, 234, 2]


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_catalogue_parses_favourites_without_padding():
    catalog = ecam_catalog.build_catalog(
        {"d265_favorite_priority_1": _b64(D265), "d266_favorite_priority_2": _b64(D266)}
    )
    assert catalog.favorite_lists == {1: FAVORITES_1, 2: []}
    assert catalog.stats["families"]["favorites"] == 2


def test_seed_makes_the_favourites_available_without_a_machine_read():
    snap = {
        **_snapshot(),
        "d265_favorite_priority_1": _b64(D265),
        "d266_favorite_priority_2": _b64(D266),
    }
    dev = _device(dict(snap))
    assert dev.favorite_beverages(1) is None  # nothing seeded yet
    dev.seed_catalog_from_properties(snap)
    assert dev.favorite_beverages(1) == FAVORITES_1
    assert dev.favorite_beverages(2) == []  # known: no favourites
    assert dev.favorite_beverages(3) is None  # not published
    assert dev.transport.sent == []


def test_favourites_follow_the_active_profile():
    snap = {**_snapshot(), "d266_favorite_priority_2": _b64(D266)}
    dev = _device(dict(snap))
    dev.seed_catalog_from_properties(snap)
    dev.current_profile = 2
    assert dev.favorite_beverages() == []


def test_the_eletta_map_lists_the_favourite_datapoints():
    dev = _device({})
    for n in range(1, 5):
        assert f"d26{4 + n}_favorite_priority_{n}" in dev.catalog_datapoints


# --- writing (0xAD) --------------------------------------------------------

from cremalink.core.binary import crc16_ccitt  # noqa: E402
from cremalink.domain.device import Device  # noqa: E402
from cremalink.ecam.builder import build_set_favorites, verify_frame  # noqa: E402
from cremalink.ecam.machine_profiles import STRIKER  # noqa: E402
from tests.test_ecam452_cloud_datapoints import DEVICES, CloudLikeTransport  # noqa: E402

import pytest  # noqa: E402


def _answer_ac(profile: int, ids: list[int]) -> bytes:
    body = bytes([0xAC, 0xF0, profile]) + bytes(ids) + bytes(12 - len(ids))
    head = bytes([0xD0, len(body) + 3]) + body
    return head + crc16_ccitt(head)


def test_set_favorites_frame_layout():
    frame = build_set_favorites(1, FAVORITES_1, STRIKER)
    assert verify_frame(frame)
    assert frame[:5] == bytes([0x0D, 0x12, 0xAD, 0xF0, 0x01])
    assert list(frame[5:17]) == FAVORITES_1 + [0]  # zero padded to 12
    assert len(frame) == 19


def test_set_favorites_matches_the_published_layout():
    """The write frame is the published 0xAC blob with the command prefix."""
    written = build_set_favorites(1, FAVORITES_1, STRIKER)
    assert written[4:17] == D265[4:17]


@pytest.mark.parametrize(
    "ids",
    [list(range(1, 14)), [8, 8], [0], [256], [-1]],
)
def test_set_favorites_rejects_invalid_lists(ids):
    with pytest.raises(ValueError):
        build_set_favorites(1, ids, STRIKER)


class _FavoritesMachine(CloudLikeTransport):
    """Plays an Eletta: an 0xAD write is republished as d265."""

    def __init__(self, properties, *, applies=True):
        super().__init__(properties)
        self.applies = applies

    def send_command(self, command, alternative_property=None):
        frame = base64.b64decode(command)
        result = super().send_command(command, alternative_property)
        if self.applies and len(frame) > 4 and frame[2] == 0xAD:
            ids = [b for b in frame[5:17] if b]
            self.properties["d265_favorite_priority_1"] = _b64(
                _answer_ac(frame[4], ids)
            )
        return result


def _favorites_device(*, applies=True):
    props = {"app_id": "-1056968978", "d265_favorite_priority_1": _b64(D265)}
    dev = Device.from_map(
        _FavoritesMachine(props, applies=applies),
        device_map_path=str(DEVICES / "ECAM452.json"),
    )
    dev.write_confirm_seconds = 2.0
    dev.app_id_confirm_seconds = 0.0
    dev.app_id_confirm_own_seconds = 0.0
    dev.app_id_confirm_poll = 0.0
    dev.response_poll = 0
    return dev


def test_set_favorite_beverages_confirms_through_the_republished_datapoint():
    dev = _favorites_device()
    new = [10, 8, 2]
    assert dev.set_favorite_beverages(new, 1) is True
    assert dev.favorite_beverages(1) == new
    sent = [f for f, _ in dev.transport.sent if len(f) > 4 and f[2] == 0xAD]
    assert len(sent) == 1
    assert list(sent[0][5:17]) == new + [0] * 9


def test_set_favorite_beverages_reports_an_ignored_write():
    dev = _favorites_device(applies=False)
    assert dev.set_favorite_beverages([10, 8, 2], 1) is False
    assert dev.favorite_beverages(1) is None  # cache untouched


def test_set_favorite_beverages_rejects_an_invalid_list_before_sending():
    dev = _favorites_device()
    with pytest.raises(ValueError):
        dev.set_favorite_beverages([8, 8], 1)
    assert not [f for f, _ in dev.transport.sent if len(f) > 4 and f[2] == 0xAD]
