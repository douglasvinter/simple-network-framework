"""Contract tests for explicit read-only SLP service inspection.

Tests are intentionally written before the inspector implementation.
"""

from unittest.mock import AsyncMock, patch

import pytest

from snf.inspection.slp import (
    SLPInspectionError,
    SLPInspector,
    SLPServiceDetails,
)
from snf.models import DiscoveryObservation
from snf.runtime import NetworkRuntime


URL = "service:snf-test://127.0.0.1:8080"


@pytest.fixture
def observation():
    return DiscoveryObservation("slp", URL, URL, metadata={"url": URL})


@pytest.mark.asyncio
async def test_inspector_reads_attributes_without_mutating_observation(observation):
    inspector = SLPInspector()
    with patch.object(
        inspector, "_run", new_callable=AsyncMock,
        return_value=["(name=SNF Test),(enabled),(tags=one,two)"],
    ) as command:
        details = await inspector.inspect_observation(observation)
    command.assert_awaited_once_with("findattrs", URL)
    assert details == SLPServiceDetails(
        url=URL,
        attributes={"name": "SNF Test", "enabled": True, "tags": ("one", "two")},
    )
    assert observation.metadata == {"url": URL}


@pytest.mark.asyncio
async def test_inspector_parses_escaped_delimiters_and_opaque_values(observation):
    inspector = SLPInspector()
    with patch.object(
        inspector, "_run", new_callable=AsyncMock,
        return_value=[r"(label=Room\\2c Office),(binary=\\ff\\00)"],
    ):
        details = await inspector.inspect_observation(observation)
    assert details.attributes["label"] == "Room, Office"
    assert details.attributes["binary"] == bytes.fromhex("ff00")


@pytest.mark.asyncio
async def test_inspector_rejects_invalid_protocol():
    with pytest.raises(SLPInspectionError) as failed:
        await SLPInspector().inspect_observation(
            DiscoveryObservation("mdns", URL, URL)
        )
    assert failed.value.code == "UNSUPPORTED_PROTOCOL"


@pytest.mark.asyncio
async def test_inspector_rejects_missing_url():
    with pytest.raises(SLPInspectionError) as failed:
        await SLPInspector().inspect_observation(
            DiscoveryObservation("slp", "", "")
        )
    assert failed.value.code == "INVALID_OBSERVATION"


@pytest.mark.asyncio
async def test_inspector_rejects_malformed_attribute_output(observation):
    inspector = SLPInspector()
    with patch.object(inspector, "_run", new_callable=AsyncMock, return_value=["(broken"]):
        with pytest.raises(SLPInspectionError) as failed:
            await inspector.inspect_observation(observation)
    assert failed.value.code == "INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_inspector_maps_missing_binary(observation):
    inspector = SLPInspector(command="missing-slptool")
    with patch("snf.inspection.slp.shutil.which", return_value=None):
        with pytest.raises(SLPInspectionError) as failed:
            await inspector.inspect_observation(observation)
    assert failed.value.code == "DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_inspector_maps_timeout(observation):
    inspector = SLPInspector()
    with patch.object(inspector, "_run", new_callable=AsyncMock, side_effect=TimeoutError):
        with pytest.raises(SLPInspectionError) as failed:
            await inspector.inspect_observation(observation)
    assert failed.value.code == "TIMEOUT"


@pytest.mark.asyncio
async def test_inspector_maps_failed_command(observation):
    inspector = SLPInspector()
    with patch.object(
        inspector, "_run", new_callable=AsyncMock, side_effect=RuntimeError("errorcode: -19")
    ):
        with pytest.raises(SLPInspectionError) as failed:
            await inspector.inspect_observation(observation)
    assert failed.value.code == "INSPECTION_FAILED"


@pytest.mark.asyncio
async def test_runtime_dispatches_slp_inspection_without_mutating_snapshot(observation):
    runtime = NetworkRuntime(plugins=[])
    runtime._protocols = ("slp",)
    with patch.object(runtime, "snapshot", return_value=(observation,)):
        with patch(
            "snf.runtime.SLPInspector.inspect_observation",
            new_callable=AsyncMock,
            return_value=SLPServiceDetails(URL, {"name": "SNF Test"}),
        ) as inspected:
            result = await runtime.inspect("slp", URL)
    inspected.assert_awaited_once_with(observation)
    assert result.attributes["name"] == "SNF Test"
