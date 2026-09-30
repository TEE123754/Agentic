import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from frictionlab.configuration import ConfigurationRejected
from frictionlab.contracts.models import RunReport
from frictionlab.planning import runner
from frictionlab.planning.contracts import AgentLimits


@pytest.mark.parametrize("case", ["configuration", "selection", "limits"])
def test_cli_preflight_rejections_export_before_any_execution(resolved, monkeypatch, capsys, case):
    def must_not_run(*args, **kwargs):
        raise AssertionError("Preflight must not reach browser/model execution")

    monkeypatch.setattr(runner, "run_persona", must_not_run)
    if case == "configuration":

        def reject(*args):
            raise ConfigurationRejected(["Invalid configuration; no rejected input echoed."])

        monkeypatch.setattr(runner, "resolve_run", reject)
    elif case == "selection":
        selected = replace(
            resolved,
            config=resolved.config.model_copy(update={"personas": ("enterprise_evaluator",)}),
        )
        monkeypatch.setattr(runner, "resolve_run", lambda *args: selected)
    else:
        # Exercise the actual Pydantic failure with a sensitive unexpected field.
        def reject_limits():
            return AgentLimits.model_validate({"private_key": "never-print-this-value"})

        monkeypatch.setattr(runner, "load_limits", reject_limits)
    assert (
        asyncio.run(
            runner.autonomous_cli("impatient_mobile", "checkout_review", "healthy", "typed_tools")
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "never-print-this-value" not in output
    directory = Path(json.loads(output)["report_directory"])
    report = RunReport.model_validate_json((directory / "report.json").read_text(encoding="utf-8"))
    assert report.scope.phase == 3 and report.execution_status == "blocked"
    assert (
        report.cohort_results.requested_sessions == 1
        and report.cohort_results.executed_sessions == 0
    )
    assert (
        report.protection.target_requests == 0 and not report.protection.network_boundary_validated
    )
    assert (
        not report.planner_decisions and not report.findings and not report.abandonment_explanations
    )
    assert report.scope.runtime_metadata["planner_stop_category"] == "configuration_rejected"
    assert all((directory / f"report.{suffix}").is_file() for suffix in ("json", "md", "html"))
