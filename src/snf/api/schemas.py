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


class NetworkEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    observations: tuple[DiscoveryObservationResponse, ...]
    services: tuple[ServiceResponse, ...]
    identity_source: str
