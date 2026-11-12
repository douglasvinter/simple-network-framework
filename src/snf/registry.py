"""Bounded event de-duplication for protocol discovery streams."""

from __future__ import annotations

from collections import OrderedDict

from snf.models import Service, ServiceState


class ServiceRegistry:
    """Suppress repeated announcements while preserving lifecycle changes."""

    def __init__(self, *, max_entries: int = 4096) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._services: OrderedDict[tuple[str, str, str | None], Service] = OrderedDict()

    @staticmethod
    def _key(service: Service) -> tuple[str, str, str | None]:
        # Address/port are deliberately excluded: endpoint changes are updates.
        return (service.protocol, service.name, service.service_type)

    @staticmethod
    def _content(service: Service) -> tuple[object, ...]:
        return (service.address, service.port, service.service_type, dict(service.metadata))

    def process(self, service: Service) -> Service | None:
        """Return a normalized event, or None when it is a duplicate/no-op."""
        key = self._key(service)
        previous = self._services.get(key)

        if service.state is ServiceState.REMOVED:
            if previous is None:
                return None
            del self._services[key]
            return service

        if previous is None:
            self._services[key] = service
            self._trim()
            return service

        self._services.move_to_end(key)
        if self._content(previous) == self._content(service):
            return None

        updated = Service(
            protocol=service.protocol,
            name=service.name,
            address=service.address,
            port=service.port,
            service_type=service.service_type,
            state=ServiceState.UPDATED,
            metadata=service.metadata,
        )
        self._services[key] = updated
        return updated

    def _trim(self) -> None:
        while len(self._services) > self.max_entries:
            self._services.popitem(last=False)

    def __len__(self) -> int:
        return len(self._services)
