"""Offline Bluetooth assigned-number lookups.

Data is a vendored snapshot of Nordic Semiconductor's Bluetooth Numbers Database,
which mirrors Bluetooth SIG assigned numbers and includes explicitly sourced extensions.
A company identifier identifies the data namespace, not necessarily a device's brand.
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

_BASE_UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"


@cache
def _entries(filename: str) -> list[dict[str, Any]]:
    resource = files("snf").joinpath("bluetooth", "data", filename)
    with resource.open("r", encoding="utf-8") as handle:
        result: list[dict[str, Any]] = json.load(handle)
    return result


@cache
def _companies() -> dict[int, str]:
    return {int(item["code"]): str(item["name"]) for item in _entries("company_ids.json")}


@cache
def _uuids(kind: str) -> dict[str, dict[str, str]]:
    filename = {
        "service": "service_uuids.json",
        "characteristic": "characteristic_uuids.json",
        "descriptor": "descriptor_uuids.json",
    }[kind]
    return {
        str(item["uuid"]).lower(): {
            "name": str(item["name"]),
            "source": str(item["source"]),
        }
        for item in _entries(filename)
    }


def company_name(company_id: int) -> str | None:
    """Resolve a Bluetooth SIG company identifier, without guessing the product brand."""
    return _companies().get(company_id)


def _normalize_uuid(value: str) -> str:
    normalized = value.strip().lower().removeprefix("0x")
    if len(normalized) == 36 and normalized.startswith("0000") and normalized.endswith(
        _BASE_UUID_SUFFIX
    ):
        return normalized[4:8]
    return normalized


def uuid_details(value: str, *, kind: str) -> dict[str, str] | None:
    """Resolve a service, characteristic or descriptor UUID with source attribution."""
    return _uuids(kind).get(_normalize_uuid(value))


def appearance_details(value: int) -> dict[str, str] | None:
    """Resolve the 16-bit GAP Appearance category and optional subcategory."""
    if not 0 <= value <= 0xFFFF:
        return None
    category, subcategory = value >> 6, value & 0x3F
    for entry in _entries("gap_appearance.json"):
        if entry["category"] != category:
            continue
        result = {"category": str(entry["name"])}
        for child in entry.get("subcategory", []):
            if child["value"] == subcategory:
                result["subcategory"] = str(child["name"])
                break
        return result
    return None
