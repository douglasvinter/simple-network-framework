"""Characterize stable string-valued inspection error codes."""

from snf.inspection.error_codes import InspectionErrorCode


def test_error_codes_preserve_public_string_values():
    assert InspectionErrorCode.INVALID_IDENTIFIER == "INVALID_IDENTIFIER"
    assert InspectionErrorCode.UNSUPPORTED_PROTOCOL == "UNSUPPORTED_PROTOCOL"
    assert InspectionErrorCode.INVALID_OBSERVATION == "INVALID_OBSERVATION"
    assert InspectionErrorCode.SOURCE_ADDRESS_MISMATCH == "SOURCE_ADDRESS_MISMATCH"
    assert InspectionErrorCode.CONNECTION_FAILED == "CONNECTION_FAILED"
