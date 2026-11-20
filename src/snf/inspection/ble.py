"""Explicit, read-only BLE GATT service enumeration for an existing observation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from snf.bluetooth.assigned_numbers import uuid_details
from snf.inspection.error_codes import InspectionErrorCode
from snf.models import DiscoveryObservation

_LOGGER = logging.getLogger(__name__)


def _assigned_name(uuid: str, kind: str) -> str | None:
    details = uuid_details(uuid, kind=kind)
    return details["name"] if details is not None else None


class BLEInspectionError(ValueError):
    """Stable error code for failed BLE inspection."""

    def __init__(
        self, message: str, *, code: str = InspectionErrorCode.INSPECTION_FAILED
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


def _service_details(service: object) -> BLEServiceDetails:
    """Project one Bleak service into immutable metadata without GATT reads."""
    item: Any = service
    return BLEServiceDetails(
        uuid=str(item.uuid),
        name=_assigned_name(str(item.uuid), "service"),
        characteristics=tuple(
            BLECharacteristicDetails(
                uuid=str(characteristic.uuid),
                properties=tuple(characteristic.properties),
                name=_assigned_name(str(characteristic.uuid), "characteristic"),
                descriptors=tuple(
                    str(descriptor.uuid) for descriptor in characteristic.descriptors
                ),
                descriptor_names=tuple(
                    _assigned_name(str(descriptor.uuid), "descriptor")
                    for descriptor in characteristic.descriptors
                ),
            )
            for characteristic in item.characteristics
        ),
    )


class BLEInspector:
    """Connect on demand to enumerate GATT metadata; never read or write values."""

    async def inspect_observation(self, observation: DiscoveryObservation) -> BLEDeviceDetails:
        if observation.protocol != "ble":
            raise BLEInspectionError(
                "Only BLE observations can be inspected", code=InspectionErrorCode.UNSUPPORTED_PROTOCOL
            )
        if not observation.identifier.strip():
            raise BLEInspectionError(
                "Observation has no BLE identifier", code=InspectionErrorCode.INVALID_OBSERVATION
            )
        try:
            from bleak import BleakClient
            from bleak.exc import BleakError
        except ImportError as exc:
            raise BLEInspectionError(
                "Install BLE support with the ble extra", code=InspectionErrorCode.DEPENDENCY_UNAVAILABLE
            ) from exc

        try:
            async with BleakClient(observation.identifier) as client:
                services = tuple(_service_details(service) for service in client.services)
        except (BleakError, OSError, TimeoutError) as exc:
            _LOGGER.exception("BLE GATT inspection failed for %s", observation.identifier)
            raise BLEInspectionError(
                "BLE GATT service enumeration failed", code=InspectionErrorCode.CONNECTION_FAILED
            ) from exc
        return BLEDeviceDetails(identifier=observation.identifier, services=services)
