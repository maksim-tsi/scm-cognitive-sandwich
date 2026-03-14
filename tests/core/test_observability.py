from core.observability import (
    LEGACY_PROJECT_NAME_ATTRIBUTE,
    OPENINFERENCE_PROJECT_NAME_ATTRIBUTE,
    SERVICE_NAME_ATTRIBUTE,
    _build_resource_attributes,
    _parse_resource_attributes,
    _resolve_project_name,
)


def test_parse_resource_attributes_parses_key_values() -> None:
    parsed = _parse_resource_attributes(
        "project.name=my-project, service.name=my-service,invalid_pair,other=value"
    )

    assert parsed == {
        "project.name": "my-project",
        "service.name": "my-service",
        "other": "value",
    }


def test_resolve_project_name_precedence() -> None:
    assert (
        _resolve_project_name(
            raw_resource_attributes=(
                "openinference.project.name=oi-project,project.name=legacy-project"
            ),
            phoenix_project_name="phoenix-project",
        )
        == "oi-project"
    )
    assert (
        _resolve_project_name(
            raw_resource_attributes="project.name=legacy-project",
            phoenix_project_name="phoenix-project",
        )
        == "legacy-project"
    )
    assert (
        _resolve_project_name(
            raw_resource_attributes="",
            phoenix_project_name="phoenix-project",
        )
        == "phoenix-project"
    )


def test_build_resource_attributes_maps_legacy_project_name(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    resource_attributes = _build_resource_attributes(
        project_name="phoenix-project",
        raw_resource_attributes="project.name=legacy-project",
    )

    assert resource_attributes[LEGACY_PROJECT_NAME_ATTRIBUTE] == "legacy-project"
    assert resource_attributes[OPENINFERENCE_PROJECT_NAME_ATTRIBUTE] == "legacy-project"
    assert resource_attributes[SERVICE_NAME_ATTRIBUTE] == "phoenix-project"


def test_build_resource_attributes_respects_explicit_openinference_and_service_name(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "service-from-env")

    resource_attributes = _build_resource_attributes(
        project_name="phoenix-project",
        raw_resource_attributes=(
            "openinference.project.name=oi-project,project.name=legacy-project"
        ),
    )

    assert resource_attributes[OPENINFERENCE_PROJECT_NAME_ATTRIBUTE] == "oi-project"
    assert resource_attributes[SERVICE_NAME_ATTRIBUTE] == "service-from-env"

    # Ensure legacy key can exist without overriding OpenInference project key.
    assert resource_attributes[LEGACY_PROJECT_NAME_ATTRIBUTE] == "legacy-project"

    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)


def test_build_resource_attributes_adds_openinference_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    resource_attributes = _build_resource_attributes(
        project_name="phoenix-project",
        raw_resource_attributes="service.name=already-set",
    )

    assert resource_attributes[OPENINFERENCE_PROJECT_NAME_ATTRIBUTE] == "phoenix-project"
    assert resource_attributes[SERVICE_NAME_ATTRIBUTE] == "already-set"
