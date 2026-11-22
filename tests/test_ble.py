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
    plugin._delivered_rssi = {}
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


def test_ble_reconciliation_preserves_partial_advertisement_evidence():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Sensor")
    first = SimpleNamespace(
        local_name="Room Sensor",
        rssi=-60,
        tx_power=4,
        service_uuids=["180f"],
        manufacturer_data={76: b"\x01\x02"},
        service_data={"180f": b"\x03"},
    )
    partial = SimpleNamespace(
        local_name=None,
        rssi=-62,
        tx_power=None,
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )

    previous = BLEPlugin._to_device(device, first)
    current = BLEPlugin._to_device(device, partial)
    reconciled = BLEPlugin._reconcile(previous, current)

    assert reconciled.name == "Room Sensor"
    assert reconciled.metadata["tx_power"] == 4
    assert reconciled.metadata["rssi"] == -62
    assert reconciled.metadata["manufacturer_data"] == {"76": "0102"}
    assert reconciled.metadata["service_data"] == {"180f": "03"}
    assert reconciled.metadata["service_uuids"] == ("180f",)
    assert reconciled.metadata["company_names"] == previous.metadata["company_names"]
    assert reconciled.metadata["service_names"] == previous.metadata["service_names"]
    assert reconciled.metadata["device_identification"] == previous.metadata["device_identification"]


@pytest.mark.parametrize(
    ("previous_rssi", "current_rssi", "expected"),
    [(-60, -64, False), (-60, -65, True), (-60, -66, True)],
)
def test_ble_rssi_threshold_boundaries(previous_rssi, current_rssi, expected):
    plugin = BLEPlugin.__new__(BLEPlugin)
    plugin.emit_rssi_updates = True
    plugin.rssi_update_threshold = 5
    plugin._pending = {}
    plugin._delivered_rssi = {"device": previous_rssi}

    assert plugin._is_rssi_change_significant("device", current_rssi) is expected


def test_ble_rssi_pending_event_takes_precedence_over_delivered_value():
    from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState

    plugin = BLEPlugin.__new__(BLEPlugin)
    plugin.emit_rssi_updates = True
    plugin.rssi_update_threshold = 5
    plugin._delivered_rssi = {"device": -60}
    observation = DiscoveryObservation(
        protocol="ble", identifier="device", name="Device", metadata={"rssi": -70}
    )
    plugin._pending = {"device": [DiscoveryEvent(DiscoveryState.ADDED, observation)]}

    assert plugin._baseline_rssi("device") == -70
    assert not plugin._is_rssi_change_significant("device", -67)
    assert plugin._is_rssi_change_significant("device", -65)
