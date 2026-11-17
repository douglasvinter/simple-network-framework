# Bluetooth assigned-number enrichment

SNF resolves Bluetooth Assigned Numbers locally and retains raw advertisement fields.
The lookup tables are a vendored snapshot of
[Nordic Semiconductor's Bluetooth Numbers Database](https://github.com/nordicsemi/bluetooth-numbers-database/tree/master/v1),
which mirrors a subset of the [Bluetooth SIG Assigned Numbers](https://www.bluetooth.com/specifications/assigned-numbers/)
and also includes sourced vendor UUID definitions.

## Included registries

- `company_ids.json`: registered company identifiers, including Samsung (117),
  Apple (76), Garmin (135), and Fujitsu (746).
- `service_uuids.json`: standard and contributed service UUID descriptions.
- `characteristic_uuids.json`: GATT characteristic descriptions.
- `descriptor_uuids.json`: GATT descriptor descriptions.
- `gap_appearance.json`: appearance categories and subcategories.

No internet connection is required during scanning or inspection. The database
is bundled in the Python package. To refresh, retrieve the corresponding files
from the upstream `v1/` directory, review changes and run the tests.

## Discovery

BLE observations retain `manufacturer_data`, `service_uuids`, and `service_data`.
The BLE adapter additionally includes:

- `company_names`: manufacturer-data company ID -> registered company name.
- `service_names`: advertised UUID -> assigned service name.
- `service_data_names`: service-data UUID -> assigned service name.

Unknown IDs are omitted from the translated fields; original values remain intact.
The registered company identifies the manufacturer-data namespace, **not verified
product identity, ownership, or physical manufacturer**.

## GATT inspection

Explicit BLE inspection additionally resolves names for services,
characteristics and descriptors. The original UUIDs remain available. The
inspector still only enumerates GATT metadata; it does not read, write, pair
or interpret proprietary payloads.

## Limitations

- Bluetooth Classic Class of Device and raw BLE Appearance values are not
  exposed by the current portable Bleak advertisement contract; the
  `appearance_details` resolver can translate Appearance if an integer
  value is obtained elsewhere.
- The upstream Nordic dataset is a **subset** of all SIG assigned numbers;
  it is not a complete worldwide registry of proprietary product models.
- Vendor-specific advertisement decoding and device control belong in the
  consuming application, not SNF.
