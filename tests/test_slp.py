from snf.adapters.slp import SLPPlugin


def test_parse_slp_service_url():
    device = SLPPlugin._to_device("service:myserv.x://myhost.example:4242/path,65535")
    assert device.protocol == "slp"
    assert device.identifier == "service:myserv.x://myhost.example:4242/path"
    assert device.services[0].service_type == "myserv.x"
    assert device.endpoints[0].address == "myhost.example"
    assert device.endpoints[0].port == 4242
    assert device.metadata["lifetime"] == "65535"


def test_parse_slp_url_with_nested_service_type():
    device = SLPPlugin._to_device("service:wbem:http://192.0.2.10:5988,65535")
    assert device.services[0].service_type == "wbem:http"
    assert device.endpoints[0].address == "192.0.2.10"
    assert device.endpoints[0].port == 5988
