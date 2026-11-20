"""Characterize API inspection error mapping before separating HTTP presentation."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sse_starlette")

from snf.api.inspection_responses import ble_error_status, mdns_error_status, upnp_error_status


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("UNSUPPORTED_DESCRIPTION_FORMAT", 422),
        ("MALFORMED_DESCRIPTION", 422),
        ("FETCH_FAILED", 502),
        ("SOURCE_ADDRESS_MISMATCH", 502),
    ],
)
def test_upnp_error_mapping(code, expected):
    assert upnp_error_status(code) == expected


@pytest.mark.parametrize("mapping", [ble_error_status, mdns_error_status])
def test_ble_and_mdns_error_mapping(mapping):
    assert mapping("INVALID_OBSERVATION") == 422
    assert mapping("CONNECTION_FAILED") == 502
    assert mapping("RESOLUTION_FAILED") == 502
