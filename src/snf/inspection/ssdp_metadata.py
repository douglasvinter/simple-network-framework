"""Conservative SSDP advertisement identity parsing, independent of the HTTP API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from snf.models import DiscoveryObservation


@dataclass(frozen=True, slots=True)
class AdvertisedDeviceMetadata:
    udn: str | None = None
    device_type: str | None = None
    friendly_name: str | None = None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _header(headers: Mapping[str, object], *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    return next(
        (value for key, raw in headers.items()
         if str(key).lower() in wanted and (value := _text(raw))),
        None,
    )


class SSDPMetadataParser:
    """Extract only identity attributes supported by advertised SSDP metadata."""

    def parse(self, observation: DiscoveryObservation) -> AdvertisedDeviceMetadata:
        udn = _text(observation.metadata.get("udn"))
        if not udn or not udn.lower().startswith("uuid:"):
            usn = _text(observation.metadata.get("usn"))
            udn = usn.split("::", 1)[0] if usn and usn.lower().startswith("uuid:") else None
        device_type = next(
            (value for service in observation.services
             if (value := _text(service.service_type))
             and value.lower().startswith("urn:")
             and ":device:" in value.lower()),
            None,
        )
        friendly_name = next(
            (value for service in observation.services
             if (value := _header(service.metadata, "friendlyName", "friendly-name"))),
            None,
        )
        return AdvertisedDeviceMetadata(udn, device_type, friendly_name)
