"""Deterministic entity projection from protocol-scoped observations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

from snf.models import DiscoveryObservation, Service


@dataclass(frozen=True, slots=True)
class NetworkEntity:
    """An evidence-based grouping, not a verified physical device."""

    id: str
    name: str
    observations: tuple[DiscoveryObservation, ...]
    services: tuple[Service, ...]
    identity_source: str


class EntityResolver:
    """Resolve snapshots without network I/O or cross-protocol guessing."""

    @staticmethod
    def _udn(observation: DiscoveryObservation) -> str | None:
        if observation.protocol != "ssdp":
            return None
        usn = observation.metadata.get("usn")
        if not isinstance(usn, str) or not usn.lower().startswith("uuid:"):
            return None
        try:
            return f"uuid:{UUID(usn.split('::', 1)[0][5:])}"
        except ValueError:
            return None

    def resolve(self, observations: Iterable[DiscoveryObservation]) -> tuple[NetworkEntity, ...]:
        groups: dict[str, list[DiscoveryObservation]] = {}
        for observation in observations:
            udn = self._udn(observation)
            if udn is not None:
                key = f"ssdp:{udn}"
            else:
                key = (
                    f"observation:{quote(observation.protocol, safe='')}:"
                    f"{quote(observation.identifier, safe='')}"
                )
            groups.setdefault(key, []).append(observation)

        entities: list[NetworkEntity] = []
        for key, members in sorted(groups.items()):
            ordered = tuple(sorted(members, key=lambda item: (item.protocol, item.identifier)))
            services: list[Service] = []
            for observation in ordered:
                for service in observation.services:
                    if service not in services:
                        services.append(service)
            entities.append(
                NetworkEntity(
                    id=key,
                    name=ordered[0].name,
                    observations=ordered,
                    services=tuple(services),
                    identity_source="ssdp_udn" if key.startswith("ssdp:uuid:") else "observation",
                )
            )
        return tuple(entities)
