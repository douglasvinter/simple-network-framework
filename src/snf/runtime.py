"""Single-consumer background discovery runtime with bounded event subscriptions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import suppress
from typing import Literal, Self, cast, overload

from snf.engine import DiscoveryEngine
from snf.entities import EntityResolver, NetworkEntity
from snf.inspection.ble import BLEDeviceDetails, BLEInspector
from snf.inspection.error_codes import InspectionErrorCode
from snf.inspection.mdns import MDNSInspector, MDNSServiceDetails
from snf.inspection.upnp import UPnPDevice, UPnPInspector
from snf.models import DiscoveryEvent, DiscoveryObservation
from snf.plugins import DiscoveryPlugin, create_plugins
from snf.storage import InMemoryStorage, ObservationStorage

_LOGGER = logging.getLogger(__name__)
_CLOSED = object()


class InspectionLookupError(ValueError):
    """An inspection target cannot be resolved from current runtime observations."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class DiscoverySubscription:
    """Future-only, bounded event subscription; close to release resources."""

    def __init__(self, runtime: NetworkRuntime, protocol: str | None, capacity: int) -> None:
        self._runtime = runtime
        self.protocol = protocol
        self._queue: asyncio.Queue[DiscoveryEvent | object] = asyncio.Queue(capacity)
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._runtime._subscribers.discard(self)
        # Ensure a blocked reader wakes even if its buffer is full.
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(_CLOSED)

    def __aiter__(self) -> AsyncIterator[DiscoveryEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[DiscoveryEvent]:
        try:
            while True:
                event = await self._queue.get()
                if event is _CLOSED:
                    return
                yield cast(DiscoveryEvent, event)
        finally:
            self.close()


class NetworkRuntime:
    """Own one discovery engine consumer and publish independent event streams."""

    def __init__(
        self,
        plugins: Iterable[DiscoveryPlugin] | None = None,
        *,
        storage: ObservationStorage | None = None,
        subscriber_buffer_size: int = 128,
        strict: bool = False,
    ) -> None:
        if subscriber_buffer_size < 1:
            raise ValueError("subscriber_buffer_size must be at least 1")
        self._plugins = tuple(plugins) if plugins is not None else None
        self._storage = storage if storage is not None else InMemoryStorage()
        self._strict = strict
        self._capacity = subscriber_buffer_size
        self._engine: DiscoveryEngine | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribers: set[DiscoverySubscription] = set()
        self._protocols: tuple[str, ...] = ()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def protocols(self) -> tuple[str, ...]:
        return self._protocols

    def validate_protocol(self, protocol: str | None) -> None:
        if protocol is not None and protocol not in self._protocols:
            raise ValueError(
                f"Unsupported protocol {protocol!r}; available: "
                f"{', '.join(self._protocols) or 'none'}"
            )

    def snapshot(self, *, protocol: str | None = None) -> tuple[DiscoveryObservation, ...]:
        self.validate_protocol(protocol)
        if self._engine is None:
            raise RuntimeError("Discovery has not started")
        return self._engine.snapshot(protocol=protocol)

    def get(self, protocol: str, identifier: str) -> DiscoveryObservation | None:
        """Find one live protocol-scoped observation without network I/O."""
        self.validate_protocol(protocol)
        return next(
            (item for item in self.snapshot(protocol=protocol) if item.identifier == identifier),
            None,
        )

    @overload
    async def inspect(self, protocol: Literal["ble"], identifier: str) -> BLEDeviceDetails: ...

    @overload
    async def inspect(self, protocol: Literal["mdns"], identifier: str) -> MDNSServiceDetails: ...

    @overload
    async def inspect(self, protocol: Literal["ssdp"], identifier: str) -> UPnPDevice: ...

    @overload
    async def inspect(
        self, protocol: str, identifier: str
    ) -> BLEDeviceDetails | MDNSServiceDetails | UPnPDevice: ...

    async def inspect(
        self, protocol: str, identifier: str
    ) -> BLEDeviceDetails | MDNSServiceDetails | UPnPDevice:
        """Inspect a live observation on demand without mutating discovery state.

        This method performs protocol-specific network I/O. It does not lock,
        serialize, cache, or retry concurrent inspections of the same target.
        Consumers must coordinate inspections when their devices require it.
        """
        if not identifier or not identifier.strip():
            raise InspectionLookupError(
                f"An inspection identifier is required for {protocol}",
                code=InspectionErrorCode.INVALID_IDENTIFIER.get_code(),
            )
        self.validate_protocol(protocol)
        if protocol not in ("ssdp", "mdns", "ble"):
            raise InspectionLookupError(
                f"Inspection is not supported for protocol {protocol!r}",
                code=InspectionErrorCode.UNSUPPORTED_PROTOCOL.get_code(),
            )
        observation = self.get(protocol, identifier)
        if observation is None:
            raise InspectionLookupError(
                f"{protocol.upper()} observation not found",
                code=InspectionErrorCode.OBSERVATION_NOT_FOUND.get_code(),
            )
        if protocol == "ssdp":
            return await UPnPInspector().inspect_observation(observation)
        if protocol == "mdns":
            return await MDNSInspector().inspect_observation(observation)
        return await BLEInspector().inspect_observation(observation)

    def entities(self, *, protocol: str | None = None) -> tuple[NetworkEntity, ...]:
        return EntityResolver().resolve(self.snapshot(protocol=protocol))

    def observation_map(
        self, *, protocol: str | None = None
    ) -> dict[str, dict[str, DiscoveryObservation]]:
        result: dict[str, dict[str, DiscoveryObservation]] = {}
        for observation in self.snapshot(protocol=protocol):
            result.setdefault(observation.protocol, {})[observation.identifier] = observation
        return result

    def subscribe(self, *, protocol: str | None = None) -> DiscoverySubscription:
        self.validate_protocol(protocol)
        if not self.running:
            raise RuntimeError("Discovery is not running")
        subscription = DiscoverySubscription(self, protocol, self._capacity)
        self._subscribers.add(subscription)
        return subscription

    def _publish(self, event: DiscoveryEvent) -> None:
        for subscriber in tuple(self._subscribers):
            if (
                subscriber.protocol is not None
                and subscriber.protocol != event.observation.protocol
            ):
                continue
            try:
                subscriber._queue.put_nowait(event)
            except asyncio.QueueFull:
                _LOGGER.warning("Disconnecting slow discovery subscriber")
                subscriber.close()

    def _close_subscribers(self) -> None:
        for subscriber in tuple(self._subscribers):
            subscriber.close()

    async def _consume(self, engine: DiscoveryEngine) -> None:
        try:
            async for event in engine.discover():
                self._publish(event)
        finally:
            self._close_subscribers()

    @staticmethod
    def _log_failure(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            _LOGGER.error("Discovery consumer stopped unexpectedly", exc_info=error)

    async def __aenter__(self) -> Self:
        if self._engine is not None:
            raise RuntimeError("NetworkRuntime is already started")
        plugins = self._plugins if self._plugins is not None else tuple(create_plugins())
        engine = DiscoveryEngine(plugins, storage=self._storage, strict=self._strict)
        await engine.__aenter__()
        self._engine = engine
        self._protocols = tuple(sorted(plugin.name for plugin in plugins))
        self._task = asyncio.create_task(self._consume(engine), name="snf:runtime")
        self._task.add_done_callback(self._log_failure)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        task, engine = self._task, self._engine
        self._task = None
        self._engine = None
        self._protocols = ()
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._close_subscribers()
        if engine is not None:
            await engine.stop()
