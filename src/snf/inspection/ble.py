"""Explicit, read-only BLE GATT service enumeration for an existing observation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from snf.bluetooth.assigned_numbers import uuid_details
from snf.inspection.error_codes import InspectionErrorCode
from snf.models import DiscoveryObservation

if TYPE_CHECKING:
    from bleak.backends.service import BleakGATTService

_LOGGER = logging.getLogger(__name__)


def _assigned_name(uuid: str, kind: str) -> str | None:
    details = uuid_details(uuid, kind=kind)
    return details["name"] if details is not None else None


class BLEInspectionError(ValueError):
    """Stable error code for failed BLE inspection."""

    def __init__(
        self, message: str, *, code: str = InspectionErrorCode.INSPECTION_FAILED.get_code()
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class BLECharacteristicDetails:
    uuid: str
    properties: tuple[str, ...]
    descriptors: tuple[str, ...]
    name: str | None = None
    descriptor_names: tuple[str | None, ...] = ()


@dataclass(frozen=True, slots=True)
class BLEServiceDetails:
    uuid: str
    characteristics: tuple[BLECharacteristicDetails, ...]
    name: str | None = None


@dataclass(frozen=True, slots=True)
class BLEDeviceDetails:
    identifier: str
    services: tuple[BLEServiceDetails, ...]


def _service_details(service: BleakGATTService) -> BLEServiceDetails:
    """Project Bleak GATT metadata without reading characteristic values."""
    service_uuid = str(service.uuid)
    service_name = _assigned_name(service_uuid, "service")
    characteristics: list[BLECharacteristicDetails] = []

    for characteristic in service.characteristics:
        characteristic_uuid = str(characteristic.uuid)
        characteristic_name = _assigned_name(characteristic_uuid, "characteristic")
        descriptors: list[str] = []
        descriptor_names: list[str | None] = []

        for descriptor in characteristic.descriptors:
            descriptor_uuid = str(descriptor.uuid)
            descriptors.append(descriptor_uuid)
            descriptor_names.append(_assigned_name(descriptor_uuid, "descriptor"))

        details = BLECharacteristicDetails(
            uuid=characteristic_uuid,
            properties=tuple(characteristic.properties),
            name=characteristic_name,
            descriptors=tuple(descriptors),
            descriptor_names=tuple(descriptor_names),
        )
        characteristics.append(details)

    return BLEServiceDetails(
        uuid=service_uuid,
        name=service_name,
        characteristics=tuple(characteristics),
    )


class BLEInspector:
    """Connect on demand to enumerate GATT metadata; never read or write values."""

    async def inspect_observation(self, observation: DiscoveryObservation) -> BLEDeviceDetails:
        if observation.protocol != "ble":
            raise BLEInspectionError(
                "Only BLE observations can be inspected",
                code=InspectionErrorCode.UNSUPPORTED_PROTOCOL.get_code()
            )
        if not observation.identifier.strip():
            raise BLEInspectionError(
                "Observation has no BLE identifier",
                code=InspectionErrorCode.INVALID_OBSERVATION.get_code()
            )
        try:
            from bleak import BleakClient
            from bleak.exc import BleakError
        except ImportError as exc:
            raise BLEInspectionError(
                "Install BLE support with the ble extra",
                code=InspectionErrorCode.DEPENDENCY_UNAVAILABLE.get_code()
            ) from exc

        try:
            async with BleakClient(observation.identifier) as client:
                services = tuple(
                    _service_details(service) for service in client.services
                )
        except (BleakError, OSError, TimeoutError) as exc:
            _LOGGER.exception("BLE GATT inspection failed for %s", observation.identifier)
            raise BLEInspectionError(
                "BLE GATT service enumeration failed",
                code=InspectionErrorCode.CONNECTION_FAILED.get_code()
            ) from exc
        return BLEDeviceDetails(identifier=observation.identifier, services=services)
