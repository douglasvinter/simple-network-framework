"""Bounded in-memory inventory and event de-duplication."""

from __future__ import annotations

from collections import OrderedDict

from snf.models import Device, DiscoveryEvent, DiscoveryState


class DeviceRegistry:
    """Maintain the latest known device records and normalize lifecycle events."""

    def __init__(self, *, max_entries: int = 4096) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._devices: OrderedDict[tuple[str, str], Device] = OrderedDict()

    def process(self, event: DiscoveryEvent) -> DiscoveryEvent | None:
        """Return a meaningful normalized event, suppressing duplicate updates."""
        device = event.device
        key = device.identity
        previous = self._devices.get(key)

        if event.state is DiscoveryState.REMOVED:
            if previous is None:
                return None
            del self._devices[key]
            return DiscoveryEvent(DiscoveryState.REMOVED, previous)

        if previous is None:
            self._devices[key] = device
            self._trim()
            return DiscoveryEvent(DiscoveryState.ADDED, device)

        self._devices.move_to_end(key)
        if previous == device:
            return None

        self._devices[key] = device
        return DiscoveryEvent(DiscoveryState.UPDATED, device)

    def get(self, protocol: str, identifier: str) -> Device | None:
        """Return one device by its protocol-scoped identity."""
        return self._devices.get((protocol, identifier))

    def snapshot(self) -> tuple[Device, ...]:
        """Return a stable snapshot of the current inventory."""
        return tuple(self._devices.values())

    def _trim(self) -> None:
        while len(self._devices) > self.max_entries:
            self._devices.popitem(last=False)

    def __len__(self) -> int:
        return len(self._devices)
