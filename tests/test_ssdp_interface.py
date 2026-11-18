"""SSDP source-interface selection regression tests."""

import socket
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from snf.adapters import ssdp


def test_default_route_ipv4_uses_os_route_selection(monkeypatch):
    fake_socket = MagicMock()
    fake_socket.__enter__.return_value = fake_socket
    fake_socket.getsockname.return_value = ("192.168.15.42", 53000)
    constructor = MagicMock(return_value=fake_socket)
    monkeypatch.setattr(ssdp.socket, "socket", constructor)

    assert ssdp._default_route_ipv4() == "192.168.15.42"
    constructor.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
    fake_socket.connect.assert_called_once_with(("1.1.1.1", 9))


def test_default_route_ipv4_rejects_unspecified_address(monkeypatch):
    fake_socket = MagicMock()
    fake_socket.__enter__.return_value = fake_socket
    fake_socket.getsockname.return_value = ("0.0.0.0", 53000)
    monkeypatch.setattr(ssdp.socket, "socket", lambda *args: fake_socket)

    with pytest.raises(OSError, match="default-route IPv4"):
        ssdp._default_route_ipv4()


@pytest.mark.asyncio
async def test_ssdp_search_uses_default_route_ipv4(monkeypatch):
    monkeypatch.setattr(ssdp, "find_spec", lambda name: object())
    monkeypatch.setattr(ssdp, "_default_route_ipv4", lambda: "192.168.15.42")

    calls = []

    async def fake_search(**kwargs):
        calls.append(kwargs)
        await kwargs["async_callback"]({
            "_host": "192.168.15.9",
            "_port": 1900,
            "usn": "uuid:tv",
            "st": "upnp:rootdevice",
        })

    fake_module = ModuleType("async_upnp_client.search")
    fake_module.async_search = fake_search
    monkeypatch.setitem(sys.modules, "async_upnp_client.search", fake_module)
    monkeypatch.setitem(sys.modules, "async_upnp_client", ModuleType("async_upnp_client"))

    plugin = ssdp.SSDPPlugin()
    await plugin.start()
    try:
        stream = plugin.discover()
        event = await anext(stream)
        assert event.observation.identifier == "uuid:tv"
        assert calls[0]["source"] == ("192.168.15.42", 0)
        await stream.aclose()
    finally:
        await plugin.stop()
