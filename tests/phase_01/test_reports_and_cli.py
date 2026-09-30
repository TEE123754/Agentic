import json
from pathlib import Path

import pytest

from frictionlab.__main__ import main
from frictionlab.configuration import resolve_run
from frictionlab.contracts.models import RunReport
from frictionlab.reporting import blocked_report, unexecuted_report, write_report

SECTIONS = (
    "Executive summary",
    "Scope and reproducibility",
    "Website protection",
    "Cohort results",
    "Individual trajectories",
    "UX findings",
    "Visual evidence and heatmaps",
    "Abandonment explanations",
    "Recommendations",
    "Comparison",
    "Review and limitations",
)


def check_partial(response):
    assert response.status_code == 409
    report = RunReport.model_validate(response.json()["report"])
    assert report.execution_status == "blocked" and report.report_status == "partial"
    assert report.protection.target_requests == 0
    assert not report.protection.network_boundary_validated
    assert not report.findings and not report.abandonment_explanations
    assert report.cohort_results.executed_sessions == 0
    return report


def test_configuration_review_is_offline_and_execution_disabled(client, payload):
    review = client.post("/configuration/review", json=payload)
    assert review.status_code == 200
    assert review.json()["configuration_valid"] and not review.json()["execution_enabled"]
    assert review.json()["requested_sessions"] == 9
    report = check_partial(client.post("/runs", json=payload))
    assert report.scope.configuration_hash == review.json()["configuration_hash"]
    assert report.cohort_results.requested_sessions == 9
    assert report.protection.environment_validated


def test_invalid_run_automatically_exports_all_sections(client, payload):
    payload["environment"] = "unknown_environment"
    response = client.post("/runs", json=payload)
    check_partial(response)
    for format_name, link in response.json()["downloads"].items():
        download = client.get(link)
        assert download.status_code == 200
        if format_name in {"md", "html"}:
            assert all(title in download.text for title in SECTIONS)
        else:
            RunReport.model_validate(download.json())
    html = client.get(response.json()["downloads"]["html"]).text
    assert "default-src 'none'" in html
    assert "<script" not in html and "<iframe" not in html


@pytest.mark.parametrize("rejected_body", [[], "private-secret-value", None])
def test_non_object_run_rejections_also_produce_reports(client, rejected_body):
    response = client.post(
        "/runs", content=json.dumps(rejected_body), headers={"Content-Type": "application/json"}
    )
    check_partial(response)
    assert "private-secret-value" not in response.text


def test_malformed_json_gets_partial_report(client):
    check_partial(
        client.post("/runs", content="{invalid", headers={"Content-Type": "application/json"})
    )


def test_invalid_review_does_not_echo_secret(client, payload):
    payload["api_key"] = "TOP_SECRET_PRIVATE"
    response = client.post("/configuration/review", json=payload)
    check_partial(response)
    assert "TOP_SECRET_PRIVATE" not in response.text


def test_report_export_escapes_html_and_is_immutable(tmp_path):
    report = blocked_report("<script>alert('x')</script>")
    directory = write_report(report, tmp_path)
    assert "<script>" not in (directory / "report.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in (directory / "report.html").read_text(encoding="utf-8")
    original = (directory / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        write_report(report, tmp_path)
    assert (directory / "report.json").read_bytes() == original


@pytest.mark.parametrize("status", ["failed", "cancelled", "interrupted"])
def test_pre_navigation_failure_reports_remain_factual(tmp_path, status):
    report = unexecuted_report("Stopped before navigation", execution_status=status)
    directory = write_report(report, tmp_path)
    assert report.execution_status == status and report.report_status == "partial"
    assert report.cohort_results.executed_sessions == 0 and not report.findings
    assert f"execution: {status}" in (directory / "report.html").read_text(encoding="utf-8")


def test_duplicate_run_id_does_not_overwrite_report(client, payload):
    payload["id"] = str(resolve_run(payload).config.id)
    first = client.post("/runs", json=payload)
    link = first.json()["downloads"]["json"]
    original = client.get(link).content
    second = client.post("/runs", json=payload)
    assert second.status_code == 409 and "already exists" in second.json()["detail"]
    assert client.get(link).content == original


def test_offline_cli_validation(payload, tmp_path, capsys):
    path = tmp_path / "run.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["validate", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] and not result["execution_enabled"]
    assert result["requested_sessions"] == 9


def test_cli_invalid_configuration_creates_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("frictionlab.__main__.ROOT", tmp_path)
    path = tmp_path / "invalid.json"
    path.write_text('{"secret": "TOP_SECRET"}', encoding="utf-8")
    assert main(["validate", str(path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "TOP_SECRET" not in json.dumps(result)
    assert (Path(result["report_directory"]) / "report.md").is_file()


def test_startup_entry_point_binds_only_loopback(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs)))
    assert main(["serve"]) == 0
    assert calls[0][1] == {"host": "127.0.0.1", "port": 8765}
    assert calls[0][0].state.origin == "http://127.0.0.1:8765"
    with pytest.raises(SystemExit):
        main(["serve", "--port", "80"])
