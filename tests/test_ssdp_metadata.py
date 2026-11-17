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
    assert SSDPMetadataParser().parse(observation) == AdvertisedDeviceMetadata()
