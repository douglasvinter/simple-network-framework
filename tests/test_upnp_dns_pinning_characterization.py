"""Characterize DNS pinning constraints before extracting HTTP transport steps."""

import pytest

pytest.importorskip("aiohttp")

from snf.inspection.upnp import UPnPInspectionError, _validate_resolved_addresses


def test_dns_answers_are_normalized_and_restricted_to_private_lan():
    assert _validate_resolved_addresses({"192.168.1.10"}, None) == {"192.168.1.10"}
    assert _validate_resolved_addresses(
        {"192.168.1.10"}, frozenset({"192.168.1.10"})
    ) == {"192.168.1.10"}


@pytest.mark.parametrize("addresses", [set(), {"127.0.0.1"}, {"192.168.1.10", "8.8.8.8"}])
def test_dns_rejects_empty_loopback_and_mixed_public_answers(addresses):
    with pytest.raises(UPnPInspectionError, match="private LAN"):
        _validate_resolved_addresses(addresses, None)


def test_dns_rejects_source_address_mismatch_with_stable_code():
    with pytest.raises(UPnPInspectionError) as failure:
        _validate_resolved_addresses({"192.168.1.10"}, frozenset({"192.168.1.11"}))
    assert failure.value.code == "SOURCE_ADDRESS_MISMATCH"
