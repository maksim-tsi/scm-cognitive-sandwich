import pytest

from core.env_guard import assert_no_localhost_services


def _set_required_env(monkeypatch, *, sandbox: str, phoenix: str) -> None:
    monkeypatch.setenv("SANDBOX_API_URL", sandbox)
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", phoenix)


def test_env_guard_rejects_localhost_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_LOCALHOST", raising=False)
    _set_required_env(
        monkeypatch,
        sandbox="http://localhost:8001",
        phoenix="http://localhost:6006/v1/traces",
    )

    with pytest.raises(RuntimeError, match="localhost endpoints are not allowed"):
        assert_no_localhost_services()


def test_env_guard_accepts_remote_endpoints(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_LOCALHOST", raising=False)
    _set_required_env(
        monkeypatch,
        sandbox="http://192.168.107.172:8001",
        phoenix="http://192.168.107.172:6006/v1/traces",
    )

    assert_no_localhost_services()


def test_env_guard_bypass_allows_localhost(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_LOCALHOST", "true")
    _set_required_env(
        monkeypatch,
        sandbox="http://localhost:8001",
        phoenix="http://localhost:6006/v1/traces",
    )

    assert_no_localhost_services()
