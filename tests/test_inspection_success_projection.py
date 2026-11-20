"""Characterize inspection success response projection."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sse_starlette")

from snf.api.inspection_responses import ble_success, mdns_success
from snf.inspection.ble import BLECharacteristicDetails, BLEDeviceDetails, BLEServiceDetails
from snf.inspection.mdns import MDNSServiceDetails


def test_ble_response_exposes_only_existing_public_fields():
    device = BLEDeviceDetails(
        identifier="AA:BB",
        services=(BLEServiceDetails(
            uuid="1800",
            name="Generic Access",
            characteristics=(BLECharacteristicDetails(
                uuid="2a00", name="Device Name", properties=("read",),
                descriptors=("2901",), descriptor_names=("User Description",),
            ),),
        ),),
    )
    response = ble_success(device).model_dump()
    assert response["identifier"] == "AA:BB"
    assert response["services"][0]["characteristics"][0] == {
        "uuid": "2a00", "properties": ("read",), "descriptors": ("2901",)
    }
    assert response["error"] == {}


def test_mdns_response_preserves_properties_and_error_object():
    details = MDNSServiceDetails(
        instance_name="TV", service_type="_airplay._tcp.local.",
        server="tv.local.", port=7000, addresses=("192.168.1.2",),
        properties={"model": "TV"},
    )
    response = mdns_success(details).model_dump()
    assert response["properties"] == {"model": "TV"}
    assert response["error"] == {}
