"""Explicit read-only mDNS/DNS-SD inspection of a discovered service instance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from snf.models import DiscoveryObservation

DEFAULT_RESOLVE_TIMEOUT_MS = 3000
MDNS_PROTOCOL = "mdns"


class MDNSInspectionError(ValueError):
    """Stable inspection error suitable for API mapping."""

    def __init__(self, message: str, *, code: str = "INSPECTION_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MDNSServiceDetails:
    instance_name: str
    service_type: str
    server: str | None
    port: int | None
    addresses: tuple[str, ...]
    properties: dict[str, str]


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


class MDNSMetadataParser:
    """Interpret DNS-SD records without inferring a physical device identity."""

    def parse(self, observation: DiscoveryObservation) -> tuple[str, str]:
        if observation.protocol != MDNS_PROTOCOL:
            raise MDNSInspectionError(
                "Only mDNS observations can be inspected", code="UNSUPPORTED_PROTOCOL"
            )
        for service in observation.services:
            if service.service_type and service.name:
                return service.service_type, service.name
        raise MDNSInspectionError(
            "Observation has no DNS-SD service instance", code="INVALID_OBSERVATION"
        )

    def details(self, service_type: str, name: str, info: Any) -> MDNSServiceDetails:
        properties = {
            _decode(key): _decode(value)
            for key, value in info.properties.items()
        }
        return MDNSServiceDetails(
            instance_name=name,
            service_type=service_type,
            server=info.server,
            port=info.port,
            addresses=tuple(info.parsed_addresses()),
            properties=properties,
        )


class MDNSInspector:
    """Resolve a single service on demand; do not mutate discovery state."""

    def __init__(self, *, timeout_ms: int = DEFAULT_RESOLVE_TIMEOUT_MS) -> None:
        if timeout_ms <= 0:
            raise ValueError("mDNS inspection timeout must be positive")
        self.timeout_ms = timeout_ms
        self._parser = MDNSMetadataParser()

    async def inspect_observation(self, observation: DiscoveryObservation) -> MDNSServiceDetails:
        service_type, name = self._parser.parse(observation)
        try:
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError as exc:
            raise MDNSInspectionError(
                "Install mDNS support with the mdns extra", code="DEPENDENCY_UNAVAILABLE"
            ) from exc

        try:
            zeroconf = AsyncZeroconf()
            try:
                info = await zeroconf.async_get_service_info(
                    service_type, name, timeout=self.timeout_ms
                )
            finally:
                await zeroconf.async_close()
        except (OSError, TimeoutError) as exc:
            raise MDNSInspectionError(
                "mDNS service resolution failed", code="RESOLUTION_FAILED"
            ) from exc
        if info is None:
            raise MDNSInspectionError(
                "mDNS service instance did not resolve", code="SERVICE_UNAVAILABLE"
            )
        return self._parser.details(service_type, name, info)
