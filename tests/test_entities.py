"""Evidence-based entity resolution tests."""

from snf.entities import EntityResolver
from snf.models import DiscoveryObservation, Endpoint, Service

UDN = "uuid:12345678-1234-1234-1234-123456789abc"


def test_ssdp_advertisements_group_by_udn_independent_of_order():
    first = DiscoveryObservation(
        "ssdp", "a", "TV", services=(Service("root"),),
        metadata={"usn": f"{UDN}::upnp:rootdevice"},
    )
    second = DiscoveryObservation(
        "ssdp", "b", "TV", services=(Service("transport"),),
        metadata={"usn": f"{UDN}::urn:schemas-upnp-org:service:AVTransport:1"},
    )
    resolver = EntityResolver()
    entities = resolver.resolve((first, second))
    assert entities == resolver.resolve((second, first))
    assert len(entities) == 1
    assert entities[0].id == f"ssdp:{UDN}"
    assert entities[0].identity_source == "ssdp_udn"
    assert len(entities[0].services) == 2
    assert len(entities[0].observations) == 2


def test_same_ip_name_does_not_imply_identity():
    endpoint = (Endpoint("ip", "192.0.2.10"),)
    records = [
        DiscoveryObservation(protocol, identifier, "TV", endpoints=endpoint)
        for protocol, identifier in (("ssdp", "a"), ("mdns", "b"), ("ble", "c"))
    ]
    assert len(EntityResolver().resolve(records)) == 3


def test_invalid_and_conflicting_udn_remain_separate():
    records = (
        DiscoveryObservation("ssdp", "a", "TV", metadata={"usn": "uuid:invalid"}),
        DiscoveryObservation("ssdp", "b", "TV", metadata={"usn": UDN}),
        DiscoveryObservation(
            "ssdp", "c", "TV",
            metadata={"usn": "uuid:12345678-1234-1234-1234-123456789abd"},
        ),
    )
    assert len(EntityResolver().resolve(records)) == 3


def test_missing_evidence_and_empty_snapshot():
    resolver = EntityResolver()
    assert resolver.resolve(()) == ()
    entities = resolver.resolve(
        (DiscoveryObservation("slp", "one", "Device"), DiscoveryObservation("slp", "two", "Device"))
    )
    assert len(entities) == 2
    assert all(entity.identity_source == "observation" for entity in entities)


def test_duplicate_service_preserved_once():
    service = Service("shared")
    records = (
        DiscoveryObservation("ssdp", "a", "TV", services=(service,), metadata={"usn": UDN}),
        DiscoveryObservation("ssdp", "b", "TV", services=(service,), metadata={"usn": UDN}),
    )
    assert EntityResolver().resolve(records)[0].services == (service,)
