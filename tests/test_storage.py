"""Storage contract and engine integration tests."""

import pytest

from snf import (
    DiscoveryEngine,
    DiscoveryEvent,
    DiscoveryObservation,
    DiscoveryState,
    InMemoryStorage,
)


@pytest.mark.asyncio
async def test_memory_storage_key_value_operations():
    storage = InMemoryStorage()
    mdns = DiscoveryObservation("mdns", "same", "Printer")
    ble = DiscoveryObservation("ble", "same", "Sensor")
    await storage.upsert(mdns)
    await storage.upsert(ble)
    assert await storage.get("mdns", "same") == mdns
    assert await storage.get("ble", "same") == ble
    assert await storage.snapshot(protocol="mdns") == (mdns,)
    assert await storage.snapshot() == (mdns, ble)
    await storage.remove("mdns", "same")
    assert await storage.get("mdns", "same") is None
    assert await storage.snapshot() == (ble,)


@pytest.mark.asyncio
async def test_engine_remembers_removed_devices_without_marking_them_live():
    device = DiscoveryObservation("mdns", "printer", "Printer")

    class Plugin:
        name = "mdns"

        async def start(self):
            pass

        async def discover(self):
            yield DiscoveryEvent(DiscoveryState.ADDED, device)
            yield DiscoveryEvent(DiscoveryState.REMOVED, device)

        async def stop(self):
            pass

    storage = InMemoryStorage()
    async with DiscoveryEngine([Plugin()], storage=storage) as engine:
        events = [event async for event in engine.discover()]
        assert [event.state for event in events] == [
            DiscoveryState.ADDED,
            DiscoveryState.REMOVED,
        ]
        assert engine.snapshot() == ()
        assert await engine.saved_observations(protocol="mdns") == (device,)


def test_storage_is_required():
    with pytest.raises(TypeError, match="storage"):
        DiscoveryEngine([])  # type: ignore[call-arg]
