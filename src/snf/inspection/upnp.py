"""Read-only UPnP device-description inspection with bounded, local-only HTTP access."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urljoin, urlsplit

import aiohttp

from snf.inspection.constants import (
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_EMBEDDED_DEPTH,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    HTTP_DEFAULT_PORT,
    MAX_TCP_PORT,
    SSDP_PROTOCOL,
)
from snf.inspection.error_codes import InspectionErrorCode
from snf.inspection.xml import child_text, children, local_name
from snf.models import DiscoveryObservation


class UPnPInspectionError(ValueError):
    """Failed inspection with a stable code and optional bounded response."""

    def __init__(
        self, message: str, *, code: str = InspectionErrorCode.INSPECTION_FAILED,
        raw_response: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw_response = raw_response



@dataclass(frozen=True, slots=True)
class UPnPService:
    service_type: str
    service_id: str
    scpd_url: str | None
    control_url: str | None
    event_sub_url: str | None


@dataclass(frozen=True, slots=True)
class UPnPDevice:
    udn: str | None
    device_type: str | None
    friendly_name: str | None
    manufacturer: str | None
    model_name: str | None
    model_number: str | None
    services: tuple[UPnPService, ...]
    embedded_devices: tuple[UPnPDevice, ...]


def _parse_service(service: ET.Element, base_url: str) -> UPnPService:
    def link(field: str) -> str | None:
        value = child_text(service, field)
        return urljoin(base_url, value) if value else None

    return UPnPService(
        child_text(service, "serviceType") or "",
        child_text(service, "serviceId") or "",
        link("SCPDURL"),
        link("controlURL"),
        link("eventSubURL"),
    )


def _device(element: ET.Element, base_url: str, depth: int, max_depth: int) -> UPnPDevice:
    if depth > max_depth:
        raise UPnPInspectionError("UPnP embedded-device nesting limit exceeded")
    services = [
        _parse_service(service, base_url)
        for service_list in children(element, "serviceList")
        for service in children(service_list, "service")
    ]
    embedded = [
        _device(child, base_url, depth + 1, max_depth)
        for device_list in children(element, "deviceList")
        for child in children(device_list, "device")
    ]
    return UPnPDevice(
        udn=child_text(element, "UDN"),
        device_type=child_text(element, "deviceType"),
        friendly_name=child_text(element, "friendlyName"),
        manufacturer=child_text(element, "manufacturer"),
        model_name=child_text(element, "modelName"),
        model_number=child_text(element, "modelNumber"),
        services=tuple(services),
        embedded_devices=tuple(embedded),
    )


def parse_description(
    xml: bytes, location: str, *, max_depth: int = DEFAULT_MAX_EMBEDDED_DEPTH
) -> UPnPDevice:
    """Parse UPnP description XML without fetching linked service documents."""
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise UPnPInspectionError("DTD and entity declarations are not permitted")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        if not xml.lstrip().startswith(b"<"):
            raise UPnPInspectionError(
                "Endpoint did not return a UPnP XML description",
                code=InspectionErrorCode.UNSUPPORTED_DESCRIPTION_FORMAT,
                raw_response=xml.decode("utf-8", errors="replace"),
            ) from exc
        raise UPnPInspectionError(
            "Malformed UPnP description XML", code=InspectionErrorCode.MALFORMED_DESCRIPTION,
            raw_response=xml.decode("utf-8", errors="replace"),
        ) from exc
    if local_name(root.tag) != "root":
        raise UPnPInspectionError(
            "Not a UPnP root description", code=InspectionErrorCode.UNSUPPORTED_DESCRIPTION_FORMAT,
            raw_response=xml.decode("utf-8", errors="replace"),
        )
    device = next(iter(children(root, "device")), None)
    if device is None:
        raise UPnPInspectionError(
            "Missing UPnP root device", code=InspectionErrorCode.UNSUPPORTED_DESCRIPTION_FORMAT,
            raw_response=xml.decode("utf-8", errors="replace"),
        )
    return _device(device, location, 0, max_depth)


def _local_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not any((
        ip.is_global, ip.is_loopback, ip.is_link_local,
        ip.is_multicast, ip.is_unspecified, ip.is_reserved,
    ))


def _validate_url(url: str) -> tuple[str, int, str]:
    parts = urlsplit(url)
    if (
        parts.scheme != "http"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise UPnPInspectionError(
            "Only plain HTTP device descriptions without credentials are allowed"
        )
    try:
        port = parts.port or HTTP_DEFAULT_PORT
    except ValueError as exc:
        raise UPnPInspectionError("Invalid UPnP description port") from exc
    if not 1 <= port <= MAX_TCP_PORT:
        raise UPnPInspectionError("Invalid UPnP description port")
    return parts.hostname, port, parts.path or "/"


def location_from_observation(observation: DiscoveryObservation) -> str:
    """Extract LOCATION only from an SSDP observation, never an arbitrary endpoint."""
    if observation.protocol != SSDP_PROTOCOL:
        raise UPnPInspectionError("Only SSDP observations support UPnP inspection")
    location = observation.metadata.get("location")
    if not isinstance(location, str) or not location.strip():
        raise UPnPInspectionError("SSDP observation has no valid LOCATION")
    _validate_url(location)
    return location


def _source_addresses(observation: DiscoveryObservation) -> frozenset[str]:
    """Use observed SSDP source IPs, never advertised LOCATION as source."""
    addresses: set[str] = set()
    for endpoint in observation.endpoints:
        if endpoint.transport != "ip":
            continue
        try:
            ip = ipaddress.ip_address(endpoint.address)
        except ValueError:
            continue
        if _local_address(str(ip)):
            addresses.add(str(ip))
    if not addresses:
        raise UPnPInspectionError(
            "SSDP observation has no eligible source IP address",
            code=InspectionErrorCode.SOURCE_ADDRESS_UNAVAILABLE,
        )
    return frozenset(addresses)


def _validate_resolved_addresses(
    addresses: set[str], expected_addresses: frozenset[str] | None
) -> set[str]:
    """Enforce local-only DNS answers and bind them to SSDP source evidence."""
    if not addresses or not all(_local_address(ip) for ip in addresses):
        raise UPnPInspectionError(
            "LOCATION must resolve exclusively to private LAN addresses"
        )
    normalized = {str(ipaddress.ip_address(ip)) for ip in addresses}
    if expected_addresses is not None and (
        not expected_addresses or not normalized.issubset(expected_addresses)
    ):
        raise UPnPInspectionError(
            "LOCATION address does not match the SSDP source address",
            code=InspectionErrorCode.SOURCE_ADDRESS_MISMATCH,
        )
    return normalized


async def _read_description(response: aiohttp.ClientResponse, max_bytes: int) -> bytes:
    """Validate status and enforce the declared and actual byte limits."""
    if response.status != HTTPStatus.OK:
        raise UPnPInspectionError(
            f"Unexpected HTTP status: {response.status}"
        )
    if (
        response.content_length is not None
        and response.content_length > max_bytes
    ):
        raise UPnPInspectionError(
            "Description exceeds byte limit",
            code=InspectionErrorCode.RESPONSE_TOO_LARGE,
        )
    content = await response.content.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise UPnPInspectionError(
            "Description exceeds byte limit",
            code=InspectionErrorCode.RESPONSE_TOO_LARGE,
        )
    return content


class UPnPInspector:
    """Fetch bounded local UPnP XML; never invoke advertised actions."""

    def __init__(
        self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        max_depth: int = DEFAULT_MAX_EMBEDDED_DEPTH,
    ) -> None:
        if timeout <= 0 or max_bytes < 1 or max_concurrency < 1 or max_depth < 0:
            raise ValueError("Invalid UPnP inspection limits")
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_depth = max_depth
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def inspect_observation(self, observation: DiscoveryObservation) -> UPnPDevice:
        """Inspect a discovered SSDP observation without changing its state."""
        return await self.inspect(
            location_from_observation(observation),
            expected_addresses=_source_addresses(observation),
        )

    async def inspect_observations(
        self, observations: list[DiscoveryObservation] | tuple[DiscoveryObservation, ...]
    ) -> dict[str, UPnPDevice]:
        """Inspect each unique LOCATION once; failures propagate to the caller."""
        locations: dict[str, set[str]] = {}
        for item in observations:
            location = location_from_observation(item)
            source = _source_addresses(item)
            if location in locations:
                locations[location].intersection_update(source)
            else:
                locations[location] = set(source)
        if any(not addresses for addresses in locations.values()):
            raise UPnPInspectionError(
                "Conflicting SSDP source addresses for a shared LOCATION",
                code=InspectionErrorCode.SOURCE_ADDRESS_MISMATCH,
            )
        results = await asyncio.gather(*(
            self.inspect(location, expected_addresses=frozenset(addresses))
            for location, addresses in locations.items()
        ))
        return dict(zip(locations, results, strict=True))

    async def inspect(
        self, location: str, *, expected_addresses: frozenset[str] | None = None
    ) -> UPnPDevice:
        """Inspect a LOCATION URL. DNS results and HTTP redirects are restricted."""
        host, port, _ = _validate_url(location)
        async with self._semaphore:
            try:
                async with asyncio.timeout(self.timeout):
                    # Resolve and pin a vetted address to prevent DNS rebinding.
                    infos = await asyncio.get_running_loop().getaddrinfo(
                        host, port, type=socket.SOCK_STREAM)
                    _validate_resolved_addresses(
                        {item[4][0] for item in infos}, expected_addresses
                    )
                    connector = aiohttp.TCPConnector(
                        resolver=_PinnedResolver(infos), use_dns_cache=False
                    )
                    async with aiohttp.ClientSession(
                        connector=connector, trust_env=False
                    ) as session:
                        async with session.get(location, allow_redirects=False) as response:
                            content = await _read_description(response, self.max_bytes)
                            return parse_description(content, location, max_depth=self.max_depth)
            except (TimeoutError, OSError, aiohttp.ClientError) as exc:
                raise UPnPInspectionError(
                    "UPnP description fetch failed", code=InspectionErrorCode.FETCH_FAILED
                ) from exc


class _PinnedResolver:
    """Supply only prevalidated DNS answers to aiohttp's connector."""

    def __init__(self, infos: list[tuple]) -> None:
        self._infos = infos

    async def resolve(self, host: str, port: int, family: int = 0) -> list[dict]:
        return [dict(host=item[4][0], hostname=host, port=port, family=item[0],
                     proto=item[2], flags=0) for item in self._infos]

    async def close(self) -> None:
        pass
