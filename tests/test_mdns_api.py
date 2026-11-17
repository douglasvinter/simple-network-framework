"""HTTP contract for explicit mDNS inspection."""

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from snf.api import create_router
from snf.inspection.mdns import MDNSInspectionError, MDNSServiceDetails
from snf.models import DiscoveryObservation, Service
from snf.runtime import NetworkRuntime


class SnapshotRuntime(NetworkRuntime):
    def __init__(self, observations):
        super().__init__(plugins=[])
        self._protocols = ("mdns",)
        self._records = observations

    def snapshot(self, *, protocol=None):
        return tuple(self._records)


@pytest.mark.asyncio
async def test_mdns_inspection_success_and_error_isolation():
    observation = DiscoveryObservation(
        "mdns", "service-id", "TV",
        services=(Service("TV._airplay._tcp.local.", "_airplay._tcp.local."),),
    )
    runtime = SnapshotRuntime([observation])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    details = MDNSServiceDetails(
        "TV._airplay._tcp.local.", "_airplay._tcp.local.",
        "tv.local.", 7000, ("192.168.1.10",), {"features": "0x1"},
    )
    url = "/network/discoveries/inspect/mdns"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch(
            "snf.api.router.MDNSInspector.inspect_observation",
            new_callable=AsyncMock, return_value=details,
        ) as mocked:
            response = await client.get(url, params={"identifier": "service-id"})
        assert response.status_code == 200
        assert response.json()["properties"] == {"features": "0x1"}
        assert response.json()["error"] == {}
        mocked.assert_awaited_once_with(observation)

        missing = await client.get(url, params={"identifier": "unknown"})
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "OBSERVATION_NOT_FOUND"

        with patch(
            "snf.api.router.MDNSInspector.inspect_observation",
            new_callable=AsyncMock,
            side_effect=MDNSInspectionError(
                "Service not available", code="SERVICE_UNAVAILABLE"
            ),
        ):
            failure = await client.get(url, params={"identifier": "service-id"})
        assert failure.status_code == 502
        assert failure.json()["service"] is None
        assert failure.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert runtime.snapshot() == (observation,)


@pytest.mark.asyncio
async def test_mdns_inspection_requires_identifier():
    app = FastAPI()
    app.include_router(create_router(SnapshotRuntime([])), prefix="/network")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/network/discoveries/inspect/mdns")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_IDENTIFIER"
