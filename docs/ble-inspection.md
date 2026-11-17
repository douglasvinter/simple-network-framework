# BLE inspection (opt-in)

BLE discovery remains advertisement-only. This feature adds an **explicit**
connection to an already discovered BLE peripheral to enumerate GATT service,
characteristic, and descriptor **metadata**.

## HTTP API

```http
GET /network/discoveries/inspect/ble?identifier=AA%3ABB%3ACC%3ADD%3AEE%3AFF
```

Use `observations[].identifier` from `GET /network/discoveries`, **not**
the prefixed entity ID. The runtime must have BLE discovery enabled and be
running; the observation must still be present.

A successful response contains `identifier`, `services`, and `error: {}`.
Each service includes its UUID and characteristics; each characteristic includes
its UUID, advertised properties, and descriptor UUIDs.

## Boundaries

- Inspection is on demand. It does **not** change discovery records or entities.
- It establishes a temporary BLE connection and disconnects on exit.
- It does **not** read characteristic values, subscribe, write, pair, or unpair.
- GATT enumeration is not guaranteed to work for all peripherals. Devices may
  refuse connections, be out of range, or require OS-level security.
- The framework cannot guarantee that the OS or device will not prompt for
  pairing; do not inspect devices without authorization.
- This is **Bluetooth Low Energy only**. Bluetooth Classic discovery and SDP
  inspection require a different platform-specific backend and are not
  implemented by Bleak.

Install BLE support with `pip install 'simple-network-framework[ble]'`.

Errors use the `device: null` and `error: {code, message, raw_response}`
envelope. Invalid or unsupported requests return 422, missing observations 404,
runtime unavailable 503, and connection failures 502.
