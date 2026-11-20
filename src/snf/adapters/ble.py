"""Bluetooth Low Energy discovery backed by Bleak."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from importlib.util import find_spec
from typing import Any, Literal, Protocol, cast

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
        self._delivered_rssi: dict[str, int] = {}
        self._expiry_task: asyncio.Task[None] | None = None
        self._running = False

    @staticmethod
    def _encode_manufacturer_data(values: dict[int, bytes]) -> dict[str, str]:
        encoded: dict[str, str] = {}
        for company_id, value in values.items():
            encoded[str(company_id)] = bytes(value).hex()
        return encoded

    @staticmethod
    def _encode_service_data(values: dict[str, bytes]) -> dict[str, str]:
        encoded: dict[str, str] = {}
        for uuid, value in values.items():
            encoded[str(uuid)] = bytes(value).hex()
        return encoded

    @staticmethod
    def _company_names(manufacturer_data: dict[str, str]) -> dict[str, str]:
        names: dict[str, str] = {}
        for company_id in manufacturer_data:
            resolved_name = company_name(int(company_id))
            if resolved_name is not None:
                names[company_id] = resolved_name
        return names

    @staticmethod
    def _service_names(uuids: tuple[str, ...]) -> dict[str, str]:
        names: dict[str, str] = {}
        for uuid in uuids:
            details = uuid_details(uuid, kind="service")
            if details is not None:
                names[uuid] = details["name"]
        return names

    @staticmethod
    def _advertised_services(uuids: tuple[str, ...]) -> tuple[Service, ...]:
        services: list[Service] = []
        for uuid in uuids:
            services.append(
                Service(name=uuid, service_type="bluetooth-le-advertised-service")
            )
        return tuple(services)

    @staticmethod
    def _enrich_metadata(metadata: dict[str, Any]) -> None:
        """Rebuild fields derived from the normalized advertisement evidence."""
        manufacturer_data = cast(dict[str, str], metadata["manufacturer_data"])
        service_data = cast(dict[str, str], metadata["service_data"])
        service_uuids = cast(tuple[str, ...], metadata["service_uuids"])
        local_name = cast(str | None, metadata["local_name"])

        raw_manufacturer_data: dict[int, bytes] = {}
        for company_id, value in manufacturer_data.items():
            raw_manufacturer_data[int(company_id)] = bytes.fromhex(value)

        metadata["device_identification"] = identify_ble_device(
            raw_manufacturer_data, local_name=local_name
        )
        metadata["company_names"] = BLEPlugin._company_names(manufacturer_data)
        metadata["service_names"] = BLEPlugin._service_names(service_uuids)
        metadata["service_data_names"] = BLEPlugin._service_names(tuple(service_data))

    @staticmethod
    def _to_device(device: _Addressable, advertisement_data: object) -> DiscoveryObservation:
        """Normalize a BLE advertisement into a discovery observation."""
        address = str(device.address)
        advertised_name = getattr(advertisement_data, "local_name", None)
        name = advertised_name or getattr(device, "name", None) or address
        raw_manufacturer_data = getattr(advertisement_data, "manufacturer_data", {}) or {}
        raw_service_data = getattr(advertisement_data, "service_data", {}) or {}
        service_uuids = tuple(getattr(advertisement_data, "service_uuids", ()) or ())

        metadata: dict[str, Any] = {
            "rssi": getattr(advertisement_data, "rssi", None),
            "tx_power": getattr(advertisement_data, "tx_power", None),
            "local_name": advertised_name,
            "service_uuids": service_uuids,
            "manufacturer_data": BLEPlugin._encode_manufacturer_data(raw_manufacturer_data),
            "service_data": BLEPlugin._encode_service_data(raw_service_data),
        }
        BLEPlugin._enrich_metadata(metadata)

        return DiscoveryObservation(
            protocol="ble",
            identifier=address,
            name=str(name),
            endpoints=(Endpoint("ble", address),),
            services=BLEPlugin._advertised_services(service_uuids),
            metadata=metadata,
        )

    @staticmethod
    def _reconcile(
        previous: DiscoveryObservation | None,
        current: DiscoveryObservation,
    ) -> DiscoveryObservation:
        """Preserve previously observed evidence absent from partial advertisements."""
        if previous is None:
            return current

        old = dict(previous.metadata)
        new = dict(current.metadata)

        for field in ("local_name", "tx_power"):
            if new[field] is None:
                new[field] = old.get(field)

        for field in ("manufacturer_data", "service_data"):
            previous_values = cast(dict[str, str], old.get(field, {}))
            current_values = cast(dict[str, str], new[field])
            new[field] = {**previous_values, **current_values}

        old_uuids = cast(tuple[str, ...], old["service_uuids"])
        current_uuids = cast(tuple[str, ...], new["service_uuids"])
        service_uuids = tuple(dict.fromkeys((*old_uuids, *current_uuids)))
        new["service_uuids"] = service_uuids
        BLEPlugin._enrich_metadata(new)

        name = new["local_name"] or (
            previous.name if previous.name != current.identifier else current.name
        )
        return DiscoveryObservation(
            protocol=current.protocol,
            identifier=current.identifier,
            name=str(name),
            endpoints=current.endpoints,
            services=BLEPlugin._advertised_services(service_uuids),
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

    @staticmethod
    def _has_observation_changed(
        previous: DiscoveryObservation, current: DiscoveryObservation
    ) -> bool:
        """Compare observation fields, excluding RSSI handled by its own policy."""
        previous_metadata = dict(previous.metadata)
        current_metadata = dict(current.metadata)
        previous_metadata.pop("rssi", None)
        current_metadata.pop("rssi", None)

        return (
            previous.name != current.name
            or previous.endpoints != current.endpoints
            or previous.services != current.services
            or previous_metadata != current_metadata
        )

    def _baseline_rssi(self, key: str) -> int | None:
        """Compare pending RSSI first, otherwise the last delivered RSSI."""
        pending = self._pending.get(key)

        if pending and pending[-1].state is not DiscoveryState.REMOVED:
            rssi = pending[-1].observation.metadata.get("rssi")
        else:
            rssi = self._delivered_rssi.get(key)

        return rssi if isinstance(rssi, int) else None

    def _is_rssi_change_significant(self, key: str, new_rssi: object) -> bool:
        """Apply the configured minimum RSSI change against the event baseline."""
        if not self.emit_rssi_updates or not isinstance(new_rssi, int):
            return False

        baseline = self._baseline_rssi(key)
        if baseline is None:
            return False

        return abs(baseline - new_rssi) >= self.rssi_update_threshold

    def _should_emit_update(
        self, key: str, previous: DiscoveryObservation, record: DiscoveryObservation
    ) -> bool:
        """Emit changed observations or RSSI updates exceeding the threshold."""
        if self._has_observation_changed(previous, record):
            return True

        return self._is_rssi_change_significant(key, record.metadata.get("rssi"))

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

        if previous is not None and not self._should_emit_update(key, previous, record):
            return
        self._enqueue(DiscoveryEvent(DiscoveryState.ADDED, record))

    async def start(self) -> None:
        from bleak import BleakScanner

        self._running = True
        self._events = asyncio.Queue()
        self._pending.clear()
        self._last_seen.clear()
        self._last_emitted.clear()
        self._delivered_rssi.clear()
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
                self._delivered_rssi.pop(address, None)
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
                if event.state is DiscoveryState.REMOVED:
                    self._delivered_rssi.pop(key, None)
                else:
                    rssi = event.observation.metadata.get("rssi")
                    if isinstance(rssi, int):
                        self._delivered_rssi[key] = rssi
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
