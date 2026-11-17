"""Read-only inspection HTTP contract and failure isolation tests."""

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from snf.api import create_router
from snf.inspection.upnp import UPnPInspectionError, parse_description
from snf.models import DiscoveryObservation, Endpoint
from snf.runtime import NetworkRuntime


class SnapshotRuntime(NetworkRuntime):
    def __init__(self, observations):
        super().__init__(plugins=[])
        self._observations_for_test = observations
        self._protocols = ("ssdp",)

    def snapshot(self, *, protocol=None):
        return tuple(self._observations_for_test)


@pytest.mark.asyncio
async def test_http_inspection_end_to_end_and_error_isolation():
    observation = DiscoveryObservation(
        "ssdp", "uuid:sample::upnp:rootdevice", "TV",
        endpoints=(Endpoint("ip", "192.168.15.9", 39261),),
        metadata={"location": "http://192.168.15.9:9110/ip_control"},
    )
    runtime = SnapshotRuntime([observation])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    xml = b"<root><device><friendlyName>Samsung TV</friendlyName></device></root>"
    device = parse_description(xml, "http://192.168.15.9:9110/ip_control")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("snf.api.router.UPnPInspector.inspect_observation", new_callable=AsyncMock, return_value=device) as mocked:
            response = await client.get("/network/discoveries/inspect", params={"identifier": observation.identifier})
        assert response.status_code == 200
        assert response.json()["friendly_name"] == "Samsung TV"
        mocked.assert_awaited_once_with(observation)
        missing = await client.get("/network/discoveries/inspect", params={"identifier": "missing"})
        assert missing.status_code == 404
        with patch("snf.api.router.UPnPInspector.inspect_observation", new_callable=AsyncMock,
                   side_effect=UPnPInspectionError("invalid description")):
            failure = await client.get("/network/discoveries/inspect", params={"identifier": observation.identifier})
        assert failure.status_code == 502
        assert failure.json()["error"]["message"] == "invalid description"
        assert failure.json()["error"]["code"] == "INSPECTION_FAILED"
        assert failure.json()["device"]["udn"] is None
        assert failure.json()["device"]["friendly_name"] is None
        assert runtime.snapshot() == (observation,)


@pytest.mark.asyncio
async def test_http_inspection_rejects_non_ssdp_protocol():
    runtime = NetworkRuntime(plugins=[])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/network/discoveries/inspect", params={"identifier": "unknown"})
    assert response.status_code == 422



@pytest.mark.asyncio
async def test_plain_text_response_error_contains_raw_evidence():
    observation = DiscoveryObservation(
        "ssdp", "uuid:SSTVKSF1==0000000000000005297130", "Netflix MDX",
        endpoints=(Endpoint("ip", "192.168.15.9", 44415),),
        metadata={"location": "http://192.168.15.9:9080"},
    )
    app = FastAPI()
    app.include_router(create_router(SnapshotRuntime([observation])), prefix="/network")
    failure = UPnPInspectionError(
        "Endpoint did not return a UPnP XML description",
        code="UNSUPPORTED_DESCRIPTION_FORMAT", raw_response="status=ok",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("snf.api.router.UPnPInspector.inspect_observation", new_callable=AsyncMock,
                   side_effect=failure):
            response = await client.get(
                "/network/discoveries/inspect", params={"identifier": observation.identifier}
            )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UNSUPPORTED_DESCRIPTION_FORMAT"
    assert response.json()["error"]["raw_response"] == "status=ok"
    assert response.json()["device"] == {
        "udn": "uuid:SSTVKSF1==0000000000000005297130",
        "device_type": None,
        "friendly_name": None,
        "manufacturer": None,
        "model_name": None,
        "model_number": None,
        "services": [],
        "embedded_devices": [],
    }



@pytest.mark.asyncio
async def test_failure_uses_only_semantically_valid_ssdp_metadata():
    from snf.models import Service

    observation = DiscoveryObservation(
        "ssdp", "uuid:device::urn:schemas-upnp-org:device:MediaRenderer:1",
        "Linux/1.0 UPnP/1.1",  # SERVER is not a friendly name.
        metadata={"udn": "uuid:device"},
        services=(Service(
            name="MediaRenderer",
            service_type="urn:schemas-upnp-org:device:MediaRenderer:1",
            metadata={"friendlyName": "Living Room TV", "server": "Linux/1.0"},
        ),),
    )
    app = FastAPI()
    app.include_router(create_router(SnapshotRuntime([observation])), prefix="/network")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("snf.api.router.UPnPInspector.inspect_observation", new_callable=AsyncMock,
                   side_effect=UPnPInspectionError("bad description")):
            response = await client.get(
                "/network/discoveries/inspect", params={"identifier": observation.identifier}
            )
    assert response.status_code == 502
    assert response.json()["device"]["udn"] == "uuid:device"
    assert response.json()["device"]["device_type"] == "urn:schemas-upnp-org:device:MediaRenderer:1"
    assert response.json()["device"]["friendly_name"] == "Living Room TV"
    assert response.json()["device"]["services"] == []
