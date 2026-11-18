import asyncio
from types import SimpleNamespace

import pytest

from snf.adapters.ble import BLEPlugin


def test_ble_advertisement_is_normalized_without_connecting():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Sensor")
    advertisement = SimpleNamespace(
        local_name="Room Sensor",
        rssi=-61,
        tx_power=4,
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={76: b"\x01\x02"},
        service_data={"180f": b"\x03"},
    )
    result = BLEPlugin._to_device(device, advertisement)

    assert result.protocol == "ble"
    assert result.identifier == "AA:BB:CC:DD:EE:FF"
    assert result.name == "Room Sensor"
    assert result.endpoints[0].transport == "ble"
    assert result.metadata["rssi"] == -61
    assert result.metadata["manufacturer_data"] == {"76": "0102"}
    assert result.services[0].service_type == "bluetooth-le-advertised-service"


@pytest.mark.asyncio
async def test_ble_suppresses_small_rssi_fluctuations():
    plugin = BLEPlugin.__new__(BLEPlugin)
    plugin._running = True
    plugin._events = asyncio.Queue()
    plugin._last_seen = {}
    plugin._last_emitted = {}
    plugin._pending = {}
    plugin.emit_rssi_updates = True
    plugin.rssi_update_threshold = 5

    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Sensor")
    advertisement = SimpleNamespace(
        local_name="Room Sensor",
        rssi=-60,
        tx_power=4,
        service_uuids=["180f"],
        manufacturer_data={},
        service_data={},
    )
    plugin._on_advertisement(device, advertisement)
    advertisement.rssi = -62
    plugin._on_advertisement(device, advertisement)
    assert plugin._events.qsize() == 1

    advertisement.rssi = -66
    plugin._on_advertisement(device, advertisement)
    assert plugin._events.qsize() == 1
    assert plugin._pending[device.address][-1].observation.metadata["rssi"] == -66
