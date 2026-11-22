"""Characterization tests for the mDNS adapter's existing behavior."""

from __future__ import annotations

import asyncio
import sys
from enum import Enum
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from snf.adapters.mdns import MDNSPlugin, _decode_properties, _observation_from_service_info
from snf.models import DiscoveryState


class StateChange(Enum):
    Added = "added"
    Removed = "removed"


@pytest.fixture
def zeroconf_stubs(monkeypatch):
    module = ModuleType("zeroconf")
    module.__path__ = []
    module.InterfaceChoice = SimpleNamespace(All="all")
    module.ServiceStateChange = StateChange

    async_module = ModuleType("zeroconf.asyncio")
    instance = SimpleNamespace(
        zeroconf=object(),
        async_get_service_info=AsyncMock(),
        async_close=AsyncMock(),
    )
    factory = MagicMock(return_value=instance)
    browser = MagicMock()
    browser.async_cancel = AsyncMock()
    browser_factory = MagicMock(return_value=browser)
    discover = AsyncMock(return_value={"_http._tcp.local."})
    async_module.AsyncZeroconf = factory
    async_module.AsyncServiceBrowser = browser_factory
    async_module.AsyncZeroconfServiceTypes = SimpleNamespace(async_find=discover)

    monkeypatch.setitem(sys.modules, "zeroconf", module)
    monkeypatch.setitem(sys.modules, "zeroconf.asyncio", async_module)
    return SimpleNamespace(
        instance=instance,
        factory=factory,
        browser=browser,
        browser_factory=browser_factory,
        discover=discover,
    )


def plugin_without_dependency_check(service_types=None):
    plugin = MDNSPlugin.__new__(MDNSPlugin)
    plugin.service_types = service_types
    plugin.resolve_timeout = 3000
    plugin.interfaces = None
    plugin.type_discovery_timeout = 3.0
    plugin._events = asyncio.Queue()
    plugin._zeroconf = None
    plugin._browsers = []
    plugin._loop = None
    return plugin


def test_txt_decoding_preserves_replacement_and_empty_values():
    assert _decode_properties({b"name": b"TV", b"invalid": bytes([255]), "empty": None, 3: 7}) == {
        "name": "TV", "invalid": "�", "empty": "", "3": "7",
    }


def test_service_projection_preserves_metadata_and_endpoints():
    info = SimpleNamespace(
        properties={b"model": b"TV"}, server="tv.local.", port=8008,
    )
    result = _observation_from_service_info(
        "_http._tcp.local.", "TV._http._tcp.local.", info, ["192.0.2.1", "fe80::1"]
    )
    assert result.identifier == "_http._tcp.local.|TV._http._tcp.local."
    assert result.protocol == "mdns"
    assert [endpoint.address for endpoint in result.endpoints] == ["192.0.2.1", "fe80::1"]
    assert result.services[0].endpoints == result.endpoints
    assert result.metadata == {"server": "tv.local.", "properties": {"model": "TV"}}


@pytest.mark.asyncio
async def test_start_discovers_types_when_not_configured(zeroconf_stubs):
    plugin = plugin_without_dependency_check()
    await plugin.start()
    zeroconf_stubs.factory.assert_called_once_with(interfaces="all")
    zeroconf_stubs.discover.assert_awaited_once_with(
        aiozc=zeroconf_stubs.instance, timeout=3.0
    )
    zeroconf_stubs.browser_factory.assert_called_once_with(
        zeroconf_stubs.instance.zeroconf,
        "_http._tcp.local.",
        handlers=[plugin._on_service_state_change],
    )
    await plugin.stop()
    zeroconf_stubs.browser.async_cancel.assert_awaited_once()
    zeroconf_stubs.instance.async_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_uses_explicit_types_without_discovery(zeroconf_stubs):
    plugin = plugin_without_dependency_check(["_airplay._tcp.local."])
    await plugin.start()
    zeroconf_stubs.discover.assert_not_awaited()
    assert zeroconf_stubs.browser_factory.call_args.args[1] == "_airplay._tcp.local."
    await plugin.stop()


@pytest.mark.asyncio
async def test_resolve_emits_added_and_removed(zeroconf_stubs):
    plugin = plugin_without_dependency_check()
    plugin._zeroconf = zeroconf_stubs.instance
    info = SimpleNamespace(
        properties={b"model": b"TV"}, server="tv.local.", port=8008,
        parsed_addresses=lambda: ["192.0.2.55"],
    )
    zeroconf_stubs.instance.async_get_service_info.return_value = info
    await plugin._resolve("_http._tcp.local.", "TV", StateChange.Added)
    added = plugin._events.get_nowait()
    assert added.state is DiscoveryState.ADDED
    assert added.observation.endpoints[0].address == "192.0.2.55"

    await plugin._resolve("_http._tcp.local.", "TV", StateChange.Removed)
    removed = plugin._events.get_nowait()
    assert removed.state is DiscoveryState.REMOVED
    assert removed.observation.identifier == added.observation.identifier
    assert removed.observation.endpoints == ()
    zeroconf_stubs.instance.async_get_service_info.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_skips_missing_info_or_addresses(zeroconf_stubs):
    plugin = plugin_without_dependency_check()
    plugin._zeroconf = zeroconf_stubs.instance
    zeroconf_stubs.instance.async_get_service_info.return_value = None
    await plugin._resolve("_http._tcp.local.", "TV", StateChange.Added)
    zeroconf_stubs.instance.async_get_service_info.return_value = SimpleNamespace(
        parsed_addresses=lambda: []
    )
    await plugin._resolve("_http._tcp.local.", "TV", StateChange.Added)
    assert plugin._events.empty()
