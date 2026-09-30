"""Offline contract checks; real OCI escape acceptance needs an installed runtime."""

import io
import json
import queue
from types import SimpleNamespace

import pytest

from frictionlab.planning.code_worker import (
    CodeWorkerSettings,
    _read_frames,
    execute_cell,
    inspect_image,
    local_settings,
    podman_command,
    worker_environment,
)
from frictionlab.planning.container_worker import validate_code
from frictionlab.planning.contracts import PlannerStopped
from frictionlab.planning.worker_gate import REQUIRED_CHECKS, require_worker_gate

PIN = "sha256:" + "a" * 64


def test_command_has_kernel_boundaries_and_no_host_mount_or_network():
    settings = CodeWorkerSettings(PIN, "C:/Program Files/RedHat/Podman/podman.exe")
    command = podman_command(settings, "frictionlab-code-" + "b" * 32)
    for required in (
        "--network=none", "--read-only", "--cap-drop=all",
        "--security-opt=no-new-privileges", "--user=65534:65534",
        "--pids-limit=32", "--memory=256m", "--cpus=0.5",
        "--pull=never", "--ipc=private", "--pid=private",
    ):
        assert required in command
    assert not any(value.startswith(("--volume", "--mount", "-v", "--env")) for value in command)
    assert command[command.index("--entrypoint=python") + 1] == PIN
    assert command[-1] == "/opt/frictionlab/worker.py"


@pytest.mark.parametrize("image", ["python:3.12", "sha256:abc", "sha256:" + "A" * 64])
def test_unpinned_image_fails_closed(image):
    with pytest.raises(PlannerStopped, match="pinned SHA-256"):
        CodeWorkerSettings(image, "podman")


def test_invalid_container_name_fails_closed():
    with pytest.raises(PlannerStopped, match="name"):
        podman_command(CodeWorkerSettings(PIN, "podman"), "another-container")


@pytest.mark.parametrize("observed", [PIN, PIN.removeprefix("sha256:")])
def test_image_inspection_accepts_only_the_pinned_digest(monkeypatch, observed):
    responses = iter(["true", observed])
    monkeypatch.setattr(
        "frictionlab.planning.code_worker.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=next(responses)),
    )
    inspect_image(CodeWorkerSettings(PIN, "podman"))


def test_image_inspection_rejects_a_different_digest(monkeypatch):
    responses = iter(["true", "b" * 64])
    monkeypatch.setattr(
        "frictionlab.planning.code_worker.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=next(responses)),
    )
    with pytest.raises(PlannerStopped, match="does not match"):
        inspect_image(CodeWorkerSettings(PIN, "podman"))


def test_cell_rejects_oversized_code_before_runtime(monkeypatch):
    monkeypatch.setattr("frictionlab.planning.code_worker.inspect_image", lambda _: pytest.fail("runtime reached"))
    with pytest.raises(PlannerStopped, match="byte ceiling"):
        execute_cell("x" * 8193, {}, None, CodeWorkerSettings(PIN, "podman"))


def test_runtime_is_absent_and_code_mode_stays_closed(monkeypatch):
    monkeypatch.setattr("frictionlab.planning.code_worker.shutil.which", lambda _: None)
    with pytest.raises(PlannerStopped, match="Podman is unavailable"):
        local_settings(PIN)


def test_worker_process_environment_omits_api_credentials(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    assert "GROQ_API_KEY" not in worker_environment()
    assert "GOOGLE_API_KEY" not in worker_environment()


def test_oversized_worker_output_is_rejected():
    class Stream(io.BytesIO):
        def fileno(self):
            return 0

    # Patch only the byte reader. No code is evaluated outside an OCI runtime.
    events = queue.Queue()
    payloads = iter([b"x" * 16385, b""])
    from unittest.mock import patch

    with patch("frictionlab.planning.code_worker.os.read", side_effect=lambda *_: next(payloads)):
        _read_frames(Stream(), events)
    result = events.get_nowait()
    assert isinstance(result, PlannerStopped)
    assert result.category == "code_output_limit"


def test_code_agent_gate_requires_a_real_acceptance_record(tmp_path, monkeypatch):
    gate = tmp_path / "worker-boundary-gate.json"
    monkeypatch.setattr("frictionlab.planning.worker_gate.GATE_PATH", gate)
    with pytest.raises(PlannerStopped, match="no host/image boundary"):
        require_worker_gate()
    gate.write_text(json.dumps({"version": 1, "status": "passed", "host": "host"}), encoding="utf-8")
    with pytest.raises(PlannerStopped, match="record is invalid"):
        require_worker_gate()


def test_code_agent_gate_is_host_image_and_check_specific(tmp_path, monkeypatch):
    gate = tmp_path / "worker-boundary-gate.json"
    monkeypatch.setattr("frictionlab.planning.worker_gate.GATE_PATH", gate)
    monkeypatch.setattr("frictionlab.planning.worker_gate.platform.node", lambda: "owned-host")
    settings = CodeWorkerSettings(PIN, "podman")
    monkeypatch.setattr("frictionlab.planning.worker_gate.local_settings", lambda image: settings)
    monkeypatch.setattr("frictionlab.planning.worker_gate.inspect_image", lambda _: None)
    gate.write_text(
        json.dumps({
            "version": 1, "status": "passed", "host": "owned-host",
            "image_id": PIN, "passed_checks": sorted(REQUIRED_CHECKS), "failed_checks": [],
        }),
        encoding="utf-8",
    )
    assert require_worker_gate() == settings
    data = json.loads(gate.read_text(encoding="utf-8"))
    data["passed_checks"].remove("network_denied")
    gate.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlannerStopped, match="record is invalid"):
        require_worker_gate()


def test_code_executor_exposes_only_reviewed_tools(monkeypatch):
    from frictionlab.planning.code_agent import PodmanPythonExecutor

    bridge = SimpleNamespace(stopped=False, broker=SimpleNamespace(finished=False))
    memory = SimpleNamespace(state={"observation_id": "owned"})
    executor = PodmanPythonExecutor(bridge, memory, CodeWorkerSettings(PIN, "podman"))
    executor.send_tools({"browser_action": object(), "final_answer": object()})
    with pytest.raises(PlannerStopped, match="unapproved tool"):
        executor.send_tools({"shell": object()})
    with pytest.raises(PlannerStopped, match="state cannot enter"):
        executor.send_variables({"secret": "value"})
    monkeypatch.setattr(
        "frictionlab.planning.code_agent.execute_cell",
        lambda code, observation, bridge, settings: {"result": "ok", "tool_calls": 1},
    )
    output = executor("result = tool({})")
    assert output.output == "ok"
    assert output.is_final_answer is False


def test_code_agent_construction_uses_remote_executor_only():
    from frictionlab.planning.code_agent import (
        BoundedCodeAgent,
        LocalCodeModel,
        PodmanPythonExecutor,
    )
    from frictionlab.planning.contracts import AgentLimits

    limits = AgentLimits()
    memory = SimpleNamespace(state={"observation_id": "owned"}, messages=[])
    writer = SimpleNamespace(json=lambda *args: None)
    bridge = SimpleNamespace(stopped=False, broker=SimpleNamespace(finished=False))
    model = LocalCodeModel(None, memory, limits, 1, writer)
    agent = BoundedCodeAgent(model, memory, bridge, limits, CodeWorkerSettings(PIN, "podman"))
    assert isinstance(agent.python_executor, PodmanPythonExecutor)
    assert set(agent.tools) == {"browser_action", "final_answer"}


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from pathlib import Path",
        "__import__('os')",
        "open('/etc/passwd')",
        "tool.__globals__",
        "getattr(tool, '__globals__')",
    ],
)
def test_worker_rejects_direct_import_process_file_and_introspection_paths(code):
    with pytest.raises((TypeError, ValueError)):
        validate_code(code)


def test_worker_accepts_simple_grounded_tool_composition_without_executing_it():
    validate_code("result = tool({'kind': 'click', 'observation_id': observation['observation_id'], 'candidate_id': observation['candidates'][0]['id']})")
