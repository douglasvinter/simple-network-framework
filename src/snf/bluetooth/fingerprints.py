"""Conservative, read-only BLE product-family identification.

A manufacturer ID alone never identifies a model. Name-only advertisements are
not considered verified fingerprints: they are trivially spoofable and often
ambiguous. Only signatures backed by public decoder definitions are matched.
"""

from __future__ import annotations

from typing import TypedDict


class DeviceFingerprint(TypedDict):
    brand: str
    family: str
    category: str
    evidence: str
    source: str
    confidence: str


# Theengs APPLEAIRPODS decoder matches the *complete* manufacturer data
# prefix 4c00071901 (Apple company ID, little-endian, followed by 071901).
# Bleak already separates the company ID, so only 071901 remains.
_APPLE_AIRPODS_PREFIX = bytes.fromhex("071901")
_APPLE_SOURCE = (
    "https://github.com/theengs/decoder/blob/development/"
    "src/devices/APPLEAIRPODS_json.h"
)


def identify_ble_device(
    manufacturer_data: dict[int, bytes],
    *,
    local_name: str | None = None,
) -> DeviceFingerprint | None:
    """Identify a publicly documented BLE advertisement family, if unambiguous.

    `local_name` is accepted for future corroboration, never as sole evidence.
    Manufacturer data is not decoded for controls, telemetry or private fields.
    """
    _ = local_name
    apple = manufacturer_data.get(76)
    if apple is not None and apple.startswith(_APPLE_AIRPODS_PREFIX):
        return {
            "brand": "Apple/Beats",
            "family": "AirPods / Beats headphones",
            "category": "audio",
            "evidence": "company_id=76; manufacturer_payload_prefix=071901",
            "source": _APPLE_SOURCE,
            "confidence": "family_signature",
        }
    return None
