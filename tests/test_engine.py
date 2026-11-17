import asyncio

import pytest

from snf.engine import DiscoveryEngine
from snf.models import (
    DiscoveryEvent,
    DiscoveryObservation,
    DiscoveryState,
    Endpoint,
    Service,
)
from snf.registry import ObservationRegistry
from snf.storage import InMemoryStorage


class FakePlugin:
    name = "fake"

    def __init__(self, events=None):
        self.started = False
        self.stopped = False
        self.events = (
            events
            if events is not None
            else [
                DiscoveryEvent(
                    DiscoveryState.ADDED,
                    DiscoveryObservation(
                        protocol=self.name,
                        identifier="device-1",
                        name="test",
                        endpoints=(Endpoint("ip", "127.0.0.1"),),
                    ),
                )
            ]
        )

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
    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        assert plugin.started
        results = [event async for event in engine.discover()]
        assert len(results) == 1
        assert results[0].observation.name == "test"
        assert engine.observations == (results[0].observation,)
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

    async with DiscoveryEngine([first, second], storage=InMemoryStorage()):
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
        async with DiscoveryEngine([healthy, failing], storage=InMemoryStorage(), strict=True):
            pytest.fail("The context manager must not be entered")

    assert healthy.started
    assert failing.started
    assert healthy.stopped
    assert failing.stopped


@pytest.mark.asyncio
async def test_engine_requires_context_manager():
    engine = DiscoveryEngine([], storage=InMemoryStorage())
    with pytest.raises(RuntimeError):
        _ = [event async for event in engine.discover()]


@pytest.mark.asyncio
async def test_engine_suppresses_duplicate_announcements_and_updates_inventory():
    device = DiscoveryObservation(
        protocol="ssdp",
        identifier="uuid:device-1",
        name="Living room TV",
        endpoints=(Endpoint("ip", "192.0.2.10", 1400),),
    )
    plugin = FakePlugin(
        [
            DiscoveryEvent(DiscoveryState.ADDED, device),
            DiscoveryEvent(DiscoveryState.ADDED, device),
        ]
    )
    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        events = [event async for event in engine.discover()]
        assert engine.get_observation("ssdp", "uuid:device-1") == device
    assert len(events) == 1
    assert events[0].state is DiscoveryState.ADDED


@pytest.mark.asyncio
async def test_engine_emits_update_when_device_changes():
    initial = DiscoveryObservation(
        "ssdp", "uuid:device-1", "TV", (Endpoint("ip", "192.0.2.10", 1400),)
    )
    changed = DiscoveryObservation(
        "ssdp", "uuid:device-1", "TV", (Endpoint("ip", "192.0.2.11", 1400),)
    )
    plugin = FakePlugin(
        [
            DiscoveryEvent(DiscoveryState.ADDED, initial),
            DiscoveryEvent(DiscoveryState.ADDED, changed),
        ]
    )
    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        events = [event async for event in engine.discover()]
    assert [event.state for event in events] == [DiscoveryState.ADDED, DiscoveryState.UPDATED]
    assert events[1].observation.endpoints[0].address == "192.0.2.11"


def test_registry_removal_allows_device_to_be_added_again():
    registry = ObservationRegistry()
    device = DiscoveryObservation("mdns", "printer", "Printer")
    added = DiscoveryEvent(DiscoveryState.ADDED, device)
    removed = DiscoveryEvent(DiscoveryState.REMOVED, device)
    assert registry.process(added) == added
    assert registry.process(added) is None
    assert registry.process(removed) == removed
    assert registry.process(added) == added


def test_registry_is_bounded():
    registry = ObservationRegistry(max_entries=1)
    registry.process(
        DiscoveryEvent(DiscoveryState.ADDED, DiscoveryObservation("mdns", "one", "One"))
    )
    registry.process(
        DiscoveryEvent(DiscoveryState.ADDED, DiscoveryObservation("mdns", "two", "Two"))
    )
    assert len(registry) == 1


def test_service_is_nested_in_device():
    endpoint = Endpoint("ip", "192.0.2.20", 80)
    service = Service("http", "_http._tcp.local.", (endpoint,))
    device = DiscoveryObservation("mdns", "web-1", "Web server", (endpoint,), (service,))
    assert device.services[0].endpoints[0].port == 80


@pytest.mark.asyncio
async def test_engine_skips_failed_start_and_keeps_healthy_plugin(caplog):
    class FailingPlugin(FakePlugin):
        name = "failing"

        async def start(self):
            self.started = True
            raise RuntimeError("cannot start")

    healthy = FakePlugin()
    failing = FailingPlugin()
    with caplog.at_level("ERROR", logger="snf.engine"):
        async with DiscoveryEngine([failing, healthy], storage=InMemoryStorage()) as engine:
            events = [event async for event in engine.discover()]

    assert len(events) == 1
    assert events[0].observation.name == "test"
    assert healthy.stopped and failing.stopped
    assert "Failed to start discovery plugin failing" in caplog.text


@pytest.mark.asyncio
async def test_engine_with_all_failed_plugins_returns_empty_stream():
    class FailingPlugin(FakePlugin):
        async def start(self):
            raise RuntimeError("cannot start")

    failing = FailingPlugin()
    async with DiscoveryEngine([failing], storage=InMemoryStorage()) as engine:
        assert [event async for event in engine.discover()] == []
    assert failing.stopped


def test_registry_snapshot_filters_protocol_without_changing_inventory():
    registry = ObservationRegistry()
    mdns = DiscoveryObservation("mdns", "one", "Printer")
    ssdp = DiscoveryObservation("ssdp", "two", "TV")
    registry.process(DiscoveryEvent(DiscoveryState.ADDED, mdns))
    registry.process(DiscoveryEvent(DiscoveryState.ADDED, ssdp))

    assert registry.snapshot() == (mdns, ssdp)
    assert registry.snapshot(protocol="mdns") == (mdns,)
    assert registry.snapshot(protocol="ssdp") == (ssdp,)
    assert registry.snapshot(protocol="ble") == ()
    assert registry.snapshot() == (mdns, ssdp)


@pytest.mark.asyncio
async def test_engine_snapshot_filters_protocol_and_preserves_devices_property():
    mdns = DiscoveryObservation("mdns", "one", "Printer")
    ssdp = DiscoveryObservation("ssdp", "two", "TV")
    plugin = FakePlugin(
        [
            DiscoveryEvent(DiscoveryState.ADDED, mdns),
            DiscoveryEvent(DiscoveryState.ADDED, ssdp),
        ]
    )

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        _ = [event async for event in engine.discover()]
        assert engine.snapshot() == engine.observations == (mdns, ssdp)
        assert engine.snapshot(protocol="mdns") == (mdns,)
        assert engine.snapshot(protocol="ssdp") == (ssdp,)
        assert engine.snapshot(protocol="slp") == ()


def test_registry_eviction_is_not_device_removal():
    registry = ObservationRegistry(max_entries=1)
    first = DiscoveryObservation("mdns", "one", "Printer")
    second = DiscoveryObservation("mdns", "two", "TV")

    assert registry.process_events(DiscoveryEvent(DiscoveryState.ADDED, first)) == (
        DiscoveryEvent(DiscoveryState.ADDED, first),
    )
    assert registry.process_events(DiscoveryEvent(DiscoveryState.ADDED, second)) == (
        DiscoveryEvent(DiscoveryState.EVICTED, first),
        DiscoveryEvent(DiscoveryState.ADDED, second),
    )
    assert registry.snapshot() == (second,)
    assert registry.process_events(DiscoveryEvent(DiscoveryState.REMOVED, first)) == ()
    assert registry.process_events(DiscoveryEvent(DiscoveryState.ADDED, first)) == (
        DiscoveryEvent(DiscoveryState.EVICTED, second),
        DiscoveryEvent(DiscoveryState.ADDED, first),
    )


def test_registry_rejects_plugin_generated_eviction():
    registry = ObservationRegistry(max_entries=1)
    observation = DiscoveryObservation("mdns", "one", "Printer")
    with pytest.raises(ValueError, match="registry-generated"):
        registry.process_events(DiscoveryEvent(DiscoveryState.EVICTED, observation))


def test_registry_repeated_observation_does_not_evict():
    registry = ObservationRegistry(max_entries=1)
    observation = DiscoveryObservation("mdns", "one", "Printer")
    registry.process_events(DiscoveryEvent(DiscoveryState.ADDED, observation))
    assert registry.process_events(DiscoveryEvent(DiscoveryState.ADDED, observation)) == ()
    assert registry.snapshot() == (observation,)


@pytest.mark.asyncio
async def test_engine_eviction_keeps_remembered_observation():
    first = DiscoveryObservation("mdns", "one", "Printer")
    second = DiscoveryObservation("mdns", "two", "TV")
    plugin = FakePlugin([
        DiscoveryEvent(DiscoveryState.ADDED, first),
        DiscoveryEvent(DiscoveryState.ADDED, second),
    ])
    storage = InMemoryStorage()
    async with DiscoveryEngine([plugin], storage=storage, dedupe_cache_size=1) as engine:
        events = [event async for event in engine.discover()]
        assert engine.snapshot() == (second,)
        assert await engine.saved_observations() == (first, second)
    assert [(event.state, event.observation.identifier) for event in events] == [
        (DiscoveryState.ADDED, "one"),
        (DiscoveryState.EVICTED, "one"),
        (DiscoveryState.ADDED, "two"),
    ]
