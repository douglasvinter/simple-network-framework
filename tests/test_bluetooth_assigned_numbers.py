"""Regression tests for offline Bluetooth assigned-number enrichment."""

from types import SimpleNamespace

from snf.adapters.ble import BLEPlugin
from snf.bluetooth.assigned_numbers import appearance_details, company_name, uuid_details


def test_company_identifiers_cover_multiple_vendors():
    assert "Samsung" in company_name(117)
    assert "Apple" in company_name(76)
    assert "Fujitsu" in company_name(746)
    assert company_name(65534) is None


def test_standard_and_vendor_uuid_resolution():
    assert uuid_details("180f", kind="service")["name"] == "Battery Service"
    assert uuid_details(
        "0000180F-0000-1000-8000-00805F9B34FB", kind="service"
    )["name"] == "Battery Service"
    assert uuid_details("2a19", kind="characteristic") is not None
    assert uuid_details("2902", kind="descriptor") is not None
    assert uuid_details("ffffffff-ffff-ffff-ffff-ffffffffffff", kind="service") is None


def test_appearance_categories():
    assert appearance_details(64)["category"] == "Phone"
    assert appearance_details(-1) is None


def test_ble_advertisement_preserves_raw_data_and_adds_names():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Room A/C")
    advertisement = SimpleNamespace(
        local_name="Room A/C",
        rssi=-74,
        tx_power=None,
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={117: bytes.fromhex("3630325004020000")},
        service_data={"180f": b"\x01"},
    )
    result = BLEPlugin._to_device(device, advertisement)
    assert result.metadata["manufacturer_data"] == {"117": "3630325004020000"}
    assert "Samsung" in result.metadata["company_names"]["117"]
    assert result.metadata["service_names"][
        "0000180f-0000-1000-8000-00805f9b34fb"
    ] == "Battery Service"
    assert result.metadata["service_data_names"]["180f"] == "Battery Service"
