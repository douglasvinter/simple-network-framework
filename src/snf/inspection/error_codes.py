"""Stable inspection identifiers with human-readable metadata."""

from enum import Enum


class InspectionErrorCode(Enum):
    """Each member stores (stable code, short reason, explanatory description)."""

    CONNECTION_FAILED = (
        "CONNECTION_FAILED",
        "Connection failed",
        "BLE GATT service enumeration failed while connecting to or communicating with the device.",
    )

    DEPENDENCY_UNAVAILABLE = (
        "DEPENDENCY_UNAVAILABLE",
        "Dependency unavailable",
        "The optional dependency required by this inspection protocol is not installed.",
    )

    FETCH_FAILED = (
        "FETCH_FAILED",
        "Fetch failed",
        "The UPnP device description could not be retrieved over HTTP.",
    )

    INSPECTION_FAILED = (
        "INSPECTION_FAILED",
        "Inspection failed",
        "The requested device or service inspection could not be completed.",
    )

    INVALID_IDENTIFIER = (
        "INVALID_IDENTIFIER",
        "Invalid identifier",
        "The inspection target identifier is missing or invalid.",
    )

    INVALID_OBSERVATION = (
        "INVALID_OBSERVATION",
        "Invalid observation",
        "The discovery observation does not contain the information required for inspection.",
    )

    MALFORMED_DESCRIPTION = (
        "MALFORMED_DESCRIPTION",
        "Malformed description",
        "The UPnP device description contains malformed XML.",
    )

    OBSERVATION_NOT_FOUND = (
        "OBSERVATION_NOT_FOUND",
        "Observation not found",
        "No live discovery observation matches the requested identifier.",
    )

    RESOLUTION_FAILED = (
        "RESOLUTION_FAILED",
        "Resolution failed",
        "The DNS-SD service instance could not be resolved.",
    )

    RESPONSE_TOO_LARGE = (
        "RESPONSE_TOO_LARGE",
        "Response too large",
        "The UPnP description exceeds the configured maximum response size.",
    )

    RUNTIME_UNAVAILABLE = (
        "RUNTIME_UNAVAILABLE",
        "Runtime unavailable",
        "The discovery runtime is not available to serve the inspection request.",
    )

    SERVICE_UNAVAILABLE = (
        "SERVICE_UNAVAILABLE",
        "Service unavailable",
        "The DNS-SD service instance did not resolve to an available service.",
    )

    SOURCE_ADDRESS_MISMATCH = (
        "SOURCE_ADDRESS_MISMATCH",
        "Source address mismatch",
        "The UPnP description address does not match the source address observed through SSDP.",
    )

    SOURCE_ADDRESS_UNAVAILABLE = (
        "SOURCE_ADDRESS_UNAVAILABLE",
        "Source address unavailable",
        "The SSDP observation has no eligible local source IP address.",
    )

    UNSUPPORTED_DESCRIPTION_FORMAT = (
        "UNSUPPORTED_DESCRIPTION_FORMAT",
        "Unsupported description format",
        "The endpoint did not provide a supported UPnP device description.",
    )

    UNSUPPORTED_PROTOCOL = (
        "UNSUPPORTED_PROTOCOL",
        "Unsupported protocol",
        "The requested observation or protocol is not supported for inspection.",
    )

    def get_code(self) -> str:
        """Return the stable machine-readable identifier."""
        return self.value[0]

    def reason(self) -> str:
        """Return a short, human-readable reason."""
        return self.value[1]

    def description(self) -> str:
        """Return a protocol-aware explanation of the error."""
        return self.value[2]
