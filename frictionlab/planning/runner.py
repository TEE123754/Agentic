"""One autonomous persona on an owned fixture, with an offline report for every outcome."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import platform
import time
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError

from frictionlab.browser.broker import BrowserBroker
from frictionlab.cognition.runtime import CognitiveRuntime
from frictionlab.configuration import (
    CONFIG_DIRECTORY,
    ROOT,
    ConfigurationRejected,
    read_json,
    resolve_run,
)
from frictionlab.contracts.models import CohortResults, PlannerDecisionRecord, RunReport
from frictionlab.planning.cloud_model import CloudModelRuntime, CloudPlannerModel
from frictionlab.planning.code_agent import BoundedCodeAgent, CodePersonaMemory, LocalCodeModel
from frictionlab.planning.contracts import PlannerStopped, load_limits
from frictionlab.planning.inference import load_inference
from frictionlab.planning.local_model import LocalModelRuntime, LocalPlannerModel
from frictionlab.planning.memory import PersonaMemory
from frictionlab.planning.tools import BoundedPersonaAgent, ToolBridge
from frictionlab.planning.worker_gate import require_worker_gate
from frictionlab.reporting import unexecuted_report, write_report


async def run_persona(
    resolved,
    *,
    persona_id="impatient_mobile",
    journey_id="checkout_review",
    variant="healthy",
    limits=None,
    runtime=None,
    model_factory=None,
    mode="typed_tools",
    behavioral=False,
    artifact_root=None,
    global_budget=None,
    session_id=None,
    inference=None,
):
    limits = limits or load_limits()
    state = {
        "category": "not_started",
        "reason": "Autonomous session has not started.",
        "model": None,
        "bridge": None,
        "runtime": runtime,
        "model_owned": runtime is None,
        "worker_drained": True,
        "cognition": None,
        "execution_mode": "typed_tools",
        "code_settings": None,
    }

    def transform(base):
        model = state["model"]
        bridge = state["bridge"]
        model_runtime = state["runtime"]
        cognition = state["cognition"]
        records = getattr(model, "records", [])
        data = base.model_dump(mode="json")
        metadata = data["scope"]["runtime_metadata"]
        metadata.update(
            {
                "execution_mode": state["execution_mode"],
                "requested_execution_mode": mode,
                "generated_python_executed": bool(
                    bridge and getattr(bridge, "code_executed", False)
                ),
                "vision_enabled": False,
                "smolagents": importlib.metadata.version("smolagents"),
                "planner_stop_category": state["category"],
                "planner_decisions": len(records),
                "trusted_tool_calls": bridge.calls if bridge else 0,
                "provider_retries": 0,
                "max_planner_steps": limits.max_steps,
                "max_tool_calls": limits.max_tool_calls,
                "max_input_tokens": limits.max_input_tokens,
                "max_output_tokens": limits.max_output_tokens,
                "planner_runtime_ceiling_seconds": limits.max_runtime_seconds,
                "model_inference_seconds": round(
                    sum(record["inference_seconds"] for record in records), 6
                ),
                "application_seconds": round(
                    sum(step.application_seconds for step in broker.steps), 6
                ),
                "model_owned_by_session": state["model_owned"],
                "planner_worker_drained": state["worker_drained"],
                "planning_protocol": getattr(model, "planning_protocol", "json_decision_v1"),
                "planner_rationale_source": (
                    "trusted_action_description"
                    if getattr(model, "planning_protocol", "") == "semantic_choice_v1"
                    else "model"
                ),
            }
        )
        if state["code_settings"]:
            metadata.update(
                {
                    "code_worker_image_id": state["code_settings"].image_id,
                    "code_worker_gate_host": platform.node(),
                    "code_worker_started": bool(
                        bridge and getattr(bridge, "code_worker_started", False)
                    ),
                    "code_worker_rootless_required": True,
                }
            )
        if model_runtime and getattr(model_runtime, "is_remote", False):
            metadata["inference"] = json.dumps(model_runtime.provenance(), sort_keys=True)
            metadata["provider_retries"] = model_runtime.retries
            metadata["max_input_tokens"] = model_runtime.config.max_input_bytes + 512
            metadata["max_input_bytes"] = model_runtime.config.max_input_bytes
            metadata["input_token_accounting"] = "conservative UTF-8 byte and framing reservation"
        else:
            metadata["inference"] = json.dumps(
                {
                    "provider": "local",
                    "actual_models": [getattr(model, "model_id", "not_started")],
                    "strict_comparable": model is not None,
                },
                sort_keys=True,
            )
        if model_runtime and not getattr(model_runtime, "is_remote", False):
            metadata.update(
                {
                    "model_repository": model_runtime.settings["repository"],
                    "model_revision": model_runtime.settings["revision"],
                    "model_sha256": model_runtime.verified_model_sha256 or "unverified",
                    "llama_cpp_release": model_runtime.resources[model_runtime.runtime_key].get(
                        "release", "b11247"
                    ),
                    "model_startup_seconds": round(model_runtime.startup_seconds, 6),
                    "model_peak_rss_bytes": model_runtime.peak_rss_bytes,
                    "model_memory_limit_hit": model_runtime.memory_exceeded,
                    "model_prompt_cache_mib": 512,
                    "model_process_stopped": bool(
                        model_runtime.process is None or model_runtime.process.poll() is not None
                    ),
                }
            )
        data["scope"]["phase"] = 4 if behavioral else 3
        if cognition:
            metadata.update(
                {
                    "cognitive_policy_version": cognition.policy.version,
                    "cognitive_policy_sha256": cognition.policy_sha256,
                    "patience_initial": cognition.initial,
                    "patience_remaining": cognition.remaining,
                    "cognitive_events": len(cognition.events),
                    "behavioral_delay_seconds": 0,
                    "queue_seconds": 0,
                }
            )
        data["planner_decisions"] = [
            PlannerDecisionRecord.model_validate(record).model_dump(mode="json")
            for record in records
        ]
        data["terminal_reason"] = (
            state["reason"] if state["category"] != "not_started" else base.terminal_reason
        )
        completed = bool(broker.completion) and all(broker.completion.values())
        if state["category"] == "completed" and (not completed or broker.cleanup_errors):
            data["terminal_reason"] = (
                "Final completion or cleanup review failed; planned success is not accepted."
            )
        executed = int(broker.started_navigation)
        outcome = (
            "timed_out"
            if broker.timed_out
            else "cancelled"
            if broker.cancelled
            else "abandoned_patience"
            if cognition and cognition.abandoned and not broker.cleanup_errors
            else "blocked_protection"
            if state["category"] == "blocked_protection"
            else "completed"
            if state["category"] == "completed" and completed and not broker.cleanup_errors
            else "inconclusive_agent_failure"
        )
        data["execution_status"] = (
            "cancelled"
            if broker.cancelled
            else "blocked"
            if outcome == "blocked_protection"
            or not executed
            and state["category"] == "code_isolation_unavailable"
            else "completed"
            if outcome in {"completed", "abandoned_patience"}
            else "failed"
        )
        data["cohort_results"] = CohortResults(
            requested_sessions=1,
            executed_sessions=executed,
            eligible_sessions=(
                int(outcome in {"completed", "abandoned_patience"}) if behavioral else 0
            ),
            outcome_counts={outcome: 1} if executed else {},
        ).model_dump(mode="json")
        if behavioral:
            diagnosis = (
                cognition.diagnosis(broker.current)
                if cognition and outcome == "abandoned_patience"
                else None
            )
            data["friction_events"] = (
                [event.model_dump(mode="json") for event in cognition.events] if cognition else []
            )
            data["patience_ledger"] = (
                [entry.model_dump(mode="json") for entry in cognition.ledger] if cognition else []
            )
            data["abandonment_diagnosis"] = diagnosis.model_dump(mode="json") if diagnosis else None
            data["abandonment_explanations"] = [diagnosis.first_person] if diagnosis else []
            data["executive_summary"] = (
                f"One model-driven {broker.persona.id} session attempted {broker.journey.id} on the owned {variant} fixture. Outcome: {outcome if executed else 'not executed'}. {len(records)} model decisions, {len(broker.steps)} browser actions, and {len(cognition.events) if cognition else 0} grounded friction events recorded. Independent goal assertions {'passed' if completed else 'did not all pass'}. Synthetic abandonment is asserted only when recorded application friction exhausted patience; this is not human churn evidence."
            )
        else:
            data["executive_summary"] = (
                f"One model-driven {broker.persona.id} session attempted {broker.journey.id} on the owned {variant} fixture. Outcome: {outcome if executed else 'not executed'}. {len(records)} model decisions and {len(broker.steps)} browser actions recorded. Independent goal assertions {'passed' if completed else 'did not all pass'}. No patience, UX finding, or human churn inference is asserted."
            )
        data["recommendations"] = [
            "Review the saved decisions, masked observations, and independent goal/protection assertions offline.",
            (
                "Review the recorded friction event and verify any interface change in a new disposable fixture run; this report does not implement or deploy fixes."
                if behavioral
                else "Implement Phase 4 friction detectors and patience accounting before asserting synthetic abandonment causes."
            ),
            "Keep external targets disabled; enable generated Python only for the exact host/image after its OS/container boundary batch passes.",
        ]
        data["review"]["method"] = (
            "Saved decision/action evidence and independent completion/protection checks; no repeat browser navigation during review."
        )
        data["review"]["missing_evidence"] = [
            item
            for item in data["review"]["missing_evidence"]
            if item != "Autonomous behavioral cohort"
        ] + ["Cohort orchestration and behavioral calibration"]
        data["review"]["limitations"] += [
            "Only the bundled disposable fixture is supported; no production or staging URL is accepted.",
            (
                "The CodeAgent worker is limited to the accepted host/image boundary record; this does not authorize external targets."
                if state["execution_mode"] == "isolated_code"
                else "Typed ToolCallingAgent mode executes reviewed tools only; generated Python remains disabled without a passing host/image gate."
            ),
            "One seeded journey per session is a provisional capability check, not a calibrated usability or conversion estimate.",
            "Vision is disabled; no coordinate model fallback was used.",
        ]
        broker.writer.json(
            "planner-review.json",
            {
                "stop_category": state["category"],
                "reason": data["terminal_reason"],
                "limits": limits.model_dump(mode="json"),
                "completion": broker.completion,
                "model_owned": state["model_owned"],
                "worker_drained": state["worker_drained"],
            },
        )
        return RunReport.model_validate(data)

    broker = BrowserBroker(
        resolved,
        persona_id=persona_id,
        journey_id=journey_id,
        variant=variant,
        artifact_root=artifact_root
        or ROOT / "artifacts" / ("phase4" if behavioral else "phase3") / "runs",
        report_transform=transform,
        global_budget=global_budget,
        session_id=session_id,
    )
    worker = agent = model = bridge = None
    try:
        if mode not in {"typed_tools", "isolated_code"}:
            raise PlannerStopped(
                "code_isolation_unavailable",
                "Unknown execution mode; no browser or model was started.",
            )
        if mode != "typed_tools" and getattr(runtime, "is_remote", False):
            raise PlannerStopped("model_setup", "BYOK supports reviewed typed tools only")
        code_settings = require_worker_gate() if mode == "isolated_code" else None
        state["execution_mode"] = mode
        state["code_settings"] = code_settings
        if runtime is None and model_factory is None:
            inference = (
                load_inference(inference)
                if inference is None or hasattr(inference, "read_text")
                else inference
            )
            if inference.provider != "local" and mode != "typed_tools":
                raise PlannerStopped("model_setup", "BYOK supports reviewed typed tools only")
            runtime = (
                CloudModelRuntime(inference)
                if inference.provider != "local"
                else LocalModelRuntime(broker.directory / "model")
            )
            state["runtime"] = runtime
            await runtime.__aenter__()
        # Startup is managed here so failures are classified before immutable export.
        await asyncio.wait_for(broker.start(), timeout=45)
        if behavioral:
            state["cognition"] = CognitiveRuntime(broker.persona, broker.run_id, broker.writer)
            broker.cognitive_runtime = state["cognition"]
        memory = (CodePersonaMemory if code_settings else PersonaMemory)(broker, limits)
        await memory.refresh()
        model = (
            model_factory
            or (
                CloudPlannerModel
                if getattr(runtime, "is_remote", False)
                else LocalCodeModel
                if code_settings
                else LocalPlannerModel
            )
        )(runtime, memory, limits, resolved.config.seed, broker.writer)
        state["model"] = model
        bridge = ToolBridge(
            broker,
            memory,
            limits,
            asyncio.get_running_loop(),
            cognition=state["cognition"],
        )
        bridge.model = model
        state["bridge"] = bridge
        agent = (
            BoundedCodeAgent(model, memory, bridge, limits, code_settings)
            if code_settings
            else BoundedPersonaAgent(model, memory, bridge, limits)
        )
        worker = asyncio.create_task(asyncio.to_thread(agent.run, broker.journey.goal))
        ceiling = min(
            limits.max_runtime_seconds,
            max(
                0.1,
                resolved.environment.limits.max_runtime_seconds
                - (time.monotonic() - broker.started),
            ),
        )
        await asyncio.wait_for(asyncio.shield(worker), timeout=ceiling)
        completion = await broker.verify_completion()
        if not completion or not all(completion.values()) or not broker.finished:
            raise PlannerStopped(
                "premature_finish",
                "Agent stopped without a trusted finish and passing independent goal criteria.",
            )
        state.update(
            category="completed",
            reason="Autonomous persona finished; all independent journey criteria passed.",
        )
    except asyncio.CancelledError:
        broker.cancelled = True
        state.update(
            category="cancelled",
            reason="Emergency cancellation stopped autonomous planning; no abandonment inferred.",
        )
        raise
    except (TimeoutError, PlannerStopped) as exc:
        category = exc.category if isinstance(exc, PlannerStopped) else "runtime_limit"
        reason = (
            str(exc)
            if isinstance(exc, PlannerStopped)
            else "Autonomous session deadline exceeded; no abandonment inferred."
        )
        broker.failed = category not in {
            "blocked_protection",
            "code_isolation_unavailable",
            "abandoned_patience",
        }
        broker.timed_out = category == "runtime_limit"
        state.update(category=category, reason=reason)
        broker.failure_reason = reason
    except Exception as exc:  # noqa: BLE001 -- every terminal run retains a factual report
        fault = (bridge.last_fault if bridge else None) or (
            getattr(model, "last_fault", None) if model else None
        )
        category = fault.category if fault else "agent_error"
        reason = (
            str(fault)
            if fault
            else f"Autonomous execution failed at {broker.stage} ({type(exc).__name__}); no UX diagnosis inferred."
        )
        broker.failed = category != "blocked_protection"
        broker.timed_out = category == "runtime_limit"
        state.update(category=category, reason=reason)
        broker.failure_reason = reason
    finally:
        if model:
            model.stopped.set()
        if bridge:
            bridge.stopped = True
        if broker.runtime.policy:
            broker.runtime.policy.stopped.set()
        if worker and not worker.done():
            if agent:
                agent.interrupt()
            try:
                await asyncio.wait_for(asyncio.shield(worker), timeout=65)
            except Exception:  # noqa: BLE001 -- bounded drain after stop; record any residual worker
                state["worker_drained"] = worker.done()
            if not state["worker_drained"]:
                broker.cleanup_errors.append(
                    "Planner worker did not drain within its stop deadline"
                )
        if state["model_owned"] and runtime:
            try:
                await runtime.close()
            except Exception as exc:  # noqa: BLE001 -- browser cleanup must still proceed
                broker.cleanup_errors.append(f"Owned model cleanup: {type(exc).__name__}")
        await broker.close()
    return broker


async def autonomous_cli(persona, journey, variant, mode, *, behavioral=False, inference_path=None):
    resolved = None
    try:
        resolved = resolve_run(read_json(CONFIG_DIRECTORY / "run.example.json"))
        limits = load_limits()
        if persona not in resolved.config.personas or journey not in resolved.config.journeys:
            raise ConfigurationRejected(
                ["Requested profile or journey is not enabled in this configuration."]
            )
    except (ConfigurationRejected, ValidationError) as exc:
        reason = (
            str(exc)
            if isinstance(exc, ConfigurationRejected)
            else "Agent settings do not match the supported typed-tools contract."
        )
        data = unexecuted_report(reason, resolved).model_dump(mode="json")
        data["run_id"] = str(uuid4())
        data["scope"].update(
            phase=4 if behavioral else 3,
            personas=[persona],
            journeys=[journey],
            runtime_metadata={
                "execution_mode": "not_started",
                "requested_execution_mode": mode,
                "planner_stop_category": "configuration_rejected",
                "generated_python_executed": False,
                "vision_enabled": False,
                "planner_worker_drained": True,
            },
        )
        data["cohort_results"]["requested_sessions"] = 1
        data["recommendations"] = [
            "Correct the configuration and choose an enabled profile and journey.",
            "Use the owned local fixture; stronger isolation is required before external replicas or generated Python.",
        ]
        report = RunReport.model_validate(data)
        directory = write_report(
            report, ROOT / "artifacts" / ("phase4" if behavioral else "phase3") / "runs"
        )
        broker = SimpleNamespace(report=report, directory=directory, completion={})
    else:
        broker = await run_persona(
            resolved,
            persona_id=persona,
            journey_id=journey,
            variant=variant,
            mode=mode,
            behavioral=behavioral,
            limits=limits,
            inference=inference_path,
        )
    print(
        json.dumps(
            {
                "report_directory": str(broker.directory),
                "execution_status": broker.report.execution_status,
                "report_status": broker.report.report_status,
                "completion": broker.completion,
                "planner_decisions": len(broker.report.planner_decisions),
                "friction_events": len(broker.report.friction_events),
                "terminal_reason": broker.report.terminal_reason,
                "sentinel_requests": broker.report.protection.sentinel_requests,
            },
            indent=2,
        )
    )
    return 0 if broker.report.execution_status == "completed" else 1
