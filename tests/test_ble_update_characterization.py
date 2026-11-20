"""Characterize BLE RSSI coalescing decisions before extracting callback logic."""

from snf.adapters.ble import BLEPlugin
from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState


def _observation(rssi: int, name: str = "device") -> DiscoveryObservation:
    return DiscoveryObservation(
        protocol="ble", identifier="AA:BB", name=name, metadata={"rssi": rssi}
    )


def test_rssi_threshold_uses_pending_event_not_latest_advertisement():
    plugin = object.__new__(BLEPlugin)
    plugin.emit_rssi_updates = True
    plugin.rssi_update_threshold = 5
    plugin._pending = {
        "AA:BB": [DiscoveryEvent(DiscoveryState.ADDED, _observation(-60))]
    }
    plugin._delivered_rssi = {"AA:BB": -70}
    assert plugin._should_emit_update("AA:BB", _observation(-62), _observation(-65))
    assert not plugin._should_emit_update("AA:BB", _observation(-62), _observation(-64))


def test_rssi_threshold_uses_delivered_event_after_pending_removal():
    plugin = object.__new__(BLEPlugin)
    plugin.emit_rssi_updates = True
    plugin.rssi_update_threshold = 5
    plugin._pending = {
        "AA:BB": [DiscoveryEvent(DiscoveryState.REMOVED, _observation(-50))]
    }
    plugin._delivered_rssi = {"AA:BB": -70}
    assert plugin._should_emit_update("AA:BB", _observation(-65), _observation(-65))


def test_non_rssi_changes_are_emitted_even_when_rssi_updates_disabled():
    plugin = object.__new__(BLEPlugin)
    plugin.emit_rssi_updates = False
    plugin.rssi_update_threshold = 5
    plugin._pending = {}
    plugin._delivered_rssi = {}
    assert plugin._should_emit_update("AA:BB", _observation(-60), _observation(-60, "new"))
    assert not plugin._should_emit_update("AA:BB", _observation(-60), _observation(-70))
