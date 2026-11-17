"""Protocol-neutral models for network discovery observations."""

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
class DiscoveryObservation:
    """A protocol-scoped observation, not a verified physical-device identity.

    The identifier is scoped by protocol. Observations from different protocols
    remain independent; consumers may correlate them using stronger evidence.
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
    observation: DiscoveryObservation
