"""Storage contract for historical discovery observations.

Storage is independent from the live discovery registry. A REMOVED event
does not delete a remembered device.
"""

from __future__ import annotations

from typing import Protocol

from snf.models import DiscoveryObservation


class ObservationStorage(Protocol):
    """Asynchronous key/value storage keyed by (protocol, identifier)."""

    async def get(self, protocol: str, identifier: str) -> DiscoveryObservation | None: ...

    async def upsert(self, device: DiscoveryObservation) -> None: ...

    async def remove(self, protocol: str, identifier: str) -> None: ...

    async def snapshot(self, *, protocol: str | None = None) -> tuple[DiscoveryObservation, ...]: ...


class InMemoryStorage(ObservationStorage):
    """Reference storage driver; records survive only as long as this instance."""

    def __init__(self) -> None:
        self._observations: dict[tuple[str, str], DiscoveryObservation] = {}

    async def get(self, protocol: str, identifier: str) -> DiscoveryObservation | None:
        return self._observations.get((protocol, identifier))

    async def upsert(self, device: DiscoveryObservation) -> None:
        self._observations[device.identity] = device

    async def remove(self, protocol: str, identifier: str) -> None:
        self._observations.pop((protocol, identifier), None)

    async def snapshot(self, *, protocol: str | None = None) -> tuple[DiscoveryObservation, ...]:
        if protocol is None:
            return tuple(self._observations.values())
        return tuple(device for device in self._observations.values() if device.protocol == protocol)
