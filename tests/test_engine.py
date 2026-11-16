import asyncio

import pytest

from snf.engine import DiscoveryEngine
from snf.models import (
    Device,
    DiscoveryEvent,
    DiscoveryState,
    Endpoint,
    Service,
)
from snf.registry import DeviceRegistry


class FakePlugin:
    name = "fake"

    def __init__(self, events=None):
        self.started = False
        self.stopped = False
        self.events = events if events is not None else [
            DiscoveryEvent(
                DiscoveryState.ADDED,
                Device(
                    protocol=self.name,
                    identifier="device-1",
                    name="test",
                    endpoints=(Endpoint("ip", "127.0.0.1"),),
                ),
            )
        ]

    async def start(self):
        self.started = True

    async def discover(self):
        for event in self.events:
            yield event

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_engine_lifecycle_and_discovery():
    plugin = FakePlugin()
    async with DiscoveryEngine([plugin]) as engine:
        assert plugin.started
        results = [event async for event in engine.discover()]
        assert len(results) == 1
        assert results[0].device.name == "test"
        assert engine.devices == (results[0].device,)
    assert plugin.stopped


@pytest.mark.asyncio
async def test_engine_starts_plugins_concurrently():
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    class CoordinatedPlugin(FakePlugin):
        def __init__(self, name, own_started, peer_started):
            self.name = name
            self.own_started = own_started
            self.peer_started = peer_started
            super().__init__(events=[])

        async def start(self):
            self.started = True
            self.own_started.set()
            await asyncio.wait_for(self.peer_started.wait(), timeout=1)

    first = CoordinatedPlugin("first", first_started, second_started)
    second = CoordinatedPlugin("second", second_started, first_started)

    async with DiscoveryEngine([first, second]):
        assert first.started
        assert second.started

    assert first.stopped
    assert second.stopped


@pytest.mark.asyncio
async def test_engine_cleans_up_all_plugins_when_startup_fails():
    class FailingPlugin(FakePlugin):
        name = "failing"

        async def start(self):
            self.started = True
            raise RuntimeError("startup failed")

    healthy = FakePlugin()
    failing = FailingPlugin()

    with pytest.raises(RuntimeError, match="startup failed"):
        async with DiscoveryEngine([healthy, failing]):
            pytest.fail("The context manager must not be entered")

    assert healthy.started
    assert failing.started
    assert healthy.stopped
    assert failing.stopped


@pytest.mark.asyncio
async def test_engine_requires_context_manager():
    engine = DiscoveryEngine([])
    with pytest.raises(RuntimeError):
        _ = [event async for event in engine.discover()]


@pytest.mark.asyncio
async def test_engine_suppresses_duplicate_announcements_and_updates_inventory():
    device = Device(
        protocol="ssdp",
        identifier="uuid:device-1",
        name="Living room TV",
        endpoints=(Endpoint("ip", "192.0.2.10", 1400),),
    )
    plugin = FakePlugin([
        DiscoveryEvent(DiscoveryState.ADDED, device),
        DiscoveryEvent(DiscoveryState.ADDED, device),
    ])
    async with DiscoveryEngine([plugin]) as engine:
        events = [event async for event in engine.discover()]
        assert engine.get_device("ssdp", "uuid:device-1") == device
    assert len(events) == 1
    assert events[0].state is DiscoveryState.ADDED


@pytest.mark.asyncio
async def test_engine_emits_update_when_device_changes():
    initial = Device(
        "ssdp", "uuid:device-1", "TV", (Endpoint("ip", "192.0.2.10", 1400),)
    )
    changed = Device(
        "ssdp", "uuid:device-1", "TV", (Endpoint("ip", "192.0.2.11", 1400),)
    )
    plugin = FakePlugin([
        DiscoveryEvent(DiscoveryState.ADDED, initial),
        DiscoveryEvent(DiscoveryState.ADDED, changed),
    ])
    async with DiscoveryEngine([plugin]) as engine:
        events = [event async for event in engine.discover()]
    assert [event.state for event in events] == [
        DiscoveryState.ADDED, DiscoveryState.UPDATED
    ]
    assert events[1].device.endpoints[0].address == "192.0.2.11"


def test_registry_removal_allows_device_to_be_added_again():
    registry = DeviceRegistry()
    device = Device("mdns", "printer", "Printer")
    added = DiscoveryEvent(DiscoveryState.ADDED, device)
    removed = DiscoveryEvent(DiscoveryState.REMOVED, device)
    assert registry.process(added) == added
    assert registry.process(added) is None
    assert registry.process(removed) == removed
    assert registry.process(added) == added


def test_registry_is_bounded():
    registry = DeviceRegistry(max_entries=1)
    registry.process(DiscoveryEvent(DiscoveryState.ADDED, Device("mdns", "one", "One")))
    registry.process(DiscoveryEvent(DiscoveryState.ADDED, Device("mdns", "two", "Two")))
    assert len(registry) == 1


def test_service_is_nested_in_device():
    endpoint = Endpoint("ip", "192.0.2.20", 80)
    service = Service("http", "_http._tcp.local.", (endpoint,))
    device = Device("mdns", "web-1", "Web server", (endpoint,), (service,))
    assert device.services[0].endpoints[0].port == 80
