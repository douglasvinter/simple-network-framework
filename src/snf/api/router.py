"""Optional REST, SSE, and health routes over an existing SNF runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from snf.api.schemas import DiscoveryObservationResponse
from snf.runtime import NetworkRuntime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    discovery_running: bool
    observations: int
    protocols: tuple[str, ...]


def create_router(runtime: NetworkRuntime) -> APIRouter:
    """Create HTTP routes sharing the caller-owned runtime; no implicit startup."""
    router = APIRouter()
    Protocol = Annotated[str | None, Query()]

    def validate(protocol: str | None) -> None:
        try:
            runtime.validate_protocol(protocol)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/discoveries", response_model=list[DiscoveryObservationResponse])
    def discoveries(protocol: Protocol = None) -> tuple:
        validate(protocol)
        try:
            return runtime.snapshot(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/discoveries/map", response_model=dict[str, dict[str, DiscoveryObservationResponse]])
    def discovery_map(protocol: Protocol = None) -> dict:
        validate(protocol)
        try:
            return runtime.observation_map(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/discoveries/events", response_class=EventSourceResponse)
    async def events(request: Request, protocol: Protocol = None) -> EventSourceResponse:
        validate(protocol)
        try:
            subscription = runtime.subscribe(protocol=protocol)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        async def serialize():
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
            serialize(), ping=15,
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
            timestamp=datetime.now(timezone.utc),
            discovery_running=running,
            observations=count,
            protocols=runtime.protocols,
        )

    return router
