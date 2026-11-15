from types import SimpleNamespace

from snf.adapters.ble import BLEPlugin


def test_ble_advertisement_is_normalized_without_connecting():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Sensor")
    advertisement = SimpleNamespace(
        local_name="Room Sensor",
        rssi=-61,
        tx_power=4,
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={76: b"\x01\x02"},
        service_data={"180f": b"\x03"},
    )
    result = BLEPlugin._to_device(device, advertisement)

    assert result.protocol == "ble"
    assert result.identifier == "AA:BB:CC:DD:EE:FF"
    assert result.name == "Room Sensor"
    assert result.endpoints[0].transport == "ble"
    assert result.metadata["rssi"] == -61
    assert result.metadata["manufacturer_data"] == {"76": "0102"}
    assert result.services[0].service_type == "bluetooth-le-advertised-service"
