"""Read-only UPnP device-description inspection with bounded, local-only HTTP access."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp

from snf.models import DiscoveryObservation


class UPnPInspectionError(ValueError):
    """Failed inspection with a stable code and optional bounded response."""

    def __init__(
        self, message: str, *, code: str = "INSPECTION_FAILED",
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


def _child_text(element: ET.Element, name: str) -> str | None:
    child = next((item for item in element if item.tag.rsplit("}", 1)[-1] == name), None)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element if item.tag.rsplit("}", 1)[-1] == name]


def _device(element: ET.Element, base_url: str, depth: int, max_depth: int) -> UPnPDevice:
    if depth > max_depth:
        raise UPnPInspectionError("UPnP embedded-device nesting limit exceeded")
    services: list[UPnPService] = []
    embedded: list[UPnPDevice] = []
    for service_list in _children(element, "serviceList"):
        for service in _children(service_list, "service"):
            def link(field: str) -> str | None:
                value = _child_text(service, field)
                return urljoin(base_url, value) if value else None
            services.append(UPnPService(
                _child_text(service, "serviceType") or "",
                _child_text(service, "serviceId") or "",
                link("SCPDURL"), link("controlURL"), link("eventSubURL"),
            ))
    for device_list in _children(element, "deviceList"):
        for child in _children(device_list, "device"):
            embedded.append(_device(child, base_url, depth + 1, max_depth))
    return UPnPDevice(
        udn=_child_text(element, "UDN"),
        device_type=_child_text(element, "deviceType"),
        friendly_name=_child_text(element, "friendlyName"),
        manufacturer=_child_text(element, "manufacturer"),
        model_name=_child_text(element, "modelName"),
        model_number=_child_text(element, "modelNumber"),
        services=tuple(services),
        embedded_devices=tuple(embedded),
    )


def parse_description(xml: bytes, location: str, *, max_depth: int = 8) -> UPnPDevice:
    """Parse UPnP description XML without fetching linked service documents."""
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise UPnPInspectionError("DTD and entity declarations are not permitted")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        if not xml.lstrip().startswith(b"<"):
            raise UPnPInspectionError(
                "Endpoint did not return a UPnP XML description",
                code="UNSUPPORTED_DESCRIPTION_FORMAT",
                raw_response=xml.decode("utf-8", errors="replace"),
            ) from exc
        raise UPnPInspectionError(
            "Malformed UPnP description XML", code="MALFORMED_DESCRIPTION",
            raw_response=xml.decode("utf-8", errors="replace"),
        ) from exc
    if root.tag.rsplit("}", 1)[-1] != "root":
        raise UPnPInspectionError(
            "Not a UPnP root description", code="UNSUPPORTED_DESCRIPTION_FORMAT",
            raw_response=xml.decode("utf-8", errors="replace"),
        )
    device = next(iter(_children(root, "device")), None)
    if device is None:
        raise UPnPInspectionError(
            "Missing UPnP root device", code="UNSUPPORTED_DESCRIPTION_FORMAT",
            raw_response=xml.decode("utf-8", errors="replace"),
        )
    return _device(device, location, 0, max_depth)


def _local_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (ip.is_global or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved)


def _validate_url(url: str) -> tuple[str, int, str]:
    parts = urlsplit(url)
    if parts.scheme != "http" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise UPnPInspectionError("Only plain HTTP device descriptions without credentials are allowed")
    try:
        port = parts.port or 80
    except ValueError as exc:
        raise UPnPInspectionError("Invalid UPnP description port") from exc
    if not 1 <= port <= 65535:
        raise UPnPInspectionError("Invalid UPnP description port")
    return parts.hostname, port, parts.path or "/"


def location_from_observation(observation: DiscoveryObservation) -> str:
    """Extract LOCATION only from an SSDP observation, never an arbitrary endpoint."""
    if observation.protocol != "ssdp":
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
            code="SOURCE_ADDRESS_UNAVAILABLE",
        )
    return frozenset(addresses)


class UPnPInspector:
    """Fetch bounded local UPnP XML; never invoke advertised actions."""

    def __init__(self, *, timeout: float = 3.0, max_bytes: int = 262144,
                 max_concurrency: int = 4, max_depth: int = 8) -> None:
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
                code="SOURCE_ADDRESS_MISMATCH",
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
                    addresses = {item[4][0] for item in infos}
                    if not addresses or not all(_local_address(ip) for ip in addresses):
                        raise UPnPInspectionError("LOCATION must resolve exclusively to private LAN addresses")
                    normalized = {str(ipaddress.ip_address(ip)) for ip in addresses}
                    if expected_addresses is not None and (
                        not expected_addresses or not normalized.issubset(expected_addresses)
                    ):
                        raise UPnPInspectionError(
                            "LOCATION address does not match the SSDP source address",
                            code="SOURCE_ADDRESS_MISMATCH",
                        )
                    connector = aiohttp.TCPConnector(resolver=_PinnedResolver(infos), use_dns_cache=False)
                    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
                        async with session.get(location, allow_redirects=False) as response:
                            if response.status != 200:
                                raise UPnPInspectionError(f"Unexpected HTTP status: {response.status}")
                            if response.content_length is not None and response.content_length > self.max_bytes:
                                raise UPnPInspectionError("Description exceeds byte limit", code="RESPONSE_TOO_LARGE")
                            content = await response.content.read(self.max_bytes + 1)
                            if len(content) > self.max_bytes:
                                raise UPnPInspectionError("Description exceeds byte limit", code="RESPONSE_TOO_LARGE")
                            return parse_description(content, location, max_depth=self.max_depth)
            except (TimeoutError, OSError, aiohttp.ClientError) as exc:
                raise UPnPInspectionError("UPnP description fetch failed", code="FETCH_FAILED") from exc


class _PinnedResolver:
    """Supply only prevalidated DNS answers to aiohttp's connector."""

    def __init__(self, infos: list[tuple]) -> None:
        self._infos = infos

    async def resolve(self, host: str, port: int, family: int = 0) -> list[dict]:
        return [dict(host=item[4][0], hostname=host, port=port, family=item[0],
                     proto=item[2], flags=0) for item in self._infos]

    async def close(self) -> None:
        pass
