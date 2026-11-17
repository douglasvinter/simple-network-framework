# Read-only UPnP inspection (PR #10)

Discovery and inspection are deliberately independent. SSDP discovery publishes protocol-scoped observations with a `metadata["location"]` value. The inspector makes a bounded HTTP GET of that device-description URL and parses device/embedded-device details and advertised service URLs. It does **not** invoke SOAP actions, pair devices, or fetch service control documents.

## Python API

```python
from snf.inspection import UPnPInspector

# observation is an existing SSDP DiscoveryObservation from runtime.snapshot(protocol="ssdp")
inspector = UPnPInspector(timeout=3.0, max_bytes=262144)
device = await inspector.inspect_observation(observation)
print(device.friendly_name, device.udn, device.services)
```

To inspect multiple SSDP advertisements, `inspect_observations(observations)` returns a mapping keyed by unique LOCATION URL; each distinct LOCATION is fetched once per call. A failed fetch raises `UPnPInspectionError` and does not change the discovery registry. No persistent cache is maintained.

## HTTP API

`GET /network/discoveries/inspect/upnp?identifier=<url-encoded SSDP USN>`

This is an **explicit network operation**, not a background enrichment job. Use an identifier returned by `GET /network/discoveries?protocol=ssdp`. Responses are structured UPnP device descriptions with an `error` key. Unknown identifiers return 404; unsupported or malformed descriptions return 422; upstream fetch failures return 502; unavailable SSDP protocol returns 422; an unstarted runtime returns 503.

## Security and compatibility

Only plain HTTP device descriptions at private LAN addresses are supported. DNS answers are validated and pinned, redirects are rejected, and HTTP responses are bounded by timeout, byte size, concurrency, and embedded-device nesting limits. Vendor-specific responses that are not UPnP root XML return a controlled error. The parsed control URLs are **data only**; they are never fetched or invoked. This inspector is not a general-purpose URL fetcher.

## Inspection response contract

Successful inspection retains the existing UPnP device fields, including UDN,
device type, friendly name, manufacturer, model, services with SCPD/control/event
URLs, and recursive embedded devices, plus `error: {}`. Failures return HTTP 422 for unsupported/malformed descriptions or 502 for upstream failures, with an `error`
object containing `code`, `message`, and `raw_response`. The raw response
is bounded by `max_bytes` and is included for unsupported or malformed
descriptions (e.g. Netflix MDX returning `status=ok`).

Observation-based inspection requires the resolved LOCATION IP to match the
originating SSDP observation IP; ports may differ. All DNS answers must match,
and the vetted addresses remain pinned for HTTP. Direct `inspect(location)`
retains private-address restrictions but has no originating SSDP source to
compare. Failed inspections do not change discovery state.

On failed inspection the response also contains a `device` object with the
same fields as a successful description, populated conservatively from the
original SSDP advertisement. `udn` comes from the advertised UUID/USN,
`device_type` only from an advertised device-type URN, and `friendly_name`
only from an explicit friendly-name header. The SSDP `SERVER` header is
**not** a friendly name; missing fields remain null, and services/embedded
devices are empty because no UPnP description was parsed. The fallback
represents the advertisement, not a verified physical-device identity.

The successful HTTP 200 payload retains UPnP device fields at the top level
and always includes `"error": {}`. Failed inspections retain the `device`
fallback wrapper and a nonempty `error` object. An endpoint that returns
plain-text `status=ok` rather than a UPnP XML description returns HTTP 422.

All application-level outcomes from the inspection endpoint use the same
error envelope. A missing/blank identifier returns HTTP 422 with
`INVALID_IDENTIFIER`; unavailable SSDP support returns HTTP 422 with
`UNSUPPORTED_PROTOCOL`; an unknown observation returns HTTP 404 with
`OBSERVATION_NOT_FOUND`; and an unstarted runtime returns HTTP 503 with
`RUNTIME_UNAVAILABLE`. When no observation is available, `device` is
`null` rather than fabricated. These endpoint-specific failures do not
use FastAPI's `detail` key. Other SNF routes are unaffected.

## Refactoring boundaries

The SSDP fallback identity parser is now `snf.inspection.ssdp_metadata.SSDPMetadataParser`,
returning immutable `AdvertisedDeviceMetadata`. It is independent of FastAPI and
never equates protocol advertisements to physical devices. Stateless XML helpers
are available from `snf.inspection.xml` for reuse by XML-based inspectors.
Named inspection limits live in `snf.inspection.constants`. UPnP service
parsing is separated from recursive device parsing. No additional runtime
dependencies were introduced.
