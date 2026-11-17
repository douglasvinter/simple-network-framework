"""Protocol-specific metadata parsing must not depend on FastAPI."""

from snf.inspection.ssdp_metadata import AdvertisedDeviceMetadata, SSDPMetadataParser
from snf.models import DiscoveryObservation, Service


def test_ssdp_identity_evidence():
    observation = DiscoveryObservation(
        "ssdp", "ad", "Linux/1.0",
        metadata={"usn": "uuid:device::urn:schemas-upnp-org:device:MediaRenderer:1"},
        services=(Service(
            "renderer", service_type="urn:schemas-upnp-org:device:MediaRenderer:1",
            metadata={"friendlyName": "Living Room TV"},
        ),),
    )
    assert SSDPMetadataParser().parse(observation) == AdvertisedDeviceMetadata(
        "uuid:device", "urn:schemas-upnp-org:device:MediaRenderer:1", "Living Room TV"
    )


def test_ssdp_server_and_service_type_not_misidentified():
    observation = DiscoveryObservation(
        "ssdp", "uuid:device", "Samsung/1.0",
        services=(Service("service", service_type="urn:schemas-upnp-org:service:AVTransport:1"),),
    )
    assert SSDPMetadataParser().parse(observation) == AdvertisedDeviceMetadata(udn="uuid:device")


def test_identifier_fallback_preserves_nonstandard_vendor_uuid():
    identifier = "uuid:SSTVKSF1==0000000000000005297130"
    observation = DiscoveryObservation("ssdp", identifier, "Netflix MDX")
    assert SSDPMetadataParser().parse(observation).udn == identifier


def test_identifier_fallback_strips_usn_suffix():
    observation = DiscoveryObservation(
        "ssdp", "uuid:device::upnp:rootdevice", "Device"
    )
    assert SSDPMetadataParser().parse(observation).udn == "uuid:device"


def test_explicit_udn_takes_precedence_over_identifier():
    observation = DiscoveryObservation(
        "ssdp", "uuid:identifier", "Device",
        metadata={"udn": "uuid:advertised"},
    )
    assert SSDPMetadataParser().parse(observation).udn == "uuid:advertised"
