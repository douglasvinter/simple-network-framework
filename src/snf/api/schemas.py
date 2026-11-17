"""HTTP serialization contracts for protocol-scoped observations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transport: str
    address: str
    port: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    service_type: str | None = None
    endpoints: tuple[EndpointResponse, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    protocol: str
    identifier: str
    name: str
    endpoints: tuple[EndpointResponse, ...] = ()
    services: tuple[ServiceResponse, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationReferenceResponse(BaseModel):
    protocol: str
    identifier: str


class NetworkEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    observations: tuple[ObservationReferenceResponse, ...]
    services: tuple[ServiceResponse, ...]
    identity_source: str


class UPnPServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_type: str
    service_id: str
    scpd_url: str | None
    control_url: str | None
    event_sub_url: str | None


class UPnPDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    udn: str | None
    device_type: str | None
    friendly_name: str | None
    manufacturer: str | None
    model_name: str | None
    model_number: str | None
    services: tuple[UPnPServiceResponse, ...]
    embedded_devices: tuple["UPnPDeviceResponse", ...]


class InspectionErrorDetail(BaseModel):
    code: str
    message: str
    raw_response: str | None = None


class InspectionSuccessResponse(UPnPDeviceResponse):
    error: dict[str, str] = Field(default_factory=dict)


class InspectionErrorResponse(BaseModel):
    device: UPnPDeviceResponse | None
    error: InspectionErrorDetail
