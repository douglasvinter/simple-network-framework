"""SLP adapter using the OpenSLP project's slptool User Agent."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState, Endpoint, Service


class SLPPlugin:
    """Discover SLP services through the OpenSLP slptool command."""

    name = "slp"

    def __init__(
        self,
        service_types: list[str] | None = None,
        *,
        scope: str | None = None,
        interval: float = 60.0,
        command: str = "slptool",
        command_timeout: float = 15.0,
    ) -> None:
        if interval <= 0 or command_timeout <= 0:
            raise ValueError("interval and command_timeout must be positive")
        executable = shutil.which(command)
        if executable is None:
            raise RuntimeError(
                "SLP support requires OpenSLP's slptool executable. "
                "Install OpenSLP and ensure slptool is on PATH."
            )
        self.service_types = service_types
        self.scope = scope
        self.interval = interval
        self.command = executable
        self.command_timeout = command_timeout
        self._running = False
        self._stop_event = asyncio.Event()
        self._seen: set[str] = set()

    async def _run(self, *arguments: str) -> list[str]:
        command = [self.command]
        if self.scope:
            command.extend(["-s", self.scope])
        command.extend(arguments)
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.command_timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"SLP command timed out: {' '.join(command)}") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"OpenSLP command failed ({process.returncode}): {detail}")
        return [
            line.strip()
            for line in stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

    async def start(self) -> None:
        self._seen.clear()
        self._running = True
        self._stop_event.clear()

    @staticmethod
    def _to_device(service_url: str) -> DiscoveryObservation:
        value = service_url.strip()
        lifetime: str | None = None
        if "," in value:
            candidate, possible_lifetime = value.rsplit(",", 1)
            if possible_lifetime.isdigit():
                value, lifetime = candidate, possible_lifetime

        prefix, separator, endpoint_value = value.partition("://")
        if not separator:
            return DiscoveryObservation(
                protocol="slp",
                identifier=value,
                name=value,
                metadata={"url": value, "lifetime": lifetime},
            )
        service_type = prefix.removeprefix("service:")
        parsed = urlsplit(f"slp://{endpoint_value}")
        endpoints = (Endpoint("ip", parsed.hostname, parsed.port),) if parsed.hostname else ()
        service = Service(name=value, service_type=service_type or None, endpoints=endpoints)
        return DiscoveryObservation(
            protocol="slp",
            identifier=value,
            name=value,
            endpoints=endpoints,
            services=(service,),
            metadata={"url": value, "lifetime": lifetime},
        )

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        if not self._running:
            raise RuntimeError("SLPPlugin.start() must be called before discover()")

        while self._running:
            service_types = self.service_types
            if service_types is None:
                service_types = await self._run("findsrvtypes")

            # Each completed scan is an authoritative snapshot for the configured
            # service types. Do not emit removals if a command fails mid-scan.
            current: dict[str, DiscoveryObservation] = {}
            for service_type in service_types:
                if not self._running:
                    break
                for service_url in await self._run("findsrvs", service_type):
                    observation = self._to_device(service_url)
                    current[observation.identifier] = observation

            if not self._running:
                break

            for identifier, observation in current.items():
                if identifier not in self._seen:
                    yield DiscoveryEvent(DiscoveryState.ADDED, observation)

            for identifier in self._seen - current.keys():
                yield DiscoveryEvent(
                    DiscoveryState.REMOVED, self._to_device(identifier)
                )

            self._seen = set(current)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
