# Native inspection

SNF supports explicit inspection of an observation through the Python runtime.
The HTTP API is optional and delegates to the same capability.

```python
from snf import NetworkRuntime

async with NetworkRuntime() as runtime:
    observations = runtime.snapshot(protocol="ble")
    if observations:
        observation = runtime.get("ble", observations[0].identifier)
        details = await runtime.inspect("ble", observation.identifier)
        print(details)
```

## Contract

- `runtime.get(protocol, identifier)` returns a live observation or `None`. It does not perform network I/O.
- `await runtime.inspect(protocol, identifier)` resolves an existing live observation and performs **explicit network I/O** using the corresponding protocol inspector.
- `ssdp` returns `UPnPDevice`, `mdns` returns `MDNSServiceDetails`, and `ble` returns `BLEDeviceDetails`. There is no universal inspected-device model.
- Empty identifiers and missing observations raise `InspectionLookupError` with `INVALID_IDENTIFIER` and `OBSERVATION_NOT_FOUND`, respectively. Protocol-specific inspection errors retain their existing error types and codes.
- Inspection does not update discovery observations, persist results, or automatically retry failed requests.
- Inspection may connect to a peripheral or perform network requests. SNF does **not** guarantee that concurrent inspections of the same target are supported. Consumers such as SHA must coordinate or lock inspection requests when appropriate for their devices and protocols.

## Scope

The registry continues to hold protocol-scoped observations, not verified physical-device identities. Inventory ownership and durable persistence belong to consuming applications. The existing HTTP inspection endpoints remain available as diagnostic interfaces.
