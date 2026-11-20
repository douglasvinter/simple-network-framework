"""Native inspection works without importing or starting the optional HTTP API."""

from unittest.mock import AsyncMock, patch

import pytest

from snf.inspection.ble import BLEDeviceDetails, BLEInspectionError
from snf.inspection.mdns import MDNSServiceDetails
from snf.inspection.upnp import UPnPDevice
from snf.models import DiscoveryObservation
from snf.runtime import InspectionLookupError, NetworkRuntime


class SnapshotRuntime(NetworkRuntime):
    def __init__(self, observation: DiscoveryObservation):
        super().__init__(plugins=[])
        self._protocols = (observation.protocol,)
        self._record = observation

    def snapshot(self, *, protocol=None):
        return (self._record,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protocol", "inspector", "details"),
    [
        (
            "ble", "BLEInspector",
            BLEDeviceDetails("AA:BB", ()),
        ),
        (
            "mdns", "MDNSInspector",
            MDNSServiceDetails("test", "_http._tcp.local.", None, None, (), {}),
        ),
        (
            "ssdp", "UPnPInspector",
            UPnPDevice(None, None, "TV", None, None, None, (), ()),
        ),
    ],
)
async def test_native_inspection_delegates_without_mutating_snapshot(
    protocol, inspector, details
):
    observation = DiscoveryObservation(protocol, "AA:BB", "Test")
    runtime = SnapshotRuntime(observation)
    with patch(
        f"snf.runtime.{inspector}.inspect_observation",
        new_callable=AsyncMock,
        return_value=details,
    ) as mocked:
        assert runtime.get(protocol, "AA:BB") == observation
        assert await runtime.inspect(protocol, "AA:BB") == details
        mocked.assert_awaited_once_with(observation)
    assert runtime.snapshot() == (observation,)


@pytest.mark.asyncio
async def test_native_inspection_validates_identifier_and_missing_observation():
    runtime = SnapshotRuntime(DiscoveryObservation("ble", "AA:BB", "Test"))
    with pytest.raises(InspectionLookupError, match="identifier") as invalid:
        await runtime.inspect("ble", " ")
    assert invalid.value.code == "INVALID_IDENTIFIER"
    with pytest.raises(InspectionLookupError) as missing:
        await runtime.inspect("ble", "missing")
    assert missing.value.code == "OBSERVATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_native_inspection_propagates_protocol_error():
    runtime = SnapshotRuntime(DiscoveryObservation("ble", "AA:BB", "Test"))
    with patch(
        "snf.runtime.BLEInspector.inspect_observation",
        new_callable=AsyncMock,
        side_effect=BLEInspectionError("Connection failed", code="CONNECTION_FAILED"),
    ):
        with pytest.raises(BLEInspectionError) as failed:
            await runtime.inspect("ble", "AA:BB")
    assert failed.value.code == "CONNECTION_FAILED"


@pytest.mark.asyncio
async def test_native_inspection_rejects_protocol_without_inspector():
    runtime = SnapshotRuntime(DiscoveryObservation("custom", "service", "Test"))
    with pytest.raises(InspectionLookupError) as unsupported:
        await runtime.inspect("custom", "service")
    assert unsupported.value.code == "UNSUPPORTED_PROTOCOL"
