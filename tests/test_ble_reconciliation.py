"""BLE reconciliation, RSSI policy and pending-event coalescing tests."""

import asyncio
from types import SimpleNamespace

import pytest

from snf.adapters.ble import BLEPlugin
from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState


def plugin(*, emit_rssi_updates=False):
    instance = BLEPlugin.__new__(BLEPlugin)
    instance._running = True
    instance._events = asyncio.Queue()
    instance._pending = {}
    instance._last_seen = {}
    instance._last_emitted = {}
    instance.emit_rssi_updates = emit_rssi_updates
    instance.rssi_update_threshold = 5
    return instance


def advertisement(*, name=None, rssi=-60, services=(), manufacturer=None, data=None):
    return SimpleNamespace(
        local_name=name,
        rssi=rssi,
        tx_power=None,
        service_uuids=list(services),
        manufacturer_data=manufacturer or {},
        service_data=data or {},
    )


def device(address="AA:BB:CC:DD:EE:FF"):
    return SimpleNamespace(address=address, name=None)


@pytest.mark.asyncio
async def test_partial_advertisements_reconcile_before_enqueue():
    p = plugin()
    d = device()
    p._on_advertisement(d, advertisement(
        name="Living Room", services=("180f",), manufacturer={76: b"\x01"}
    ))
    p._on_advertisement(d, advertisement(
        rssi=-62, data={"180a": b"\x02"}
    ))
    latest = p._pending[d.address][-1].observation
    assert latest.name == "Living Room"
    assert latest.metadata["manufacturer_data"] == {"76": "01"}
    assert latest.metadata["service_data"] == {"180a": "02"}
    assert latest.metadata["service_uuids"] == ("180f",)
    assert p._events.qsize() == 1


@pytest.mark.asyncio
async def test_rssi_only_changes_suppressed_by_default_but_refresh_last_seen():
    p = plugin()
    d = device()
    p._on_advertisement(d, advertisement(rssi=-70))
    first_seen = p._last_seen[d.address]
    p._on_advertisement(d, advertisement(rssi=-40))
    assert p._events.qsize() == 1
    assert p._last_seen[d.address] >= first_seen
    assert p._last_emitted[d.address].metadata["rssi"] == -40


@pytest.mark.asyncio
async def test_rssi_updates_enabled_and_threshold_applied():
    p = plugin(emit_rssi_updates=True)
    d = device()
    p._on_advertisement(d, advertisement(rssi=-70))
    p._on_advertisement(d, advertisement(rssi=-67))
    assert p._pending[d.address][-1].observation.metadata["rssi"] == -70
    p._on_advertisement(d, advertisement(rssi=-60))
    assert p._pending[d.address][-1].observation.metadata["rssi"] == -60
    assert p._events.qsize() == 1


@pytest.mark.asyncio
async def test_pending_updates_coalesce_per_device():
    p = plugin()
    for address in ("A", "B", "C"):
        p._on_advertisement(device(address), advertisement())
    assert p._events.qsize() == 3
    for rssi in range(-80, -40):
        p._on_advertisement(device("A"), advertisement(rssi=rssi))
    assert p._events.qsize() == 3
    assert len(p._pending) == 3


@pytest.mark.asyncio
async def test_removal_then_rediscovery_preserves_lifecycle():
    p = plugin()
    d = device()
    p._on_advertisement(d, advertisement(name="Sensor"))
    p._last_emitted.pop(d.address)
    p._last_seen.pop(d.address)
    p._enqueue(DiscoveryEvent(
        DiscoveryState.REMOVED,
        DiscoveryObservation(
            protocol="ble", identifier=d.address, name=d.address
        ),
    ))
    p._on_advertisement(d, advertisement(name="Sensor"))
    assert [event.state for event in p._pending[d.address]] == [
        DiscoveryState.ADDED, DiscoveryState.REMOVED, DiscoveryState.ADDED
    ]
    assert p._events.qsize() == 1
