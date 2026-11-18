"""Optional REST, SSE, and health routes over an existing SNF runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from snf.api.schemas import (
    BLEInspectionErrorResponse,
    BLEInspectionResponse,
    DiscoveryObservationResponse,
    InspectionErrorResponse,
    InspectionSuccessResponse,
    MDNSInspectionErrorResponse,
    MDNSInspectionResponse,
    NetworkEntityResponse,
    UPnPDeviceResponse,
)
from snf.entities import NetworkEntity
from snf.inspection.ble import BLEInspectionError
from snf.inspection.mdns import MDNSInspectionError
from snf.inspection.ssdp_metadata import SSDPMetadataParser
from snf.inspection.upnp import UPnPInspectionError
from snf.models import DiscoveryObservation
from snf.runtime import NetworkRuntime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    discovery_running: bool
    observations: int
    protocols: tuple[str, ...]


def _advertised_device(observation: DiscoveryObservation) -> UPnPDeviceResponse:
    """Translate SSDP identity evidence into the API's fallback device."""
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


def create_router(runtime: NetworkRuntime) -> APIRouter:
    """Create HTTP routes sharing the caller-owned runtime; no implicit startup."""
    router = APIRouter()

    def validate(protocol: str | None) -> None:
        try:
            runtime.validate_protocol(protocol)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/discoveries", response_model=list[DiscoveryObservationResponse])
    def discoveries(protocol: str | None = None) -> tuple[DiscoveryObservation, ...]:
        validate(protocol)
        try:
            return runtime.snapshot(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get(
        "/discoveries/map",
        response_model=dict[str, dict[str, DiscoveryObservationResponse]],
    )
    def discovery_map(
        protocol: str | None = None,
    ) -> dict[str, dict[str, DiscoveryObservation]]:
        validate(protocol)
        try:
            return runtime.observation_map(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/entities", response_model=list[NetworkEntityResponse])
    def entities(protocol: str | None = None) -> tuple[NetworkEntity, ...]:
        validate(protocol)
        try:
            return runtime.entities(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get(
        "/discoveries/inspect/upnp",
        response_model=InspectionSuccessResponse,
        responses={
            404: {"model": InspectionErrorResponse},
            422: {"model": InspectionErrorResponse},
            502: {"model": InspectionErrorResponse},
            503: {"model": InspectionErrorResponse},
        },
    )
    async def inspect_discovery(identifier: str | None = None) -> object:
        """Explicit, read-only inspection of a discovered SSDP advertisement."""

        def failure(
            status: int, code: str, message: str,
            observation: DiscoveryObservation | None = None,
            raw_response: str | None = None,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=status,
                content=InspectionErrorResponse(
                    device=_advertised_device(observation) if observation else None,
                    error={
                        "code": code,
                        "message": message,
                        "raw_response": raw_response,
                    },
                ).model_dump(),
            )

        if identifier is None or not identifier.strip():
            return failure(422, "INVALID_IDENTIFIER", "An SSDP identifier is required")
        try:
            runtime.validate_protocol("ssdp")
        except ValueError as exc:
            return failure(422, "UNSUPPORTED_PROTOCOL", str(exc))
        try:
            observations = runtime.snapshot(protocol="ssdp")
        except RuntimeError as exc:
            return failure(503, "RUNTIME_UNAVAILABLE", str(exc))
        observation = runtime.get("ssdp", identifier)
        if observation is None:
            return failure(404, "OBSERVATION_NOT_FOUND", "SSDP observation not found")
        try:
            device = await runtime.inspect("ssdp", identifier)
            return InspectionSuccessResponse.model_validate({
                **UPnPDeviceResponse.model_validate(device).model_dump(),
                "error": {},
            })
        except UPnPInspectionError as exc:
            status = 422 if exc.code in {
                "UNSUPPORTED_DESCRIPTION_FORMAT",
                "MALFORMED_DESCRIPTION",
            } else 502
            return failure(status, exc.code, str(exc), observation, exc.raw_response)

    @router.get(
        "/discoveries/inspect/mdns",
        response_model=MDNSInspectionResponse,
        responses={
            404: {"model": MDNSInspectionErrorResponse},
            422: {"model": MDNSInspectionErrorResponse},
            502: {"model": MDNSInspectionErrorResponse},
            503: {"model": MDNSInspectionErrorResponse},
        },
    )
    async def inspect_mdns(identifier: str | None = None) -> object:
        """Resolve one existing DNS-SD observation without changing discovery state."""

        def failure(status: int, code: str, message: str) -> JSONResponse:
            payload = MDNSInspectionErrorResponse(
                service=None, error={"code": code, "message": message}
            )
            return JSONResponse(status_code=status, content=payload.model_dump())

        if identifier is None or not identifier.strip():
            return failure(422, "INVALID_IDENTIFIER", "An mDNS identifier is required")
        try:
            runtime.validate_protocol("mdns")
        except ValueError as exc:
            return failure(422, "UNSUPPORTED_PROTOCOL", str(exc))
        try:
            observations = runtime.snapshot(protocol="mdns")
        except RuntimeError as exc:
            return failure(503, "RUNTIME_UNAVAILABLE", str(exc))
        observation = runtime.get("mdns", identifier)
        if observation is None:
            return failure(404, "OBSERVATION_NOT_FOUND", "mDNS observation not found")
        try:
            details = await runtime.inspect("mdns", identifier)
        except MDNSInspectionError as exc:
            status = 422 if exc.code == "INVALID_OBSERVATION" else 502
            return failure(status, exc.code, str(exc))
        return MDNSInspectionResponse.model_validate({
            "instance_name": details.instance_name,
            "service_type": details.service_type,
            "server": details.server,
            "port": details.port,
            "addresses": details.addresses,
            "properties": details.properties,
            "error": {},
        })

    @router.get(
        "/discoveries/inspect/ble",
        response_model=BLEInspectionResponse,
        responses={
            404: {"model": BLEInspectionErrorResponse},
            422: {"model": BLEInspectionErrorResponse},
            502: {"model": BLEInspectionErrorResponse},
            503: {"model": BLEInspectionErrorResponse},
        },
    )
    async def inspect_ble(identifier: str | None = None) -> object:
        """Explicitly connect to enumerate GATT metadata without reading values."""

        def failure(status: int, code: str, message: str) -> JSONResponse:
            payload = BLEInspectionErrorResponse(
                device=None, error={"code": code, "message": message}
            )
            return JSONResponse(status_code=status, content=payload.model_dump())

        if identifier is None or not identifier.strip():
            return failure(422, "INVALID_IDENTIFIER", "A BLE identifier is required")
        try:
            runtime.validate_protocol("ble")
        except ValueError as exc:
            return failure(422, "UNSUPPORTED_PROTOCOL", str(exc))
        try:
            observations = runtime.snapshot(protocol="ble")
        except RuntimeError as exc:
            return failure(503, "RUNTIME_UNAVAILABLE", str(exc))
        observation = runtime.get("ble", identifier)
        if observation is None:
            return failure(404, "OBSERVATION_NOT_FOUND", "BLE observation not found")
        try:
            details = await runtime.inspect("ble", identifier)
        except BLEInspectionError as exc:
            status = 422 if exc.code == "INVALID_OBSERVATION" else 502
            return failure(status, exc.code, str(exc))
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

    @router.get("/discoveries/events", response_class=EventSourceResponse)
    async def events(request: Request, protocol: str | None = None) -> EventSourceResponse:
        validate(protocol)
        try:
            subscription = runtime.subscribe(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        async def serialize() -> AsyncIterator[ServerSentEvent]:
            try:
                async for event in subscription:
                    if await request.is_disconnected():
                        break
                    observation = DiscoveryObservationResponse.model_validate(event.observation)
                    yield ServerSentEvent(
                        event=event.state.value, data=observation.model_dump_json()
                    )
            finally:
                subscription.close()

        return EventSourceResponse(
            serialize(),
            ping=15,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        running = runtime.running
        try:
            count = len(runtime.snapshot()) if running else 0
        except RuntimeError:
            count = 0
        return HealthResponse(
            status="ok" if running else "degraded",
            timestamp=datetime.now(UTC),
            discovery_running=running,
            observations=count,
            protocols=runtime.protocols,
        )

    return router
