"""Optional REST, SSE, and health routes over an existing SNF runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from snf.api.schemas import (
    DiscoveryObservationResponse,
    InspectionErrorResponse,
    InspectionSuccessResponse,
    NetworkEntityResponse,
    UPnPDeviceResponse,
)
from snf.entities import NetworkEntity
from snf.inspection.upnp import UPnPInspector, UPnPInspectionError
from snf.models import DiscoveryObservation
from snf.runtime import NetworkRuntime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    discovery_running: bool
    observations: int
    protocols: tuple[str, ...]


def _advertised_device(observation: DiscoveryObservation) -> UPnPDeviceResponse:
    """Conservative SSDP identity fallback; never infer physical-device identity."""
    udn = observation.metadata.get("udn")
    if not isinstance(udn, str) or not udn.startswith("uuid:"):
        usn = observation.metadata.get("usn")
        udn = usn.split("::", 1)[0] if isinstance(usn, str) and usn.startswith("uuid:") else None

    # SSDP ST may describe a device, service, UUID, or ssdp:all. Only a
    # device-type URN is semantically equivalent to UPnP device_type.
    device_type = next((
        service.service_type
        for service in observation.services
        if isinstance(service.service_type, str)
        and ":device:" in service.service_type.lower()
        and service.service_type.lower().startswith("urn:")
    ), None)

    # The SSDP adapter's observation.name is SERVER or ST, neither of which
    # is a friendly name. Only an explicitly advertised friendlyName is safe.
    friendly_name = next((
        value.strip()
        for service in observation.services
        for key, value in service.metadata.items()
        if str(key).lower() in {"friendlyname", "friendly-name"}
        and isinstance(value, str) and value.strip()
    ), None)

    return UPnPDeviceResponse(
        udn=udn,
        device_type=device_type,
        friendly_name=friendly_name,
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
        "/discoveries/inspect",
        response_model=InspectionSuccessResponse,
        responses={
            422: {"model": InspectionErrorResponse},
            502: {"model": InspectionErrorResponse},
        },
    )
    async def inspect_discovery(identifier: str) -> object:
        """Explicit, read-only inspection of a discovered SSDP advertisement."""
        validate("ssdp")
        try:
            observations = runtime.snapshot(protocol="ssdp")
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        observation = next((item for item in observations if item.identifier == identifier), None)
        if observation is None:
            raise HTTPException(status_code=404, detail="SSDP observation not found")
        try:
            device = await UPnPInspector().inspect_observation(observation)
            return InspectionSuccessResponse.model_validate({
                **UPnPDeviceResponse.model_validate(device).model_dump(),
                "error": {},
            })
        except UPnPInspectionError as exc:
            status = 422 if exc.code in {
                "UNSUPPORTED_DESCRIPTION_FORMAT",
                "MALFORMED_DESCRIPTION",
            } else 502
            return JSONResponse(
                status_code=status,
                content=InspectionErrorResponse(
                    device=_advertised_device(observation),
                    error={
                        "code": exc.code,
                        "message": str(exc),
                        "raw_response": exc.raw_response,
                    },
                ).model_dump(),
            )

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
