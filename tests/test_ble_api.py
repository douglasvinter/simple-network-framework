"""HTTP contract tests for explicit BLE inspection."""

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from snf.api import create_router
from snf.inspection.ble import BLEDeviceDetails, BLEInspectionError, BLEServiceDetails
from snf.models import DiscoveryObservation
from snf.runtime import NetworkRuntime


class SnapshotRuntime(NetworkRuntime):
    def __init__(self, observations):
        super().__init__(plugins=[])
        self._protocols = ("ble",)
        self._records = observations

    def snapshot(self, *, protocol=None):
        return tuple(self._records)


@pytest.mark.asyncio
async def test_ble_inspection_api_is_explicit_and_does_not_mutate_snapshot():
    observation = DiscoveryObservation("ble", "AA:BB:CC:DD:EE:FF", "Sensor")
    runtime = SnapshotRuntime([observation])
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/network")
    url = "/network/discoveries/inspect/ble"
    details = BLEDeviceDetails(observation.identifier, (BLEServiceDetails("180f", ()),))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch(
            "snf.runtime.BLEInspector.inspect_observation",
            new_callable=AsyncMock,
            return_value=details,
        ) as mocked:
            success = await client.get(url, params={"identifier": observation.identifier})
        assert success.status_code == 200
        assert success.json()["services"] == [{"uuid": "180f", "characteristics": []}]
        mocked.assert_awaited_once_with(observation)

        missing = await client.get(url, params={"identifier": "missing"})
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "OBSERVATION_NOT_FOUND"

        invalid = await client.get(url)
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_IDENTIFIER"

        with patch(
            "snf.runtime.BLEInspector.inspect_observation",
            new_callable=AsyncMock,
            side_effect=BLEInspectionError("Cannot connect", code="CONNECTION_FAILED"),
        ):
            failed = await client.get(url, params={"identifier": observation.identifier})
        assert failed.status_code == 502
        assert failed.json()["error"]["code"] == "CONNECTION_FAILED"
    assert runtime.snapshot() == (observation,)
