"""Bluetooth Low Energy discovery backed by Bleak."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any, Literal, Protocol

from snf.bluetooth.assigned_numbers import company_name, uuid_details
from snf.bluetooth.fingerprints import identify_ble_device
from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState, Endpoint, Service


class _Addressable(Protocol):
    address: str


_LOGGER = logging.getLogger(__name__)


class BLEPlugin:
    """Discover BLE peripherals from advertisements without pairing or connecting."""

    name = "ble"

    def __init__(
        self,
        *,
        service_uuids: list[str] | None = None,
        scanning_mode: Literal["active", "passive"] = "active",
        device_timeout: float = 15.0,
        rssi_update_threshold: int = 5,
        emit_rssi_updates: bool = False,
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
        self.emit_rssi_updates = emit_rssi_updates
        self._scanner: Any = None
        self._events: asyncio.Queue[str | None] = asyncio.Queue()
        self._pending: dict[str, list[DiscoveryEvent]] = {}
        self._last_seen: dict[str, float] = {}
        self._last_emitted: dict[str, DiscoveryObservation] = {}
        self._expiry_task: asyncio.Task[None] | None = None
        self._running = False

    @staticmethod
    def _to_device(device: _Addressable, advertisement_data: object) -> DiscoveryObservation:
        """Normalize Bleak's public BLEDevice and AdvertisementData objects."""
        address = str(device.address)
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
        identification = identify_ble_device(
            dict(getattr(advertisement_data, "manufacturer_data", {}) or {}),
            local_name=advertised_name,
        )
        endpoint = Endpoint("ble", address)
        services = tuple(
            Service(name=uuid, service_type="bluetooth-le-advertised-service")
            for uuid in service_uuids
        )
        return DiscoveryObservation(
            protocol="ble",
            identifier=address,
            name=str(name),
            endpoints=(endpoint,),
            services=services,
            metadata={
                "rssi": rssi,
                "tx_power": tx_power,
                "local_name": advertised_name,
                "device_identification": identification,
                "service_uuids": service_uuids,
                "manufacturer_data": manufacturer_data,
                "company_names": {
                    key: name
                    for key in manufacturer_data
                    if (name := company_name(int(key))) is not None
                },
                "service_names": {
                    uuid: details["name"]
                    for uuid in service_uuids
                    if (details := uuid_details(uuid, kind="service")) is not None
                },
                "service_data_names": {
                    uuid: details["name"]
                    for uuid in service_data
                    if (details := uuid_details(uuid, kind="service")) is not None
                },
                "service_data": service_data,
            },
        )

    @staticmethod
    def _reconcile(
        previous: DiscoveryObservation | None,
        current: DiscoveryObservation,
    ) -> DiscoveryObservation:
        """Keep last observed fields when a partial advertisement omits them."""
        if previous is None:
            return current

        old = dict(previous.metadata)
        new = dict(current.metadata)
        for field in ("local_name", "tx_power"):
            if new[field] is None:
                new[field] = old.get(field)
        for field in ("manufacturer_data", "service_data"):
            new[field] = {**old.get(field, {}), **new[field]}

        # Derived metadata is recalculated only for fields affected by merging.
        new["device_identification"] = identify_ble_device(
            {int(key): bytes.fromhex(value) for key, value in new["manufacturer_data"].items()},
            local_name=new["local_name"],
        )
        new["company_names"] = {
            key: company_name(int(key))
            for key in new["manufacturer_data"]
            if company_name(int(key)) is not None
        }
        new["service_data_names"] = {
            uuid: details["name"]
            for uuid in new["service_data"]
            if (details := uuid_details(uuid, kind="service")) is not None
        }
        uuids = tuple(dict.fromkeys((*old["service_uuids"], *new["service_uuids"])))
        new["service_uuids"] = uuids
        new["service_names"] = {
            uuid: details["name"]
            for uuid in uuids
            if (details := uuid_details(uuid, kind="service")) is not None
        }
        services = tuple(
            Service(name=uuid, service_type="bluetooth-le-advertised-service")
            for uuid in uuids
        )
        name = new["local_name"] or (
            previous.name if previous.name != current.identifier else current.name
        )
        return DiscoveryObservation(
            protocol=current.protocol,
            identifier=current.identifier,
            name=str(name),
            endpoints=current.endpoints,
            services=services,
            metadata=new,
        )

    def _enqueue(self, event: DiscoveryEvent) -> None:
        """Coalesce observations without losing removal/rediscovery transitions."""
        key = event.observation.identifier
        pending = self._pending.get(key)
        if pending is None:
            self._pending[key] = [event]
            self._events.put_nowait(key)
        elif event.state is DiscoveryState.REMOVED:
            if pending[-1].state is DiscoveryState.REMOVED:
                pending[-1] = event
            else:
                pending.append(event)
        elif pending[-1].state is DiscoveryState.REMOVED:
            pending.append(event)
        else:
            pending[-1] = event

    def _on_advertisement(self, device: _Addressable, advertisement_data: object) -> None:
        if not self._running:
            return
        key = str(device.address)
        current = self._to_device(device, advertisement_data)
        self._last_seen[key] = asyncio.get_running_loop().time()
        previous = self._last_emitted.get(key)
        record = self._reconcile(previous, current)
        if previous is not None and record != current:
            _LOGGER.debug("Reconciled BLE advertisement %s into device %s", key, record.identifier)
        self._last_emitted[key] = record

        if previous is not None:
            old_metadata = dict(previous.metadata)
            new_metadata = dict(record.metadata)
            old_rssi = old_metadata.pop("rssi", None)
            new_rssi = new_metadata.pop("rssi", None)
            unchanged = (
                previous.name == record.name
                and previous.endpoints == record.endpoints
                and previous.services == record.services
                and old_metadata == new_metadata
            )
            # Compare against the queued event, not the last advertisement.
            # Small consecutive fluctuations must not hide a cumulative change.
            pending = self._pending.get(key)
            baseline_rssi = (
                pending[-1].observation.metadata.get("rssi")
                if pending and pending[-1].state is not DiscoveryState.REMOVED
                else old_rssi
            )
            rssi_significant = (
                self.emit_rssi_updates
                and isinstance(baseline_rssi, int)
                and isinstance(new_rssi, int)
                and abs(baseline_rssi - new_rssi) >= self.rssi_update_threshold
            )
            if unchanged and not rssi_significant:
                return
        self._enqueue(DiscoveryEvent(DiscoveryState.ADDED, record))

    async def start(self) -> None:
        from bleak import BleakScanner

        self._running = True
        self._events = asyncio.Queue()
        self._pending.clear()
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
        self._expiry_task = asyncio.create_task(self._expire_stale_devices(), name="snf:ble-expiry")
        _LOGGER.debug("BLE scanning started")

    async def _expire_stale_devices(self) -> None:
        interval = min(self.device_timeout / 2, 5.0)
        while self._running:
            await asyncio.sleep(interval)
            now = asyncio.get_running_loop().time()
            expired = [
                address
                for address, seen_at in self._last_seen.items()
                if now - seen_at >= self.device_timeout
            ]
            for address in expired:
                self._last_seen.pop(address, None)
                self._last_emitted.pop(address, None)
                device = DiscoveryObservation(protocol=self.name, identifier=address, name=address)
                self._enqueue(DiscoveryEvent(DiscoveryState.REMOVED, device))

    async def discover(self) -> AsyncIterator[DiscoveryEvent]:
        if not self._running:
            raise RuntimeError("BLEPlugin.start() must be called before discover()")
        while self._running:
            key = await self._events.get()
            if key is None:
                return
            for event in self._pending.pop(key, ()):
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
