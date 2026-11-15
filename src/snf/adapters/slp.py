"""SLP adapter using the OpenSLP project's slptool User Agent.

OpenSLP is an external native dependency. This adapter deliberately delegates
SLPv2 wire encoding, multicast convergence, scopes, and Directory Agent handling
to OpenSLP rather than implementing RFC 2608 itself.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

from snf.models import Service


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
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.command_timeout
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"SLP command timed out: {' '.join(command)}")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"OpenSLP command failed ({process.returncode}): {detail}"
            )
        return [
            line.strip()
            for line in stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]

    async def start(self) -> None:
        self._running = True
        self._stop_event.clear()

    @staticmethod
    def _to_service(service_url: str) -> Service | None:
        value = service_url.strip()
        lifetime: str | None = None
        if "," in value:
            candidate, possible_lifetime = value.rsplit(",", 1)
            if possible_lifetime.isdigit():
                value, lifetime = candidate, possible_lifetime

        prefix, separator, endpoint = value.partition("://")
        if not separator:
            return Service(
                protocol="slp",
                name=value,
                address="",
                metadata={"url": value, "lifetime": lifetime},
            )
        service_type = prefix.removeprefix("service:")
        parsed = urlsplit(f"slp://{endpoint}")
        return Service(
            protocol="slp",
            name=value,
            address=parsed.hostname or "",
            port=parsed.port,
            service_type=service_type or None,
            metadata={"url": value, "lifetime": lifetime},
        )

    async def discover(self) -> AsyncIterator[Service]:
        if not self._running:
            raise RuntimeError("SLPPlugin.start() must be called before discover()")

        while self._running:
            service_types = self.service_types
            if service_types is None:
                service_types = await self._run("findsrvtypes")

            for service_type in service_types:
                if not self._running:
                    break
                for service_url in await self._run("findsrvs", service_type):
                    if service_url in self._seen:
                        continue
                    self._seen.add(service_url)
                    service = self._to_service(service_url)
                    if service is not None:
                        yield service

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
