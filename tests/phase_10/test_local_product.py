"""One phase-boundary batch: real adapters against mocked free-service responses."""

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from frictionlab.cohorts.coordinator import CohortCoordinator, CohortSettings
from frictionlab.configuration import CONFIG_DIRECTORY, read_json, resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.evaluation.comparison import _inference_identities, compare_runs
from frictionlab.planning.cloud_model import CloudModelRuntime
from frictionlab.planning.contracts import PlannerStopped
from frictionlab.planning.inference import InferenceSettings, load_inference, safe_text
from frictionlab.planning.runner import run_persona
from frictionlab.product import doctor, initialize
from frictionlab.sharing.bundle import export_bundle

KEY = "gsk_SYNTHETIC_ACCEPTANCE_ONLY_123456789"


def settings(provider="groq", **overrides):
    return InferenceSettings(
        provider=provider,
        model="fixture-model",
        allow_remote=True,
        share_sanitized_state=True,
        free_tier_confirmed=True,
        **overrides,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("allow_remote", False),
        ("share_sanitized_state", False),
        ("free_tier_confirmed", False),
        ("paid_fallback", True),
        ("max_retries", 3),
        ("api_key", KEY),
        ("endpoint", "https://attacker.invalid"),
        ("fallback", "paid"),
    ],
)
def test_remote_policy_rejects_implicit_access(field, value):
    payload = settings().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        InferenceSettings.model_validate(payload)


def test_init_and_doctor_no_network(tmp_path, monkeypatch):
    home = tmp_path / "workspace"
    result = initialize(home)
    assert not result["downloads"] and (home / "site/index.html").is_file()
    with pytest.raises(ValueError):
        initialize(home)
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    path = home / "frictionlab.local.json"
    path.write_text(settings().model_dump_json())
    with patch("httpx.Client", side_effect=AssertionError("No network in doctor")):
        result = doctor(path)
    assert result["network_requests"] == 0 and not result["models_started"]
    assert KEY not in json.dumps(result)
    assert (
        safe_text(f"password=hidden {KEY} alice@example.com https://private.invalid/?key=hidden")
        == "[redacted credential] [redacted credential] [redacted email] [redacted URL]"
    )
    path.write_text('{"provider":"groq","api_key":"' + KEY + '"}')
    with pytest.raises(PlannerStopped) as rejected:
        load_inference(path)
    assert KEY not in str(rejected.value)


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_transport_endpoint_key_and_budgets(provider, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY" if provider == "groq" else "GEMINI_API_KEY", KEY)
    requests = []

    def respond(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.url.host == (
            "api.groq.com" if provider == "groq" else "generativelanguage.googleapis.com"
        )
        assert KEY not in request.content.decode()
        return httpx.Response(200, json={"model": "fixture-model", "usage": {"total_tokens": 12}})

    async def run():
        runtime = CloudModelRuntime(
            settings(provider, max_requests=1), transport=httpx.MockTransport(respond)
        )
        await runtime.__aenter__()
        try:
            runtime.complete([{"role": "user", "content": "hello"}], 96, time.monotonic() + 10)
            with pytest.raises(PlannerStopped, match="budget"):
                runtime.complete([{"role": "user", "content": "hello"}], 96, time.monotonic() + 10)
            assert runtime.provenance()["quota_paused"]
        finally:
            await runtime.close()

    asyncio.run(run())
    assert len(requests) == 1


@pytest.mark.parametrize(
    "fault,category",
    [
        (429, "cloud_budget_paused"),
        (401, "model_provider_error"),
        (503, "model_provider_error"),
        (302, "model_provider_error"),
        ("timeout", "model_timeout"),
        ("oversize", "invalid_model_output"),
        ("usage", "cloud_budget_paused"),
    ],
)
def test_provider_faults_stop_without_dispatch(fault, category, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)

    def respond(request):
        if fault == "timeout":
            raise httpx.ReadTimeout("Fake key " + KEY, request=request)
        if fault == "oversize":
            return httpx.Response(200, content=b"x" * 256001)
        if fault == "usage":
            return httpx.Response(
                200, json={"model": "fixture-model", "usage": {"total_tokens": 999999}}
            )
        return httpx.Response(
            fault, headers={"Location": "https://attacker.invalid"}, json={"error": KEY}
        )

    async def run():
        runtime = CloudModelRuntime(settings(), transport=httpx.MockTransport(respond))
        await runtime.__aenter__()
        try:
            with pytest.raises(PlannerStopped) as stopped:
                runtime.complete(
                    [{"role": "user", "content": "fixture"}], 96, time.monotonic() + 10
                )
            assert stopped.value.category == category and KEY not in str(stopped.value)
        finally:
            await runtime.close()

    asyncio.run(run())


def test_runtime_input_time_and_retry_limits(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)

    async def run():
        requests = []

        def retry(request):
            requests.append(request)
            return httpx.Response(503)

        runtime = CloudModelRuntime(settings(max_retries=1), transport=httpx.MockTransport(retry))
        await runtime.__aenter__()
        try:
            with pytest.raises(PlannerStopped):
                runtime.complete(
                    [{"role": "user", "content": "x" * 25000}], 96, time.monotonic() + 10
                )
            with pytest.raises(PlannerStopped):
                runtime.complete([], 96, time.monotonic() - 1)
            assert not requests
            with pytest.raises(PlannerStopped):
                runtime.complete([], 96, time.monotonic() + 10)
            assert len(requests) == 2 and runtime.retries == 1 and runtime.budget.requests == 2
        finally:
            await runtime.close()

    asyncio.run(run())


def _decision_response(request):
    payload = json.loads(request.content)
    state = json.loads(
        next(item["content"] for item in payload["messages"] if item["role"] == "user")
    )
    controls = state["candidates"]
    fields = {"observation_id": state["observation_id"]}

    def named(name):
        return next((c for c in controls if c["name"] == name), None)

    textbox = next((c for c in controls if c["role"] == "textbox"), None)
    typed = any(a["kind"] == "type_text" for a in state["recent_actions"])
    if state["milestones"] and all(state["milestones"].values()):
        fields.update(kind="finish")
    elif textbox and not typed:
        fields.update(
            kind="type_text", candidate_id=textbox["id"], text_reference="synthetic_email"
        )
    elif button := named("Continue to order review") or named("Start checkout"):
        fields.update(kind="click", candidate_id=button["id"])
    else:
        fields.update(kind="scroll", direction="down", amount=400)
    return httpx.Response(
        200,
        json={
            "model": "fixture-model",
            "usage": {"total_tokens": 256},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {"action": fields, "rationale": "Observed synthetic control " + KEY}
                        )
                    },
                }
            ],
        },
    )


def test_byok_cohorts_reports_comparability_and_secret_exclusion(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", KEY)
    root = Path(os.environ.get("FRICTIONLAB_PHASE10_EVIDENCE", tmp_path)) / str(uuid4())
    root = root.resolve()

    async def run():
        payload = read_json(CONFIG_DIRECTORY / "run.quickstart.json")
        ids = []
        factory = lambda config: CloudModelRuntime(
            config, transport=httpx.MockTransport(_decision_response)
        )
        with (
            patch("frictionlab.cohorts.coordinator.load_inference", return_value=settings()),
            patch("frictionlab.cohorts.coordinator.CloudModelRuntime", side_effect=factory),
        ):
            coordinator = CohortCoordinator(root, settings=CohortSettings(workers=1))
            try:
                for variant in ("dead_button", "healthy"):
                    payload["id"] = str(uuid4())
                    ids.append(payload["id"])
                    await coordinator.submit(resolve_run(payload), variant=variant)
                    await coordinator.wait(payload["id"])
                comparison = compare_runs(root, coordinator.store, *ids)
                assert comparison["matched"] and comparison["completion_delta"] == 1
            finally:
                await coordinator.close()
        report = RunReport.model_validate_json(
            (root / "reports" / ids[0] / "revisions/2/report.json").read_text()
        )
        assert (
            report.findings
            and report.protection.sentinel_requests == 0
            and report.protection.sentinel_data_unchanged
        )
        export_bundle(root, ids[0], root / "portable")
        healthy = RunReport.model_validate_json(
            (root / "reports" / ids[1] / "revisions/2/report.json").read_text()
        )
        path = (root / healthy.session_summaries[0].report_path).with_name("report.json")
        session = json.loads(path.read_text())
        provenance = json.loads(session["scope"]["runtime_metadata"]["inference"])
        assert provenance["actual_models"] == ["fixture-model"] and provenance["provider"] == "groq"
        original = path.read_bytes()
        provenance["actual_models"] = ["one", "two"]
        provenance["strict_comparable"] = False
        session["scope"]["runtime_metadata"]["inference"] = json.dumps(provenance)
        path.write_text(json.dumps(session))
        with pytest.raises(ValueError, match="Mixed"):
            _inference_identities(root, healthy)
        path.write_bytes(original)
        # Quota failure is an agent infrastructure outcome, not abandonment.
        runtime = CloudModelRuntime(
            settings(), transport=httpx.MockTransport(lambda _: httpx.Response(429))
        )
        await runtime.__aenter__()
        try:
            failed = await run_persona(
                resolve_run(payload), runtime=runtime, behavioral=True, artifact_root=root / "fault"
            )
            assert failed.report.abandonment_diagnosis is None
            assert "inconclusive_agent_failure" in failed.report.cohort_results.outcome_counts
        finally:
            await runtime.close()
        monkeypatch.delenv("GROQ_API_KEY")
        missing = await run_persona(
            resolve_run(payload), inference=settings(), artifact_root=root / "missing-key"
        )
        assert not missing.started_navigation and missing.report.abandonment_diagnosis is None
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".html"}:
                assert KEY not in path.read_text(encoding="utf-8")
        (root / "phase10-review.json").write_text(
            json.dumps(
                {
                    "runs": ids,
                    "findings": len(report.findings),
                    "sentinel_requests": report.protection.sentinel_requests,
                    "comparison": comparison,
                    "mocked_providers_only": True,
                    "key_absent_from_text_evidence": True,
                },
                indent=2,
            )
        )

    asyncio.run(run())
