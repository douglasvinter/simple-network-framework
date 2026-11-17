"""Bounded in-memory observation registry and event de-duplication."""

from __future__ import annotations

from collections import OrderedDict

from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState


class ObservationRegistry:
    """Maintain live protocol-scoped observations and normalize lifecycle events."""

    def __init__(self, *, max_entries: int = 4096) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._observations: OrderedDict[tuple[str, str], DiscoveryObservation] = OrderedDict()

    def process(self, event: DiscoveryEvent) -> DiscoveryEvent | None:
        """Return a meaningful normalized event, suppressing duplicate updates."""
        device = event.observation
        key = device.identity
        previous = self._observations.get(key)

        if event.state is DiscoveryState.REMOVED:
            if previous is None:
                return None
            del self._observations[key]
            return DiscoveryEvent(DiscoveryState.REMOVED, previous)

        if previous is None:
            self._observations[key] = device
            self._trim()
            return DiscoveryEvent(DiscoveryState.ADDED, device)

        self._observations.move_to_end(key)
        if previous == device:
            return None

        self._observations[key] = device
        return DiscoveryEvent(DiscoveryState.UPDATED, device)

    def get(self, protocol: str, identifier: str) -> DiscoveryObservation | None:
        """Return one device by its protocol-scoped identity."""
        return self._observations.get((protocol, identifier))

    def snapshot(self, *, protocol: str | None = None) -> tuple[DiscoveryObservation, ...]:
        """Return inventory records, optionally restricted to one protocol."""
        if protocol is None:
            return tuple(self._observations.values())
        return tuple(
            observation
            for observation in self._observations.values()
            if observation.protocol == protocol
        )

    def _trim(self) -> None:
        while len(self._observations) > self.max_entries:
            self._observations.popitem(last=False)

    def __len__(self) -> int:
        return len(self._observations)
