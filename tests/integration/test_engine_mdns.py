from __future__ import annotations

import asyncio
import sys
from enum import Enum
from types import ModuleType, SimpleNamespace

import pytest

from snf import DiscoveryEngine, DiscoveryState
from snf.adapters.mdns import MDNSPlugin


class FakeServiceStateChange(Enum):
    Added = "added"
    Removed = "removed"


class FakeServiceInfo:
    server = "tv.local."
    port = 8008
    properties = {b"model": b"test-tv"}

    @staticmethod
    def parsed_addresses():
        return ["192.0.2.55"]


class FakeAsyncZeroconf:
    def __init__(self, *, interfaces):
        self.zeroconf = self
        self.closed = False

    async def async_get_service_info(self, service_type, name, *, timeout):
        assert service_type == "_http._tcp.local."
        assert name == "Test TV._http._tcp.local."
        return FakeServiceInfo()

    async def async_close(self):
        self.closed = True


class FakeAsyncServiceBrowser:
    instances = []

    def __init__(self, zeroconf, service_type, *, handlers):
        self.handlers = handlers
        self.cancelled = False
        self.__class__.instances.append(self)

    async def async_cancel(self):
        self.cancelled = True


@pytest.mark.asyncio
async def test_real_mdns_adapter_and_engine_with_mocked_zeroconf(monkeypatch):
    zeroconf_module = ModuleType("zeroconf")
    zeroconf_module.InterfaceChoice = SimpleNamespace(All="all")
    zeroconf_module.ServiceStateChange = FakeServiceStateChange
    asyncio_module = ModuleType("zeroconf.asyncio")
    asyncio_module.AsyncZeroconf = FakeAsyncZeroconf
    asyncio_module.AsyncServiceBrowser = FakeAsyncServiceBrowser
    asyncio_module.AsyncZeroconfServiceTypes = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "zeroconf", zeroconf_module)
    monkeypatch.setitem(sys.modules, "zeroconf.asyncio", asyncio_module)
    FakeAsyncServiceBrowser.instances.clear()

    plugin = MDNSPlugin.__new__(MDNSPlugin)
    plugin.service_types = ["_http._tcp.local."]
    plugin.resolve_timeout = 100
    plugin.interfaces = None
    plugin.type_discovery_timeout = 0.1
    plugin._events = asyncio.Queue()
    plugin._zeroconf = None
    plugin._browsers = []
    plugin._loop = None

    async with DiscoveryEngine([plugin]) as engine:
        browser = FakeAsyncServiceBrowser.instances[0]
        callback = browser.handlers[0]
        callback(
            plugin._zeroconf.zeroconf,
            "_http._tcp.local.",
            "Test TV._http._tcp.local.",
            FakeServiceStateChange.Added,
        )
        stream = engine.discover()
        event = await asyncio.wait_for(anext(stream), timeout=1)
        await stream.aclose()

        assert event.state is DiscoveryState.ADDED
        assert event.device.protocol == "mdns"
        assert event.device.endpoints[0].address == "192.0.2.55"
        assert event.device.endpoints[0].port == 8008
        assert event.device.services[0].service_type == "_http._tcp.local."
        assert engine.get_device("mdns", event.device.identifier) == event.device

    assert browser.cancelled
