"""Optional HTTP contract tests using an injected runtime."""

from datetime import datetime

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from snf import DiscoveryEvent, DiscoveryObservation, DiscoveryState
from snf.api import create_router
from snf.runtime import NetworkRuntime


class Plugin:
    name = "fake"

    async def start(self):
        pass

    async def discover(self):
        yield DiscoveryEvent(DiscoveryState.ADDED, DiscoveryObservation("fake", "one", "TV"))

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_http_routes_and_utc_health_timestamp():
    runtime = NetworkRuntime([Plugin()])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    paths = set(app.openapi()["paths"])
    assert paths == {
        "/network/discoveries",
        "/network/discoveries/map",
        "/network/discoveries/events",
        "/network/health",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/network/health")
        assert before.json()["status"] == "degraded"
        async with runtime:
            for _ in range(100):
                if runtime.snapshot():
                    break
                import asyncio

                await asyncio.sleep(0.01)
            health = (await client.get("/network/health")).json()
            assert health["discovery_running"] is False
            assert health["status"] == "degraded"
            assert datetime.fromisoformat(health["timestamp"]).utcoffset().total_seconds() == 0
            observations = await client.get("/network/discoveries")
            assert observations.json()[0]["identifier"] == "one"
            grouped = await client.get("/network/discoveries/map")
            assert grouped.json()["fake"]["one"]["name"] == "TV"
            invalid = await client.get("/network/discoveries?protocol=unknown")
            assert invalid.status_code == 422
