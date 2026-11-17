"""UPnP inspection unit and local HTTP integration tests."""

import asyncio
from unittest.mock import patch

import pytest

from snf.inspection.upnp import UPnPInspectionError, UPnPInspector, parse_description

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
