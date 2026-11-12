"""Shared, protocol-neutral discovery models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class ServiceState(StrEnum):
    """Lifecycle state reported by a discovery protocol."""

    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class Service:
    """A discovered service with protocol-specific metadata preserved."""

    protocol: str
    name: str
    address: str
    port: int | None = None
    service_type: str | None = None
    state: ServiceState = ServiceState.ADDED
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def identity(self) -> tuple[str, str, str, int | None]:
        """Return a stable key suitable for a discovery cache."""
        return (self.protocol, self.name, self.address, self.port)
