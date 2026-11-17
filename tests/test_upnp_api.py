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
from snf.models import DiscoveryObservation
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
    observation = DiscoveryObservation("ssdp", "uuid:sample::upnp:rootdevice", "TV",
        metadata={"location": "http://192.168.15.9:9110/ip_control"})
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
        assert runtime.snapshot() == (observation,)


@pytest.mark.asyncio
async def test_http_inspection_rejects_non_ssdp_protocol():
    runtime = NetworkRuntime(plugins=[])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/network/discoveries/inspect", params={"identifier": "unknown"})
    assert response.status_code == 422
