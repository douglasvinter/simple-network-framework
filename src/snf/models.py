"""Shared, protocol-neutral discovery models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


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
    def identity(self) -> tuple[str, str, str | None]:
        """Return a protocol-scoped identity stable across endpoint changes."""
        return (self.protocol, self.name, self.service_type)
