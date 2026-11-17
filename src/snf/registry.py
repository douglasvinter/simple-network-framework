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
        """Normalize an event; use process_events() to observe capacity evictions."""
        events = self.process_events(event)
        return next((item for item in events if item.state is not DiscoveryState.EVICTED), None)

    def process_events(self, event: DiscoveryEvent) -> tuple[DiscoveryEvent, ...]:
        """Return normalized events, including any capacity eviction.

        EVICTED means a bounded cache entry was forgotten, not that the device
        disappeared. Eviction is emitted before the new ADDED event.
        """
        device = event.observation
        key = device.identity
        previous = self._observations.get(key)

        if event.state is DiscoveryState.EVICTED:
            raise ValueError("EVICTED is registry-generated, not a plugin event")

        if event.state is DiscoveryState.REMOVED:
            if previous is None:
                return ()
            del self._observations[key]
            return (DiscoveryEvent(DiscoveryState.REMOVED, previous),)

        if previous is None:
            self._observations[key] = device
            evicted = self._trim()
            return (*evicted, DiscoveryEvent(DiscoveryState.ADDED, device))

        self._observations.move_to_end(key)
        if previous == device:
            return ()

        self._observations[key] = device
        return (DiscoveryEvent(DiscoveryState.UPDATED, device),)

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

    def _trim(self) -> tuple[DiscoveryEvent, ...]:
        evicted: list[DiscoveryEvent] = []
        while len(self._observations) > self.max_entries:
            _, observation = self._observations.popitem(last=False)
            evicted.append(DiscoveryEvent(DiscoveryState.EVICTED, observation))
        return tuple(evicted)

    def __len__(self) -> int:
        return len(self._observations)
