"""Public contract for structured inspection error metadata."""

from snf.inspection.error_codes import InspectionErrorCode


def test_error_code_exposes_stable_identifier_reason_and_description():
    error = InspectionErrorCode.CONNECTION_FAILED
    assert error.get_code() == "CONNECTION_FAILED"
    assert error.reason() == "Connection failed"
    assert "BLE" in error.description()
    assert error.value == (
        "CONNECTION_FAILED",
        "Connection failed",
        error.description(),
    )


def test_all_error_metadata_is_nonempty_and_identifiers_unique():
    codes = [item.get_code() for item in InspectionErrorCode]
    assert len(codes) == len(set(codes))
    for item in InspectionErrorCode:
        assert item.get_code()
        assert item.reason().strip()
        assert item.description().strip()
        assert isinstance(item.value, tuple)
