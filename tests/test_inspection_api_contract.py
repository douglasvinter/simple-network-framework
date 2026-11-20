"""Regression coverage for public inspection HTTP contracts.

Exercise registered routes rather than private extraction helpers. Existing
test files remain unchanged.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sse_starlette")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from snf.api import create_router


class _Runtime:
    protocols = ("ssdp", "mdns", "ble")
    running = True

    def validate_protocol(self, protocol):
        if protocol not in self.protocols:
            raise ValueError("Unsupported discovery protocol")

    def snapshot(self, protocol=None):
        return ()

    def get(self, protocol, identifier):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protocol", "missing_message", "not_found_message"),
    [
        ("upnp", "An SSDP identifier is required", "SSDP observation not found"),
        ("mdns", "An mDNS identifier is required", "mDNS observation not found"),
        ("ble", "A BLE identifier is required", "BLE observation not found"),
    ],
)
async def test_inspection_http_error_contract(protocol, missing_message, not_found_message):
    app = FastAPI()
    app.include_router(create_router(_Runtime()))
    path = f"/discoveries/inspect/{protocol}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get(path)
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "INVALID_IDENTIFIER"
        assert missing.json()["error"]["message"] == missing_message

        unknown = await client.get(path, params={"identifier": "absent"})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "OBSERVATION_NOT_FOUND"
        assert unknown.json()["error"]["message"] == not_found_message
        assert unknown.json()["device" if protocol != "mdns" else "service"] is None
