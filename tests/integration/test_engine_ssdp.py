from __future__ import annotations

import asyncio
import sys
from types import ModuleType

import pytest

from snf import DiscoveryEngine, DiscoveryState, InMemoryStorage
from snf.adapters import ssdp
from snf.adapters.ssdp import SSDPPlugin


@pytest.mark.asyncio
async def test_real_ssdp_adapter_and_engine_with_mocked_network_boundary(monkeypatch):
    """Exercise adapter parsing, event aggregation and registry without UDP."""
    async_upnp_client = ModuleType("async_upnp_client")
    async_upnp_client.__path__ = []
    search_module = ModuleType("async_upnp_client.search")

    monkeypatch.setattr(ssdp, "_default_route_ipv4", lambda: "192.0.2.10")

    async def fake_async_search(*, async_callback, source, timeout, search_target):
        assert source == ("192.0.2.10", 0)
        assert timeout == 2
        assert search_target == "ssdp:all"
        await async_callback(
            {
                "_host": "192.0.2.40",
                "_port": "1400",
                "USN": "uuid:living-room-tv::upnp:rootdevice",
                "ST": "upnp:rootdevice",
                "SERVER": "Test TV/1.0 UPnP/1.1",
                "LOCATION": "http://192.0.2.40:1400/device.xml",
            }
        )
        plugin._running = False

    search_module.async_search = fake_async_search
    monkeypatch.setitem(sys.modules, "async_upnp_client", async_upnp_client)
    monkeypatch.setitem(sys.modules, "async_upnp_client.search", search_module)

    # Bypass optional-package detection: the protocol boundary is replaced above.
    plugin = SSDPPlugin.__new__(SSDPPlugin)
    plugin.search_target = "ssdp:all"
    plugin.search_interval = 0.01
    plugin.search_timeout = 2
    plugin._running = False
    plugin._stop_event = asyncio.Event()

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        events = [event async for event in engine.discover()]
        assert len(events) == 1
        event = events[0]
        assert event.state is DiscoveryState.ADDED
        assert event.observation.protocol == "ssdp"
        assert event.observation.identifier == "uuid:living-room-tv::upnp:rootdevice"
        assert event.observation.name == "Test TV/1.0 UPnP/1.1"
        assert event.observation.endpoints[0].address == "192.0.2.40"
        assert event.observation.endpoints[0].port == 1400
        assert event.observation.services[0].service_type == "upnp:rootdevice"
        assert event.observation.metadata["usn"] == "uuid:living-room-tv::upnp:rootdevice"
        assert event.observation.metadata["udn"] == "uuid:living-room-tv"
        assert engine.get_observation("ssdp", event.observation.identifier) == event.observation


@pytest.mark.asyncio
async def test_ssdp_preserves_distinct_service_advertisements_with_shared_udn(monkeypatch):
    """A shared UPnP UDN is evidence, not an observation de-duplication key."""
    async_upnp_client = ModuleType("async_upnp_client")
    async_upnp_client.__path__ = []
    search_module = ModuleType("async_upnp_client.search")
    usns = (
        "uuid:tv-123::upnp:rootdevice",
        "uuid:tv-123::urn:schemas-upnp-org:service:AVTransport:1",
    )

    monkeypatch.setattr(ssdp, "_default_route_ipv4", lambda: "192.0.2.10")

    async def fake_async_search(*, async_callback, source, timeout, search_target):
        assert source == ("192.0.2.10", 0)
        for usn in usns:
            await async_callback({"_host": "192.0.2.40", "USN": usn, "ST": usn.split("::", 1)[-1]})
        plugin._running = False

    search_module.async_search = fake_async_search
    monkeypatch.setitem(sys.modules, "async_upnp_client", async_upnp_client)
    monkeypatch.setitem(sys.modules, "async_upnp_client.search", search_module)

    plugin = SSDPPlugin.__new__(SSDPPlugin)
    plugin.search_target = "ssdp:all"
    plugin.search_interval = 0.01
    plugin.search_timeout = 2
    plugin._running = False
    plugin._stop_event = asyncio.Event()

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        events = [event async for event in engine.discover()]
        assert len(events) == 2
        assert {event.observation.identifier for event in events} == set(usns)
        assert {event.observation.metadata["udn"] for event in events} == {"uuid:tv-123"}
        assert len(engine.observations) == 2
