from snf.adapters.slp import SLPPlugin


def test_parse_slp_service_url():
    service = SLPPlugin._to_service("service:myserv.x://myhost.example:4242/path,65535")
    assert service is not None
    assert service.protocol == "slp"
    assert service.service_type == "myserv.x"
    assert service.address == "myhost.example"
    assert service.port == 4242
    assert service.metadata["lifetime"] == "65535"


def test_parse_slp_url_with_nested_service_type():
    service = SLPPlugin._to_service("service:wbem:http://192.0.2.10:5988,65535")
    assert service is not None
    assert service.service_type == "wbem:http"
    assert service.address == "192.0.2.10"
    assert service.port == 5988
