"""Bluetooth Low Energy discovery backed by Bleak."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any

from snf.models import Device, DiscoveryEvent, DiscoveryState, Endpoint, Service

_LOGGER = logging.getLogger(__name__)


class BLEPlugin:
    """Discover BLE peripherals from advertisements without pairing or connecting."""

    name = "ble"

    def __init__(
        self,
        *,
        service_uuids: list[str] | None = None,
        scanning_mode: str = "active",
        device_timeout: float = 15.0,
        rssi_update_threshold: int = 5,
    ) -> None:
        if device_timeout <= 0:
            raise ValueError("device_timeout must be positive")
        if rssi_update_threshold < 1:
            raise ValueError("rssi_update_threshold must be at least 1")
        if find_spec("bleak") is None:
            raise ImportError(
                "Install BLE support with: pip install 'simple-network-framework[ble]'"
            )
        self.service_uuids = service_uuids
        self.scanning_mode = scanning_mode
        self.device_timeout = device_timeout
        self.rssi_update_threshold = rssi_update_threshold
        self._scanner: Any = None
        self._events: asyncio.Queue[DiscoveryEvent | None] = asyncio.Queue()
        self._last_seen: dict[str, float] = {}
        self._last_emitted: dict[str, Device] = {}
        self._expiry_task: asyncio.Task[None] | None = None
        self._running = False

    @staticmethod
    def _to_device(device: object, advertisement_data: object) -> Device:
        """Normalize Bleak's public BLEDevice and AdvertisementData objects."""
        address = str(getattr(device, "address"))
        advertised_name = getattr(advertisement_data, "local_name", None)
        name = advertised_name or getattr(device, "name", None) or address
        rssi = getattr(advertisement_data, "rssi", None)
        tx_power = getattr(advertisement_data, "tx_power", None)
        service_uuids = tuple(getattr(advertisement_data, "service_uuids", ()) or ())
        manufacturer_data = {
            str(company_id): bytes(value).hex()
            for company_id, value in (
                getattr(advertisement_data, "manufacturer_data", {}) or {}
            ).items()
        }
        service_data = {
            str(uuid): bytes(value).hex()
            for uuid, value in (getattr(advertisement_data, "service_data", {}) or {}).items()
        }
        endpoint = Endpoint("ble", address)
        services = tuple(
            Service(name=uuid, service_type="bluetooth-le-advertised-service")
            for uuid in service_uuids
        )
        return Device(
            protocol="ble",
            identifier=address,
            name=str(name),
            endpoints=(endpoint,),
            services=services,
            metadata={
                "rssi": rssi,
                "tx_power": tx_power,
                "local_name": advertised_name,
                "service_uuids": service_uuids,
                "manufacturer_data": manufacturer_data,
                "service_data": service_data,
            },
        )

    def _on_advertisement(self, device: object, advertisement_data: object) -> None:
        if not self._running:
            return
        record = self._to_device(device, advertisement_data)
        self._last_seen[record.identifier] = asyncio.get_running_loop().time()
        previous = self._last_emitted.get(record.identifier)
        if previous is not None:
            previous_metadata = dict(previous.metadata)
            current_metadata = dict(record.metadata)
            previous_rssi = previous_metadata.pop("rssi", None)
            current_rssi = current_metadata.pop("rssi", None)
            same_advertisement = (
                previous.name == record.name
                and previous.endpoints == record.endpoints
                and previous.services == record.services
                and previous_metadata == current_metadata
            )
            rssi_change = (
                not isinstance(previous_rssi, int)
                or not isinstance(current_rssi, int)
                or abs(previous_rssi - current_rssi) >= self.rssi_update_threshold
            )
            if same_advertisement and not rssi_change:
                return
        self._last_emitted[record.identifier] = record
        self._events.put_nowait(DiscoveryEvent(DiscoveryState.ADDED, record))

    async def start(self) -> None:
        from bleak import BleakScanner

        self._running = True
        self._events = asyncio.Queue()
        self._last_seen.clear()
        self._last_emitted.clear()
        self._scanner = BleakScanner(
            detection_callback=self._on_advertisement,
            service_uuids=self.service_uuids,
            scanning_mode=self.scanning_mode,
        )
        try:
            await self._scanner.start()
        except BaseException:
            self._running = False
            with contextlib.suppress(Exception):
                await self._scanner.stop()
            self._scanner = None
            raise
        self._expiry_task = asyncio.create_task(
            self._expire_stale_devices(), name="snf:ble-expiry"
        )
        _LOGGER.debug("BLE scanning started")

    async def _expire_stale_devices(self) -> None:
        interval = min(self.device_timeout / 2, 5.0)
        while self._running:
            await asyncio.sleep(interval)
            now = asyncio.get_running_loop().time()
            expired = [
                address for address, seen_at in self._last_seen.items()
                if now - seen_at >= self.device_timeout
            ]
            for address in expired:
                self._last_seen.pop(address, None)
                self._last_emitted.pop(address, None)
                device = Device(
                    protocol=self.name, identifier=address, name=address
                )
                await self._events.put(
                    DiscoveryEvent(DiscoveryState.REMOVED, device)
                )

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        if not self._running:
            raise RuntimeError("BLEPlugin.start() must be called before discover()")
        while self._running:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def stop(self) -> None:
        self._running = False
        self._events.put_nowait(None)
        if self._expiry_task is not None:
            self._expiry_task.cancel()
            try:
                await self._expiry_task
            except asyncio.CancelledError:
                pass
            self._expiry_task = None
        if self._scanner is not None:
            await self._scanner.stop()
            self._scanner = None
        _LOGGER.debug("BLE scanning stopped")
