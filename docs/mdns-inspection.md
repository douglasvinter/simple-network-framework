# mDNS/DNS-SD inspection

Inspection is opt-in, read-only, and scoped to one previously discovered mDNS
service observation. It does not trigger discovery, modify runtime observations,
or correlate service instances into physical devices.

```python
from snf.inspection.mdns import MDNSInspector

details = await MDNSInspector().inspect_observation(observation)
print(details.instance_name, details.server, details.port)
print(details.addresses, details.properties)
```

Install the `mdns` extra to enable on-demand DNS-SD resolution. The inspector
creates and closes its own zeroconf client, requests current service information
with a bounded timeout, and returns immutable structured service details.
TXT keys and values are decoded with UTF-8 replacement for invalid byte sequences;
this is a presentation representation, not lossless binary preservation.

A service instance is not a physical-device identifier. The inspector does not
infer manufacturer, model, or cross-protocol identity from TXT attributes.

## HTTP API

`GET /network/discoveries/inspect/mdns?identifier=<observation-identifier>`

Success returns the resolved service instance fields and `"error": {}`.
Application-level errors return `{"service": null, "error": {"code": "...",
"message": "...", "raw_response": null}}`. Missing identifiers and invalid
observations return 422, unknown identifiers return 404, unavailable runtime
returns 503, and resolution failures return 502. The existing SSDP inspection
endpoint remains unchanged.
