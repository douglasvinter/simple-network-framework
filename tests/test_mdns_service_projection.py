"""Characterize mDNS resolved-service projection without network I/O."""

from types import SimpleNamespace

from snf.adapters.mdns import _observation_from_service_info


def test_mdns_projection_preserves_endpoints_service_metadata_and_identity():
    info = SimpleNamespace(
        port=5353,
        server="host.local.",
        properties={b"flag": None, b"label": b"ok"},
        parsed_addresses=lambda: ["192.168.1.10", "fe80::1"],
    )
    observation = _observation_from_service_info(
        "_http._tcp.local.", "Printer._http._tcp.local.", info, info.parsed_addresses()
    )
    assert observation.identifier == "_http._tcp.local.|Printer._http._tcp.local."
    assert tuple(e.address for e in observation.endpoints) == ("192.168.1.10", "fe80::1")
    assert observation.services[0].endpoints == observation.endpoints
    assert observation.metadata["properties"] == {"flag": "", "label": "ok"}
    assert observation.services[0].metadata == observation.metadata
