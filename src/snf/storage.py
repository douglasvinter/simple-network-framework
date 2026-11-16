"""Storage contract for historical device records.

Storage is independent from the live discovery registry. A REMOVED event
does not delete a remembered device.
"""

from __future__ import annotations

from typing import Protocol

from snf.models import Device


class InventoryStorage(Protocol):
    """Asynchronous key/value storage keyed by (protocol, identifier)."""

    async def get(self, protocol: str, identifier: str) -> Device | None: ...

    async def upsert(self, device: Device) -> None: ...

    async def remove(self, protocol: str, identifier: str) -> None: ...

    async def snapshot(self, *, protocol: str | None = None) -> tuple[Device, ...]: ...


class InMemoryStorage:
    """Reference storage driver; records survive only as long as this instance."""

    def __init__(self) -> None:
        self._devices: dict[tuple[str, str], Device] = {}

    async def get(self, protocol: str, identifier: str) -> Device | None:
        return self._devices.get((protocol, identifier))

    async def upsert(self, device: Device) -> None:
        self._devices[device.identity] = device

    async def remove(self, protocol: str, identifier: str) -> None:
        self._devices.pop((protocol, identifier), None)

    async def snapshot(self, *, protocol: str | None = None) -> tuple[Device, ...]:
        if protocol is None:
            return tuple(self._devices.values())
        return tuple(device for device in self._devices.values() if device.protocol == protocol)
