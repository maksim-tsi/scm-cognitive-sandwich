from clients.port_sandbox import get_port_capacities


def test_get_port_capacities_mock(monkeypatch):
    monkeypatch.setenv("USE_MOCK_SANDBOX", "true")

    capacities = get_port_capacities()
    assert capacities["NLRTM"] == 25000
    assert capacities["BEANR"] == 15000
    assert capacities["DEBRV"] == 10000


def test_get_port_capacities_mock_subset(monkeypatch):
    monkeypatch.setenv("USE_MOCK_SANDBOX", "1")

    capacities = get_port_capacities(["NLRTM"])
    assert capacities == {"NLRTM": 25000}


def test_get_port_capacities_mock_off(monkeypatch):
    monkeypatch.delenv("USE_MOCK_SANDBOX", raising=False)

    # We don't assert on live values (depends on local sandbox service availability),
    # but we do assert the function returns a mapping.
    capacities = get_port_capacities(["NLRTM"])
    assert isinstance(capacities, dict)
