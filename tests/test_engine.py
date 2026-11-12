import pytest

from snf.engine import DiscoveryEngine
from snf.models import Service, ServiceState
from snf.registry import ServiceRegistry


class FakePlugin:
    name = "fake"

    def __init__(self, events=None):
        self.started = False
        self.stopped = False
        self.events = events or [Service(protocol=self.name, name="test", address="127.0.0.1")]

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
        results = [service async for service in engine.discover()]
        assert len(results) == 1
        assert results[0].address == "127.0.0.1"
    assert plugin.stopped


@pytest.mark.asyncio
async def test_engine_requires_context_manager():
    engine = DiscoveryEngine([])
    with pytest.raises(RuntimeError):
        _ = [service async for service in engine.discover()]


@pytest.mark.asyncio
async def test_engine_suppresses_duplicate_announcements():
    announcement = Service(protocol="ssdp", name="uuid:device-1", address="192.0.2.10")
    plugin = FakePlugin([announcement, announcement, announcement])
    async with DiscoveryEngine([plugin]) as engine:
        events = [event async for event in engine.discover()]
    assert events == [announcement]


@pytest.mark.asyncio
async def test_engine_emits_update_when_endpoint_changes():
    initial = Service(protocol="ssdp", name="uuid:device-1", address="192.0.2.10")
    changed = Service(protocol="ssdp", name="uuid:device-1", address="192.0.2.11")
    plugin = FakePlugin([initial, changed])
    async with DiscoveryEngine([plugin]) as engine:
        events = [event async for event in engine.discover()]
    assert len(events) == 2
    assert events[1].state is ServiceState.UPDATED
    assert events[1].address == "192.0.2.11"


def test_registry_removal_allows_service_to_be_added_again():
    registry = ServiceRegistry()
    service = Service(protocol="mdns", name="printer._ipp._tcp.local.", address="192.0.2.20")
    removed = Service(
        protocol="mdns",
        name=service.name,
        address="",
        state=ServiceState.REMOVED,
    )
    assert registry.process(service) == service
    assert registry.process(service) is None
    assert registry.process(removed) == removed
    assert registry.process(service) == service


def test_registry_is_bounded():
    registry = ServiceRegistry(max_entries=1)
    first = Service(protocol="mdns", name="one", address="192.0.2.1")
    second = Service(protocol="mdns", name="two", address="192.0.2.2")
    registry.process(first)
    registry.process(second)
    assert len(registry) == 1
