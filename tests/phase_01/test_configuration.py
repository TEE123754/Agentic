import json
from uuid import uuid4

import pytest

from frictionlab.configuration import ConfigurationRejected, read_json, resolve_run


def modify_environment(registry, change):
    path = registry / "environments" / "local_storefront.json"
    value = read_json(path)
    change(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_profiles_goals_and_reproducible_hash(payload):
    first = resolve_run(payload)
    second = resolve_run(payload)
    assert first.config.id != second.config.id
    assert first.configuration_hash == second.configuration_hash
    assert first.requested_sessions == 9
    assert {p.device.input_mode for p in first.personas} == {"mouse", "touch", "keyboard"}
    assert all(j.completion for j in first.journeys)
    payload["seed"] += 1
    assert resolve_run(payload).configuration_hash != first.configuration_hash


@pytest.mark.parametrize("value", [0, 6, True, "2"])
def test_invalid_repetition_limits_are_rejected(payload, value):
    payload["repetitions"] = value
    with pytest.raises(ConfigurationRejected, match="repetitions"):
        resolve_run(payload)


@pytest.mark.parametrize(
    "origin",
    [
        "https://production.example.invalid",
        "http://localhost:8765",
        "http://127.0.0.1:8766",
        "http://127.0.0.1:8765/private",
        "http://user:TOP_SECRET@127.0.0.1:8765",
        "http://127.0.0.1:8765#secret",
    ],
)
def test_unsafe_or_unowned_origin_rejected_offline(payload, registry, origin):
    modify_environment(registry, lambda e: e.update(replica_origins=[origin]))
    with pytest.raises(ConfigurationRejected) as caught:
        resolve_run(payload, registry)
    assert "TOP_SECRET" not in str(caught.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dependency_origins", ["https://production.example.invalid"]),
        ("integration_mocks", ["payment", "email", "sms", "webhook", "inventory"]),
        ("credential_reference", "literal-api-secret"),
        ("service_workers", "allowed"),
        ("cleanup_scope", "entire_database"),
        ("blocked_live_origins", ["http://127.0.0.1:8765"]),
    ],
)
def test_incomplete_or_unsafe_policy_rejected(payload, registry, field, value):
    modify_environment(registry, lambda e: e.update({field: value}))
    with pytest.raises(ConfigurationRejected):
        resolve_run(payload, registry)


@pytest.mark.parametrize(
    "field",
    [
        "separate_database",
        "disposable_data",
        "no_live_credentials",
        "external_integrations_mocked",
    ],
)
def test_isolation_attestations_all_required(payload, registry, field):
    modify_environment(registry, lambda e: e["isolation"].update({field: False}))
    with pytest.raises(ConfigurationRejected, match="isolation"):
        resolve_run(payload, registry)


def test_traffic_limits_fail_before_target_traffic(payload, registry):
    modify_environment(registry, lambda e: e["limits"].update(concurrency=3))
    with pytest.raises(ConfigurationRejected, match="concurrency"):
        resolve_run(payload, registry)


@pytest.mark.parametrize(
    "reference", ["unknown_profile", "../secret", "impatient_mobile/../../secret"]
)
def test_unknown_and_escaping_references_rejected(payload, reference):
    payload["personas"] = [reference]
    with pytest.raises(ConfigurationRejected):
        resolve_run(payload)


def test_duplicate_references_and_filename_mismatch(payload, registry):
    payload["personas"] *= 2
    with pytest.raises(ConfigurationRejected):
        resolve_run(payload, registry)
    payload["personas"] = ["impatient_mobile"]
    path = registry / "personas" / "impatient_mobile.json"
    document = read_json(path)
    document["id"] = "different_profile"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ConfigurationRejected, match="filename"):
        resolve_run(payload, registry)


def test_missing_malformed_and_oversized_config(tmp_path):
    path = tmp_path / "invalid.json"
    for text in (None, "{invalid", " " * (64 * 1024 + 1)):
        if text is not None:
            path.write_text(text, encoding="utf-8")
        with pytest.raises(ConfigurationRejected):
            read_json(path)


def test_run_id_does_not_change_configuration_hash(payload):
    first = resolve_run(payload)
    payload["id"] = str(uuid4())
    assert resolve_run(payload).configuration_hash == first.configuration_hash
