"""Characterize UPnP bounded HTTP body reads before transport extraction."""

from http import HTTPStatus
from types import SimpleNamespace

import pytest

pytest.importorskip("aiohttp")

from snf.inspection.upnp import UPnPInspectionError, _read_description


class _Body:
    def __init__(self, data):
        self.data = data
        self.limit = None

    async def read(self, limit):
        self.limit = limit
        return self.data[:limit]


@pytest.mark.asyncio
async def test_description_read_uses_one_byte_over_limit():
    body = _Body(b"hello")
    response = SimpleNamespace(status=HTTPStatus.OK, content_length=None, content=body)
    assert await _read_description(response, 5) == b"hello"
    assert body.limit == 6


@pytest.mark.asyncio
async def test_description_read_rejects_declared_or_actual_oversize():
    declared = SimpleNamespace(
        status=HTTPStatus.OK, content_length=10, content=_Body(b"hello")
    )
    with pytest.raises(UPnPInspectionError) as exc:
        await _read_description(declared, 5)
    assert exc.value.code == "RESPONSE_TOO_LARGE"

    actual = SimpleNamespace(
        status=HTTPStatus.OK, content_length=None, content=_Body(b"abcdef")
    )
    with pytest.raises(UPnPInspectionError) as exc:
        await _read_description(actual, 5)
    assert exc.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_description_read_rejects_non_200_without_consuming_body():
    body = _Body(b"error")
    response = SimpleNamespace(status=302, content_length=None, content=body)
    with pytest.raises(UPnPInspectionError, match="Unexpected HTTP status: 302"):
        await _read_description(response, 5)
    assert body.limit is None
