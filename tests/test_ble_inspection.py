"""Unit tests for explicit BLE GATT metadata inspection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("bleak")

from snf.inspection.ble import BLEInspectionError, BLEInspector
from snf.models import DiscoveryObservation


@pytest.mark.asyncio
async def test_ble_inspection_enumerates_services_without_reading_values():
    descriptor = SimpleNamespace(uuid="2902")
    characteristic = SimpleNamespace(
        uuid="2a19", properties=["read", "notify"], descriptors=[descriptor]
    )
    service = SimpleNamespace(uuid="180f", characteristics=[characteristic])
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.services = [service]
    observation = DiscoveryObservation("ble", "AA:BB:CC:DD:EE:FF", "Sensor")

    with patch("bleak.BleakClient", return_value=client) as constructor:
        result = await BLEInspector().inspect_observation(observation)

    constructor.assert_called_once_with(observation.identifier)
    assert result.identifier == observation.identifier
    assert result.services[0].uuid == "180f"
    assert result.services[0].characteristics[0].properties == ("read", "notify")
    assert result.services[0].characteristics[0].descriptors == ("2902",)
    client.__aexit__.assert_awaited_once()
    assert observation.services == ()


@pytest.mark.asyncio
async def test_ble_inspection_rejects_other_protocols():
    with pytest.raises(BLEInspectionError, match="Only BLE"):
        await BLEInspector().inspect_observation(
            DiscoveryObservation("mdns", "example", "Example")
        )


@pytest.mark.asyncio
async def test_ble_inspection_reports_connection_failure():
    observation = DiscoveryObservation("ble", "AA:BB:CC:DD:EE:FF", "Sensor")
    with patch("bleak.BleakClient", side_effect=OSError("radio unavailable")):
        with pytest.raises(BLEInspectionError) as exc:
            await BLEInspector().inspect_observation(observation)
    assert exc.value.code == "CONNECTION_FAILED"
