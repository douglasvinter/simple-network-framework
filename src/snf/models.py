"""Protocol-neutral domain models for discovered network and Bluetooth devices."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class DiscoveryState(StrEnum):
    """Lifecycle state of a discovered device."""

    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """A transport-specific way to reach a device or one of its services."""

    transport: str
    address: str
    port: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Service:
    """A service advertised by a discovered device."""

    name: str
    service_type: str | None = None
    endpoints: tuple[Endpoint, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Device:
    """A protocol-scoped inventory record.

    The identifier is scoped by protocol. Two protocols discovering the same
    physical device remain separate records until a consumer can correlate them
    using stronger evidence.
    """

    protocol: str
    identifier: str
    name: str
    endpoints: tuple[Endpoint, ...] = ()
    services: tuple[Service, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def identity(self) -> tuple[str, str]:
        """Return the stable, protocol-scoped identity for this observation."""
        return (self.protocol, self.identifier)


@dataclass(frozen=True, slots=True)
class DiscoveryEvent:
    """A lifecycle event for a discovered device."""

    state: DiscoveryState
    device: Device
