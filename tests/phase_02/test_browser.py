import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from frictionlab.browser.broker import ActionRejected, BrowserBroker
from frictionlab.browser.demo import demo
from frictionlab.configuration import ROOT
from frictionlab.contracts.models import Action, Viewport

ARTIFACTS = ROOT / "artifacts" / "phase2" / "runs"


def candidate(broker, name):
    return next(c for c in broker.current.candidates if c.name == name)


async def click(broker, name):
    selected = candidate(broker, name)
    return await broker.act(
        Action(kind="click", observation_id=broker.current.id, candidate_id=selected.candidate_id)
    )


async def press(broker, key):
    return await broker.act(Action(kind="press_key", observation_id=broker.current.id, key=key))


async def fill(broker, reference="synthetic_email"):
    selected = next(c for c in broker.current.candidates if c.role == "textbox")
    return await broker.act(
        Action(
            kind="type_text",
            observation_id=broker.current.id,
            candidate_id=selected.candidate_id,
            text_reference=reference,
        )
    )


def reviewed_cleanup(broker):
    assert broker.closed and not broker.cleanup_errors
    assert (
        broker.runtime.task is None
        and broker.runtime.proxy is None
        and broker.runtime.sentinel is None
    )
    assert not Path(broker.profile.name).exists()
    assert broker.runtime.sentinel_state == {"requests": [], "balance": 100}
    assert all(broker.boundary_checks.values())
    assert broker.report.protection.network_boundary_validated
    assert broker.report.protection.boundary_scope == "owned_fixture_browser_proxy"
    state = broker.runtime.app.state.fixture.snapshot(broker.run_id)
    assert (
        state["account_count"] == state["checkout_attempt_count"] == 0 and not state["mock_events"]
    )
    assert (broker.directory / "report.json").is_file()
    assert (broker.directory / "report.md").is_file()
    html = (broker.directory / "report.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html and "<script" not in html
    assert len(broker.report.visual_evidence) >= 2
    limits = broker.resolved.environment.limits
    assert broker.runtime.policy.metrics()["peak_requests_per_second"] <= limits.requests_per_second
    assert broker.runtime.peak_active_requests <= limits.concurrency
    arrivals = [request["at"] for request in broker.runtime.arrivals]
    assert (
        max(sum(0 <= other - stamp < 0.95 for other in arrivals) for stamp in arrivals)
        <= limits.requests_per_second
    )
    assert not broker.report.findings and not broker.report.abandonment_explanations


def test_healthy_form_evidence_grounding_axe_and_cleanup(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            original = broker.current
            assert original.target_id == broker.target_id
            assert not hasattr(broker.session, "event_bus")
            selected = candidate(broker, "Start checkout")
            px, py = original.coordinates.css_to_pixel(
                selected.bounds[0] + selected.bounds[2] / 2,
                selected.bounds[1] + selected.bounds[3] / 2,
            )
            assert broker.candidate_at_pixel(px, py, original.id) == selected.candidate_id
            assert (await click(broker, "Start checkout")).result == "progress"
            assert (await fill(broker)).result == "progress"
            assert (await click(broker, "Continue to order review")).result == "progress"
            assert all((await broker.verify_completion()).values())
            signal = await broker.accessibility()
            assert signal["version"] == "4.13.0" and "violations" in signal
            await broker.act(Action(kind="finish", observation_id=broker.current.id))
        reviewed_cleanup(broker)
        assert broker.report.cohort_results.outcome_counts == {"completed": 1}
        for ref in broker.observations[-1].evidence:
            assert (broker.directory / ref.path).is_file()
        text = "".join(
            path.read_text(encoding="utf-8")
            for path in (broker.directory / "evidence").glob("*.aria.txt")
        )
        assert next(iter(broker.text_values.values())) not in text
        assert (
            "<script"
            not in json.loads(next((broker.directory / "evidence").glob("*.dom.json")).read_text())[
                "sanitized_dom"
            ]
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "variant", ["generic_validation", "dead_button", "delayed_feedback", "hidden_shipping"]
)
def test_controlled_defects_produce_observed_results_not_invented_churn(resolved, variant):
    async def scenario():
        async with BrowserBroker(
            resolved, variant=variant, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            if variant == "hidden_shipping":
                assert "Total including shipping" not in broker.current.semantic_text
            result = await click(broker, "Start checkout")
            if variant == "dead_button":
                assert result.result == "no_change"
                assert not any((await broker.verify_completion()).values())
            else:
                if variant == "generic_validation":
                    assert (
                        await click(broker, "Continue to order review")
                    ).result == "validation_error"
                    assert "Invalid input" in broker.current.validation
                    await fill(broker)
                start = time.monotonic()
                result = await click(broker, "Continue to order review")
                assert result.result == "progress" and all(
                    (await broker.verify_completion()).values()
                )
                if variant == "delayed_feedback":
                    assert time.monotonic() - start >= 2.5
                if variant == "hidden_shipping":
                    assert "shipping $5" in broker.current.semantic_text
        reviewed_cleanup(broker)

    asyncio.run(scenario())


def test_keyboard_only_navigation_and_focus_trap(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved,
            variant="focus_trap",
            persona_id="keyboard_low_vision",
            journey_id="delivery_information",
            artifact_root=ARTIFACTS,
        ) as broker:
            selected = (
                broker.current.candidates[0].candidate_id if broker.current.candidates else 999
            )
            blocked = await broker.act(
                Action(kind="click", observation_id=broker.current.id, candidate_id=selected)
            )
            assert blocked.result == "blocked"
            for _ in range(12):
                if broker.current.focus["id"] == "delivery":
                    break
                await press(broker, "Tab")
            assert broker.current.focus["id"] == "delivery"
            assert (await press(broker, "Enter")).result == "progress"
            assert broker.current.focus["id"] == "delivery-dialog"
            trapped = broker.current.focus
            await press(broker, "Tab")
            assert broker.current.focus == trapped
            await press(broker, "Escape")
            assert await broker.page.get_by_role("dialog").is_visible()
            assert broker.current.coordinates.css_width < broker.viewport.width
        reviewed_cleanup(broker)

    asyncio.run(scenario())


def test_stale_candidate_replacement_resize_and_target_identity(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            original = broker.current
            selected = candidate(broker, "Start checkout")
            node = broker.registry[selected.candidate_id]
            # Replace with an identical-looking node: an HTML hash alone would not detect identity loss.
            await broker.page.get_by_role("button", name="Start checkout", exact=True).evaluate(
                "el => el.replaceWith(el.cloneNode(true))"
            )
            result = await broker.act(
                Action(kind="click", observation_id=original.id, candidate_id=selected.candidate_id)
            )
            assert result.result == "blocked"
            assert not await broker.page.get_by_role(
                "heading", name="Checkout details"
            ).is_visible()
            with pytest.raises(ActionRejected):
                broker.candidate_at_pixel(1, 1, original.id)
            broker.registry = {selected.candidate_id: node}
            with pytest.raises(ActionRejected, match="identity"):
                await broker.verify_candidate(selected.candidate_id)
            await broker.observe()
            prior = broker.current
            resized = await broker.resize(Viewport(width=1000, height=800))
            assert resized.id != prior.id and resized.viewport.width == 1000
            assert (
                await broker.act(Action(kind="wait", observation_id=prior.id, timeout_ms=1))
            ).result == "blocked"
            assert (
                await broker.act(
                    Action(
                        kind="scroll",
                        observation_id=broker.current.id,
                        direction="down",
                        amount=100,
                    )
                )
            ).result in {"no_change", "progress"}
        reviewed_cleanup(broker)

    asyncio.run(scenario())


def test_popup_unknown_operations_and_emergency_stop(resolved):
    async def scenario():
        async with BrowserBroker(
            resolved, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            async with httpx.AsyncClient(
                proxy=broker.runtime.proxy.origin, trust_env=False
            ) as client:
                result = await client.post(
                    f"{broker.runtime.origin}/fixture/runs/{broker.run_id}/checkout",
                    json={"email": "real@company.example"},
                )
                assert result.status_code == 403
                result = await client.post(
                    f"{broker.runtime.origin}/fixture/runs/{broker.run_id}/order", json={}
                )
                assert result.status_code == 403
            await broker.page.evaluate("window.open('about:blank')")
            await asyncio.sleep(0.2)
            assert len(broker.context.pages) == 1
            assert any("Popup detected" in gap for gap in broker.coverage)
            await broker.cancel()
        reviewed_cleanup(broker)
        assert broker.report.execution_status == "cancelled"
        assert "cancellation" in broker.report.terminal_reason

    asyncio.run(scenario())


def test_step_limit_blocks_additional_actions(resolved):
    # ResolvedRun is frozen; construct a validated equivalent with the tighter test ceiling.
    limits = resolved.environment.limits.model_copy(update={"max_steps": 1})
    limited = replace(
        resolved, environment=resolved.environment.model_copy(update={"limits": limits})
    )

    async def run():
        async with BrowserBroker(
            limited, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            await broker.act(Action(kind="wait", observation_id=broker.current.id, timeout_ms=1))
            result = await click(broker, "Start checkout")
            assert result.result == "blocked" and "ceiling" in result.detail
            assert not await broker.page.get_by_role(
                "heading", name="Checkout details"
            ).is_visible()
        reviewed_cleanup(broker)

    asyncio.run(run())


@pytest.mark.parametrize(
    "persona_id", ["enterprise_evaluator", "impatient_mobile", "keyboard_low_vision"]
)
def test_browser_demo_entry_uses_the_broker_and_produces_report(capsys, persona_id):
    assert asyncio.run(demo("healthy", persona_id)) == 0
    output = json.loads(capsys.readouterr().out)
    assert all(output["completion"].values()) and not output["cleanup_errors"]
    assert (Path(output["report_directory"]) / "report.html").is_file()


def test_runtime_watchdog_stops_and_reports_timeout(resolved):
    limits = resolved.environment.limits.model_copy(update={"max_runtime_seconds": 10})
    limited = replace(
        resolved, environment=resolved.environment.model_copy(update={"limits": limits})
    )

    async def scenario():
        async with BrowserBroker(
            limited, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS
        ) as broker:
            await broker.watchdog
        reviewed_cleanup(broker)
        assert broker.report.cohort_results.outcome_counts == {"timed_out": 1}
        assert broker.report.execution_status == "failed"
        assert "Runtime ceiling" in broker.report.terminal_reason

    asyncio.run(scenario())


def test_missing_browser_startup_failure_still_reports_and_disposes_owned_services(
    resolved, tmp_path, monkeypatch
):
    monkeypatch.setenv("FRICTIONLAB_BROWSER_PATH", str(tmp_path / "missing-browser.exe"))
    broker = BrowserBroker(resolved, persona_id="enterprise_evaluator", artifact_root=ARTIFACTS)

    async def scenario():
        with pytest.raises(FileNotFoundError):
            async with broker:
                pytest.fail("An absent browser executable cannot start execution")

    asyncio.run(scenario())
    assert broker.closed and not broker.cleanup_errors
    assert (
        broker.runtime.task is None
        and broker.runtime.proxy is None
        and broker.runtime.sentinel is None
    )
    assert broker.runtime.sentinel_state == {"requests": [], "balance": 100}
    assert broker.report.execution_status == "failed" and broker.report.report_status == "partial"
    assert "FileNotFoundError" in broker.report.terminal_reason
    assert "executable lookup" in broker.report.terminal_reason
    assert broker.report.cohort_results.executed_sessions == 0
    assert (broker.directory / "report.json").is_file()
    assert (broker.directory / "report.md").is_file()
    assert (broker.directory / "report.html").is_file()
