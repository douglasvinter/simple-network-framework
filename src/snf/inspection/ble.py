"""Explicit, read-only BLE GATT service enumeration for an existing observation."""

from __future__ import annotations

from dataclasses import dataclass

from snf.models import DiscoveryObservation


class BLEInspectionError(ValueError):
    """Stable error code for failed BLE inspection."""

    def __init__(self, message: str, *, code: str = "INSPECTION_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BLECharacteristicDetails:
    uuid: str
    properties: tuple[str, ...]
    descriptors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BLEServiceDetails:
    uuid: str
    characteristics: tuple[BLECharacteristicDetails, ...]


@dataclass(frozen=True, slots=True)
class BLEDeviceDetails:
    identifier: str
    services: tuple[BLEServiceDetails, ...]


class BLEInspector:
    """Connect on demand to enumerate GATT metadata; never read or write values."""

    async def inspect_observation(self, observation: DiscoveryObservation) -> BLEDeviceDetails:
        if observation.protocol != "ble":
            raise BLEInspectionError(
                "Only BLE observations can be inspected", code="UNSUPPORTED_PROTOCOL"
            )
        if not observation.identifier.strip():
            raise BLEInspectionError(
                "Observation has no BLE identifier", code="INVALID_OBSERVATION"
            )
        try:
            from bleak import BleakClient
        except ImportError as exc:
            raise BLEInspectionError(
                "Install BLE support with the ble extra", code="DEPENDENCY_UNAVAILABLE"
            ) from exc

        try:
            async with BleakClient(observation.identifier) as client:
                services = tuple(
                    BLEServiceDetails(
                        uuid=str(service.uuid),
                        characteristics=tuple(
                            BLECharacteristicDetails(
                                uuid=str(characteristic.uuid),
                                properties=tuple(characteristic.properties),
                                descriptors=tuple(
                                    str(descriptor.uuid)
                                    for descriptor in characteristic.descriptors
                                ),
                            )
                            for characteristic in service.characteristics
                        ),
                    )
                    for service in client.services
                )
        except (OSError, TimeoutError) as exc:
            raise BLEInspectionError(
                "BLE GATT service enumeration failed", code="CONNECTION_FAILED"
            ) from exc
        return BLEDeviceDetails(identifier=observation.identifier, services=services)
