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

`GET /network/discoveries/inspect?identifier=<url-encoded SSDP USN>`

This is an **explicit network operation**, not a background enrichment job. Use an identifier returned by `GET /network/discoveries?protocol=ssdp`. Responses are structured UPnP device descriptions. Unknown identifiers return 404; failed inspections return 502; unavailable SSDP protocol returns 422; an unstarted runtime returns 503.

## Security and compatibility

Only plain HTTP device descriptions at private LAN addresses are supported. DNS answers are validated and pinned, redirects are rejected, and HTTP responses are bounded by timeout, byte size, concurrency, and embedded-device nesting limits. Vendor-specific responses that are not UPnP root XML return a controlled error. The parsed control URLs are **data only**; they are never fetched or invoked. This inspector is not a general-purpose URL fetcher.
