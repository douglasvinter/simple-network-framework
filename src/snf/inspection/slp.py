"""Explicit, read-only SLP inspection using system-installed OpenSLP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from snf.models import DiscoveryObservation


SLPAttributeValue: TypeAlias = str | bytes | bool | tuple[str | bytes, ...]


class SLPInspectionError(ValueError):
    """Stable error code for failed SLP inspection."""

    def __init__(self, message: str, *, code: str = "INSPECTION_FAILED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SLPServiceDetails:
    url: str
    attributes: dict[str, SLPAttributeValue]


class SLPInspector:
    """Inspect one advertised SLP service without modifying discovery state."""

    def __init__(
        self, *, command: str = "slptool", scope: str | None = None,
        command_timeout: float = 15.0,
    ) -> None:
        self.command = command
        self.scope = scope
        self.command_timeout = command_timeout

    async def _run(self, *arguments: str) -> list[str]:
        raise NotImplementedError("Implement after inspection contract tests are reviewed")

    async def inspect_observation(
        self, observation: DiscoveryObservation
    ) -> SLPServiceDetails:
        raise NotImplementedError("Implement after inspection contract tests are reviewed")
