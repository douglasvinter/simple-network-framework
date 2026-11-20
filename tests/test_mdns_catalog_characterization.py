"""Preserve the published mDNS default service catalog and alias contract."""

from snf.adapters.mdns import ALL_MDSNS_SERVICE_TYPES, DEFAULT_SERVICE_TYPES


def test_mdns_catalog_is_loaded_as_mutable_list_and_alias_is_identical():
    assert isinstance(DEFAULT_SERVICE_TYPES, list)
    assert ALL_MDSNS_SERVICE_TYPES is DEFAULT_SERVICE_TYPES
    assert DEFAULT_SERVICE_TYPES[0] == "_airplay._tcp.local."
    assert DEFAULT_SERVICE_TYPES[-1] == "_occam._udp.local."
    assert len(DEFAULT_SERVICE_TYPES) == 37
