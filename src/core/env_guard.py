from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse


LOCALHOST_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


@dataclass(frozen=True)
class EnvGuardConfig:
    required_keys: tuple[str, ...] = (
        "SANDBOX_API_URL",
        "YAAM_API_URL",
        "PHOENIX_COLLECTOR_ENDPOINT",
    )
    optional_keys: tuple[str, ...] = ("REDIS_URL",)
    allow_localhost_env_key: str = "ALLOW_LOCALHOST"


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _extract_hostname(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme and parsed.hostname:
        return parsed.hostname

    # Allow bare host:port values by treating them as http://host:port.
    if "://" not in value:
        parsed = urlparse(f"http://{value}")
        return parsed.hostname

    return None


def _iter_env_keys(config: EnvGuardConfig) -> Iterable[tuple[str, bool]]:
    for key in config.required_keys:
        yield key, True
    for key in config.optional_keys:
        yield key, False


def assert_no_localhost_services(config: EnvGuardConfig | None = None) -> None:
    """Fail fast if configured service endpoints resolve to localhost/loopback.

    This guard exists because the WinterSim environment does not use localhost; all
    external services run on remote nodes.

    Escape hatch:
        - Set ALLOW_LOCALHOST=true for local development/tests only.
    """
    resolved_config = config or EnvGuardConfig()
    if _is_truthy(os.getenv(resolved_config.allow_localhost_env_key)):
        return

    errors: list[str] = []
    for key, required in _iter_env_keys(resolved_config):
        raw_value = os.getenv(key)
        if raw_value is None or not raw_value.strip():
            if required:
                errors.append(f"{key} is required but was not set.")
            continue

        hostname = _extract_hostname(raw_value)
        if hostname is None:
            errors.append(f"{key} must be a URL or host:port value, got: {raw_value!r}.")
            continue

        if hostname.lower() in LOCALHOST_HOSTNAMES:
            errors.append(
                f"{key} must not point to localhost/loopback (got host={hostname!r}, value={raw_value!r})."
            )

    if errors:
        joined = "\n- " + "\n- ".join(errors)
        raise RuntimeError(
            "Environment guard failed: localhost endpoints are not allowed in this environment."
            f"{joined}\n\n"
            f"Set {resolved_config.allow_localhost_env_key}=true to bypass for local dev/testing only."
        )

