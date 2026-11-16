from __future__ import annotations

import asyncio
import sys
from types import ModuleType

import pytest

from snf import DiscoveryEngine, DiscoveryState
from snf.adapters.ssdp import SSDPPlugin


@pytest.mark.asyncio
async def test_real_ssdp_adapter_and_engine_with_mocked_network_boundary(monkeypatch):
    """Exercise adapter parsing, event aggregation and registry without UDP."""
    async_upnp_client = ModuleType("async_upnp_client")
    async_upnp_client.__path__ = []
    search_module = ModuleType("async_upnp_client.search")

    async def fake_async_search(*, async_callback, timeout, search_target):
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
    plugin.search_interval = 30.0
    plugin.search_timeout = 2
    plugin._running = False
    plugin._stop_event = asyncio.Event()

    async with DiscoveryEngine([plugin]) as engine:
        events = [event async for event in engine.discover()]
        assert len(events) == 1
        event = events[0]
        assert event.state is DiscoveryState.ADDED
        assert event.device.protocol == "ssdp"
        assert event.device.identifier == "uuid:living-room-tv::upnp:rootdevice"
        assert event.device.name == "Test TV/1.0 UPnP/1.1"
        assert event.device.endpoints[0].address == "192.0.2.40"
        assert event.device.endpoints[0].port == 1400
        assert event.device.services[0].service_type == "upnp:rootdevice"
        assert engine.get_device("ssdp", event.device.identifier) == event.device
