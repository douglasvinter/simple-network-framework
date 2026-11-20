"""Characterization of DNS-SD TXT property normalization.

These tests protect the existing decoding behavior during method extraction.
"""

from snf.adapters.mdns import _decode_properties


def test_decode_properties_preserves_utf8_and_string_conversion():
    properties = {
        b"name": "Café".encode(),
        "empty": None,
        12: 34,
        b"binary": bytes([255]),
    }

    assert _decode_properties(properties) == {
        "name": "Café",
        "empty": "",
        "12": "34",
        "binary": chr(0xFFFD),
    }


def test_decode_properties_does_not_mutate_input():
    original = {b"flag": None}
    assert _decode_properties(original) == {"flag": ""}
    assert original == {b"flag": None}
