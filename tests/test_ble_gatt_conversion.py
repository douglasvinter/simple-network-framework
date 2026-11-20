"""Characterize BLE GATT metadata conversion independently of device I/O."""

from types import SimpleNamespace

from snf.inspection.ble import _service_details


def test_service_details_preserves_characteristic_and_descriptor_order(monkeypatch):
    monkeypatch.setattr(
        "snf.inspection.ble._assigned_name", lambda uuid, kind: f"{kind}:{uuid}"
    )
    descriptors = [SimpleNamespace(uuid="2901"), SimpleNamespace(uuid="2902")]
    characteristic = SimpleNamespace(
        uuid="2a00", properties=["read", "notify"], descriptors=descriptors
    )
    service = SimpleNamespace(uuid="1800", characteristics=[characteristic])

    details = _service_details(service)

    assert details.uuid == "1800"
    assert details.name == "service:1800"
    assert len(details.characteristics) == 1
    assert details.characteristics[0].properties == ("read", "notify")
    assert details.characteristics[0].descriptors == ("2901", "2902")
    assert details.characteristics[0].descriptor_names == (
        "descriptor:2901", "descriptor:2902"
    )
