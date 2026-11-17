"""mDNS inspection parser and isolated resolver tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from snf.inspection.mdns import MDNSInspectionError, MDNSInspector, MDNSMetadataParser
from snf.models import DiscoveryObservation, Service


def observation():
    return DiscoveryObservation(
        "mdns", "_airplay._tcp.local.|Living Room._airplay._tcp.local.", "Living Room",
        services=(Service(
            "Living Room._airplay._tcp.local.",
            service_type="_airplay._tcp.local.",
        ),),
    )


def test_metadata_parser_does_not_infer_device_identity():
    assert MDNSMetadataParser().parse(observation()) == (
        "_airplay._tcp.local.", "Living Room._airplay._tcp.local."
    )


def test_rejects_wrong_protocol_and_missing_service():
    with pytest.raises(MDNSInspectionError, match="Only mDNS"):
        MDNSMetadataParser().parse(DiscoveryObservation("ssdp", "id", "device"))
    with pytest.raises(MDNSInspectionError, match="no DNS-SD"):
        MDNSMetadataParser().parse(DiscoveryObservation("mdns", "id", "device"))


def test_txt_decoding_and_addresses():
    info = SimpleNamespace(
        properties={b"model": b"TV", b"empty": None, b"binary": b"\xff"},
        server="tv.local.", port=7000,
        parsed_addresses=lambda: ["192.168.1.10", "fe80::1"],
    )
    details = MDNSMetadataParser().details("_airplay._tcp.local.", "TV", info)
    assert details.properties["model"] == "TV"
    assert details.properties["empty"] == ""
    assert details.properties["binary"] == "\ufffd"
    assert details.addresses == ("192.168.1.10", "fe80::1")


@pytest.mark.asyncio
async def test_inspector_uses_fresh_resolution_without_mutating_observation():
    pytest.importorskip("zeroconf")
    record = observation()
    info = SimpleNamespace(
        properties={b"features": b"0x1"}, server="tv.local.", port=7000,
        parsed_addresses=lambda: ["192.168.1.10"],
    )
    instance = MagicMock()
    instance.async_get_service_info = AsyncMock(return_value=info)
    instance.async_close = AsyncMock()
    with patch("zeroconf.asyncio.AsyncZeroconf", return_value=instance):
        result = await MDNSInspector().inspect_observation(record)
    assert result.properties == {"features": "0x1"}
    instance.async_get_service_info.assert_awaited_once_with(
        "_airplay._tcp.local.", "Living Room._airplay._tcp.local.", timeout=3000
    )
    instance.async_close.assert_awaited_once()
    assert record == observation()


@pytest.mark.asyncio
async def test_unavailable_service_returns_stable_error():
    pytest.importorskip("zeroconf")
    instance = MagicMock()
    instance.async_get_service_info = AsyncMock(return_value=None)
    instance.async_close = AsyncMock()
    with patch("zeroconf.asyncio.AsyncZeroconf", return_value=instance):
        with pytest.raises(MDNSInspectionError) as caught:
            await MDNSInspector().inspect_observation(observation())
    assert caught.value.code == "SERVICE_UNAVAILABLE"
