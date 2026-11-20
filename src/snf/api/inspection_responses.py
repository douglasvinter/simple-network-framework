"""HTTP presentation for protocol-specific inspection failures.

No runtime access, observation lookup, or network I/O belongs in this module.
"""

from http import HTTPStatus

from fastapi.responses import JSONResponse

from snf.api.schemas import (
    BLEInspectionErrorResponse,
    BLEInspectionResponse,
    InspectionErrorResponse,
    MDNSInspectionErrorResponse,
    MDNSInspectionResponse,
    UPnPDeviceResponse,
)
from snf.inspection.ble import BLEDeviceDetails
from snf.inspection.error_codes import InspectionErrorCode
from snf.inspection.mdns import MDNSServiceDetails
from snf.inspection.ssdp_metadata import SSDPMetadataParser
from snf.models import DiscoveryObservation


def upnp_error_status(code: str) -> int:
    return (
        HTTPStatus.UNPROCESSABLE_ENTITY
        if code in {
            InspectionErrorCode.UNSUPPORTED_DESCRIPTION_FORMAT,
            InspectionErrorCode.MALFORMED_DESCRIPTION,
        }
        else HTTPStatus.BAD_GATEWAY
    )


def mdns_error_status(code: str) -> int:
    return (
        HTTPStatus.UNPROCESSABLE_ENTITY
        if code == InspectionErrorCode.INVALID_OBSERVATION
        else HTTPStatus.BAD_GATEWAY
    )


def ble_error_status(code: str) -> int:
    return mdns_error_status(code)


def _advertised_device(observation: DiscoveryObservation) -> UPnPDeviceResponse:
    metadata = SSDPMetadataParser().parse(observation)
    return UPnPDeviceResponse(
        udn=metadata.udn,
        device_type=metadata.device_type,
        friendly_name=metadata.friendly_name,
        manufacturer=None,
        model_name=None,
        model_number=None,
        services=(),
        embedded_devices=(),
    )


def upnp_failure(
    status: int,
    code: str,
    message: str,
    *,
    observation: DiscoveryObservation | None = None,
    raw_response: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=InspectionErrorResponse(
            device=_advertised_device(observation) if observation else None,
            error={"code": code, "message": message, "raw_response": raw_response},
        ).model_dump(),
    )


def mdns_failure(status: int, code: str, message: str) -> JSONResponse:
    payload = MDNSInspectionErrorResponse(
        service=None, error={"code": code, "message": message}
    )
    return JSONResponse(status_code=status, content=payload.model_dump())


def ble_failure(status: int, code: str, message: str) -> JSONResponse:
    payload = BLEInspectionErrorResponse(
        device=None, error={"code": code, "message": message}
    )
    return JSONResponse(status_code=status, content=payload.model_dump())


def mdns_success(details: MDNSServiceDetails) -> MDNSInspectionResponse:
    return MDNSInspectionResponse.model_validate({
        "instance_name": details.instance_name,
        "service_type": details.service_type,
        "server": details.server,
        "port": details.port,
        "addresses": details.addresses,
        "properties": details.properties,
        "error": {},
    })


def ble_success(details: BLEDeviceDetails) -> BLEInspectionResponse:
    return BLEInspectionResponse.model_validate({
        "identifier": details.identifier,
        "services": [
            {
                "uuid": service.uuid,
                "characteristics": [
                    {
                        "uuid": characteristic.uuid,
                        "properties": characteristic.properties,
                        "descriptors": characteristic.descriptors,
                    }
                    for characteristic in service.characteristics
                ],
            }
            for service in details.services
        ],
        "error": {},
    })
