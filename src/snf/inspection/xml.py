"""Reusable stateless XML element accessors for protocol description parsers."""

from __future__ import annotations

import xml.etree.ElementTree as ET


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element if local_name(item.tag) == name]


def child_text(element: ET.Element, name: str) -> str | None:
    child = next(iter(children(element, name)), None)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None
