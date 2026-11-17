"""BLE fingerprint matching must be conservative and non-invasive."""

from types import SimpleNamespace

import pytest

from snf.adapters.ble import BLEPlugin
from snf.bluetooth.fingerprints import identify_ble_device


@pytest.mark.parametrize(
    ("company_id", "name", "family"),
    [
        (301, "WH-1000XM5", "1000X headphones"),
        (117, "Galaxy Buds2 Pro", "Galaxy Buds"),
        (196, "LG TONE Free", "LG wireless audio"),
    ],
)
def test_vendor_name_hints_are_explicitly_unverified(company_id, name, family):
    match = identify_ble_device({company_id: b"\x00"}, local_name=name)
    assert match is not None
    assert match["family"] == family
    assert match["confidence"] == "unverified_name_hint"


def test_apple_public_audio_signature_matches_family_not_specific_model():
    match = identify_ble_device({76: bytes.fromhex("0719010e2000")})
    assert match is not None
    assert match["family"] == "AirPods / Beats headphones"
    assert match["confidence"] == "family_signature"


@pytest.mark.parametrize(
    ("data", "name"),
    [
        ({117: b"\x00"}, "WH-1000XM5"),
        ({301: b"\x00"}, "Galaxy Buds2 Pro"),
        ({196: b"\x00"}, "LG OLED TV"),
        ({76: bytes.fromhex("0719")}, "AirPods Pro"),
        ({117: bytes.fromhex("3630325004020000")}, "Room A/C"),
        ({}, "WH-1000XM5"),
    ],
)
def test_ambiguous_or_unrecognized_advertisements_remain_unknown(data, name):
    assert identify_ble_device(data, local_name=name) is None


def test_discovery_adds_fingerprint_without_mutating_raw_data():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="AirPods")
    advertisement = SimpleNamespace(
        local_name="AirPods", rssi=-50, tx_power=None, service_uuids=[],
        manufacturer_data={76: bytes.fromhex("0719010e2000")}, service_data={},
    )
    observation = BLEPlugin._to_device(device, advertisement)
    assert observation.metadata["manufacturer_data"]["76"] == "0719010e2000"
    assert observation.metadata["device_identification"]["brand"] == "Apple/Beats"
