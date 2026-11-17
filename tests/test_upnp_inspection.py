"""UPnP inspection unit and local HTTP integration tests."""

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import pytest

from snf.inspection.upnp import UPnPInspectionError, UPnPInspector, parse_description
from snf.models import DiscoveryObservation, Endpoint

XML = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
<friendlyName>Living Room TV</friendlyName><manufacturer>Samsung</manufacturer>
<modelName>TV</modelName><UDN>uuid:abc</UDN>
<serviceList><service><serviceType>urn:service:AVTransport:1</serviceType>
<serviceId>urn:id:transport</serviceId><SCPDURL>/scpd.xml</SCPDURL>
<controlURL>/control</controlURL></service></serviceList>
<deviceList><device><friendlyName>Embedded</friendlyName></device></deviceList>
</device></root>"""


def test_parse_root_and_embedded_devices():
    result = parse_description(XML, "http://192.168.1.2:8000/description.xml")
    assert result.friendly_name == "Living Room TV"
    assert result.manufacturer == "Samsung"
    assert result.udn == "uuid:abc"
    assert result.services[0].scpd_url == "http://192.168.1.2:8000/scpd.xml"
    assert result.services[0].control_url == "http://192.168.1.2:8000/control"
    assert result.embedded_devices[0].friendly_name == "Embedded"


@pytest.mark.parametrize("xml", [b"", b"<broken", b"<root/>", b"<device/>",
    b'<!DOCTYPE root [<!ENTITY x "unsafe">]><root><device/></root>'])
def test_invalid_descriptions(xml):
    with pytest.raises(UPnPInspectionError):
        parse_description(xml, "http://192.168.1.2/desc")


def test_depth_limit():
    with pytest.raises(UPnPInspectionError, match="nesting"):
        parse_description(XML, "http://192.168.1.2/desc", max_depth=0)


@pytest.mark.parametrize("url", ["https://192.168.1.2/desc", "http://127.0.0.1/desc",
    "http://example.com/desc", "http://user:pass@192.168.1.2/desc",
    "file:///etc/passwd", "http://192.168.1.2:99999/desc"])
@pytest.mark.asyncio
async def test_rejects_unsafe_locations(url):
    inspector = UPnPInspector()
    with pytest.raises(UPnPInspectionError):
        await inspector.inspect(url)


@pytest.mark.asyncio
async def test_private_lan_http_integration():
    # A real TCP server, with the DNS resolver pinned to a synthetic private address.
    # Localhost is intentionally rejected by the production guard; this test exercises
    # the HTTP path via a temporary override of the local-address policy.
    async def handler(reader, writer):
        await reader.read(4096)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(XML)).encode()
                     + b"\r\nConnection: close\r\n\r\n" + XML)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with patch("snf.inspection.upnp._local_address", return_value=True):
            result = await UPnPInspector().inspect(f"http://127.0.0.1:{port}/desc")
        assert result.manufacturer == "Samsung"
    finally:
        server.close()
        await server.wait_closed()


from snf.inspection.upnp import location_from_observation


def test_location_from_ssdp_observation():
    observation = DiscoveryObservation("ssdp", "uuid:test", "TV", metadata={
        "location": "http://192.168.15.9:9110/ip_control"
    })
    assert location_from_observation(observation) == "http://192.168.15.9:9110/ip_control"


@pytest.mark.parametrize("observation", [
    DiscoveryObservation("mdns", "x", "TV", metadata={"location": "http://192.168.1.2"}),
    DiscoveryObservation("ssdp", "x", "TV"),
    DiscoveryObservation("ssdp", "x", "TV", metadata={"location": 123}),
    DiscoveryObservation("ssdp", "x", "TV", metadata={"location": "file:///etc/passwd"}),
])
def test_rejects_non_ssdp_or_invalid_location(observation):
    with pytest.raises(UPnPInspectionError):
        location_from_observation(observation)


@pytest.mark.asyncio
async def test_batch_inspection_deduplicates_shared_location():
    location = "http://192.168.15.9:9110/ip_control"
    records = tuple(DiscoveryObservation(
        "ssdp", f"ad-{i}", "TV",
        endpoints=(Endpoint("ip", "192.168.15.9", 40000 + i),),
        metadata={"location": location},
    ) for i in range(4))
    inspector = UPnPInspector()
    parsed = parse_description(XML, location)
    with patch.object(inspector, "inspect", return_value=parsed) as mocked:
        result = await inspector.inspect_observations(records)
    assert result == {location: parsed}
    mocked.assert_awaited_once_with(location, expected_addresses=frozenset({"192.168.15.9"}))


@pytest.mark.asyncio
async def test_single_observation_inspection():
    location = "http://192.168.15.9:9080"
    observation = DiscoveryObservation(
        "ssdp", "nonstandard-udn", "TV",
        endpoints=(Endpoint("ip", "192.168.15.9", 44415),),
        metadata={"location": location},
    )
    inspector = UPnPInspector()
    with patch.object(inspector, "inspect", return_value=parse_description(XML, location)) as mocked:
        result = await inspector.inspect_observation(observation)
    assert result.friendly_name == "Living Room TV"
    mocked.assert_awaited_once_with(location, expected_addresses=frozenset({"192.168.15.9"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [
    (302, b""),
    (404, b"missing"),
    (200, b"<html>not UPnP</html>"),
])
async def test_http_rejects_redirects_non_success_and_vendor_xml(status, body):
    async def handler(reader, writer):
        await reader.read(4096)
        response = (f"HTTP/1.1 {status} Test\r\nContent-Length: {len(body)}\r\n"
                    "Location: http://example.com/\r\nConnection: close\r\n\r\n").encode()
        writer.write(response + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with patch("snf.inspection.upnp._local_address", return_value=True):
            with pytest.raises(UPnPInspectionError):
                await UPnPInspector().inspect(f"http://127.0.0.1:{port}/desc")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_http_rejects_oversized_chunked_body():
    async def handler(reader, writer):
        await reader.read(4096)
        writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
                     b"Connection: close\r\n\r\n"
                     b"14\r\n01234567890123456789\r\n0\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with patch("snf.inspection.upnp._local_address", return_value=True):
            with pytest.raises(UPnPInspectionError, match="byte limit"):
                await UPnPInspector(max_bytes=10).inspect(f"http://127.0.0.1:{port}/desc")
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_http_timeout_does_not_block_discovery():
    async def handler(reader, writer):
        await reader.read(4096)
        await asyncio.sleep(0.2)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with patch("snf.inspection.upnp._local_address", return_value=True):
            with pytest.raises(UPnPInspectionError, match="fetch failed"):
                await UPnPInspector(timeout=0.03).inspect(f"http://127.0.0.1:{port}/desc")
    finally:
        server.close()
        await server.wait_closed()



def test_plain_text_health_response_preserved():
    with pytest.raises(UPnPInspectionError) as caught:
        parse_description(b"status=ok", "http://192.168.15.9:9080")
    assert caught.value.code == "UNSUPPORTED_DESCRIPTION_FORMAT"
    assert caught.value.raw_response == "status=ok"


def test_invalid_xml_distinguished_from_plain_text():
    with pytest.raises(UPnPInspectionError) as caught:
        parse_description(b"<root><device>", "http://192.168.15.9:9080")
    assert caught.value.code == "MALFORMED_DESCRIPTION"


@pytest.mark.asyncio
async def test_mismatched_source_rejected_before_http():
    observation = DiscoveryObservation(
        "ssdp", "uuid:test", "TV",
        endpoints=(Endpoint("ip", "192.168.15.9", 44415),),
        metadata={"location": "http://192.168.15.10:9110/desc"},
    )
    with patch("snf.inspection.upnp.aiohttp.ClientSession") as session:
        with pytest.raises(UPnPInspectionError) as caught:
            await UPnPInspector().inspect_observation(observation)
    assert caught.value.code == "SOURCE_ADDRESS_MISMATCH"
    session.assert_not_called()


@pytest.mark.asyncio
async def test_missing_source_address_rejected():
    observation = DiscoveryObservation(
        "ssdp", "uuid:test", "TV",
        metadata={"location": "http://192.168.15.9:9110/desc"},
    )
    with pytest.raises(UPnPInspectionError) as caught:
        await UPnPInspector().inspect_observation(observation)
    assert caught.value.code == "SOURCE_ADDRESS_UNAVAILABLE"
