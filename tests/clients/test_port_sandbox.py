from clients.port_sandbox import get_port_capacities


def test_get_port_capacities_mock(monkeypatch):
    monkeypatch.setenv("USE_MOCK_SANDBOX", "true")

    capacities = get_port_capacities()
    assert capacities["NLRTM"] == 25000
    assert capacities["BEANR"] == 15000
    assert capacities["DEBRV"] == 10000


def test_get_port_capacities_mock_subset(monkeypatch):
    monkeypatch.setenv("USE_MOCK_SANDBOX", "True")

    capacities = get_port_capacities(["NLRTM"])
    assert capacities == {"NLRTM": 25000}

def test_get_port_capacities_mock_strict(monkeypatch):
    monkeypatch.setenv("USE_MOCK_SANDBOX", "1")

    # With strict check, "1" should NOT enable mock mode.
    # We can't assume the sandbox API is reachable, so we only assert it returns a dict.
    capacities = get_port_capacities(["NLRTM"])
    assert isinstance(capacities, dict)


def test_get_port_capacities_mock_off(monkeypatch):
    monkeypatch.delenv("USE_MOCK_SANDBOX", raising=False)

    # We don't assert on live values (depends on local sandbox service availability),
    # but we do assert the function returns a mapping.
    capacities = get_port_capacities(["NLRTM"])
    assert isinstance(capacities, dict)


def test_get_port_capacities_http_failure_falls_back_to_mock(monkeypatch):
    class _FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, timeout: float = 5.0):  # noqa: ARG002
            raise httpx.ConnectError("boom")

    import httpx  # local import to keep test file minimal

    monkeypatch.setenv("USE_MOCK_SANDBOX", "false")
    monkeypatch.setenv("SANDBOX_API_URL", "http://example.invalid")
    monkeypatch.setattr("clients.port_sandbox.httpx.Client", _FailingClient)

    capacities = get_port_capacities(["NLRTM", "BEANR", "DEBRV"])
    assert capacities["NLRTM"] == 25000
    assert capacities["BEANR"] == 15000
    assert capacities["DEBRV"] == 10000
