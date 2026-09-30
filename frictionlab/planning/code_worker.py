"""Host-side OCI launcher and narrow, validated stdio bridge for generated code.

This module never evaluates a code cell in the host Python process. Runtime
availability alone does not unlock the product mode; the isolation gate must
also be run on the actual host and image first.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from frictionlab.planning.contracts import PlannerStopped

IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_CELL_BYTES = 8192
MAX_OBSERVATION_BYTES = 20000
MAX_LINE_BYTES = 16384
MAX_OUTPUT_BYTES = 131072


@dataclass(frozen=True)
class CodeWorkerSettings:
    image_id: str
    podman_path: str
    timeout_seconds: int = 75

    def __post_init__(self):
        if not IMAGE_ID.fullmatch(self.image_id):
            raise PlannerStopped("code_isolation_unavailable", "Worker image must have a pinned SHA-256 ID.")
        if not self.podman_path or os.path.basename(self.podman_path).lower() not in {
            "podman", "podman.exe"
        }:
            raise PlannerStopped("code_isolation_unavailable", "A local Podman executable is required.")
        if not 5 <= self.timeout_seconds <= 90:
            raise PlannerStopped("code_isolation_unavailable", "Worker timeout is outside the bounded range.")


def worker_environment():
    """Podman client gets only OS essentials; no API keys or model credentials."""
    allowed = (
        "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
        "USER", "LOGNAME", "XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
    )
    return {key: os.environ[key] for key in allowed if key in os.environ}


def podman_command(settings: CodeWorkerSettings, name: str):
    if not re.fullmatch(r"frictionlab-code-[0-9a-f]{32}", name):
        raise PlannerStopped("code_isolation_unavailable", "Invalid disposable worker name.")
    return [
        settings.podman_path,
        "run", "--rm", "--interactive", "--pull=never", f"--name={name}",
        "--network=none", "--read-only", "--cap-drop=all",
        "--security-opt=no-new-privileges", "--user=65534:65534",
        "--pids-limit=32", "--memory=256m", "--cpus=0.5",
        "--ipc=private", "--pid=private", "--uts=private",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--workdir=/tmp", "--entrypoint=python",
        settings.image_id, "-I", "-u", "/opt/frictionlab/worker.py",
    ]


def local_settings(image_id: str | None = None):
    path = shutil.which("podman")
    if not path:
        raise PlannerStopped("code_isolation_unavailable", "Podman is unavailable on this host.")
    image_id = image_id or os.environ.get("FRICTIONLAB_CODE_IMAGE_ID", "")
    return CodeWorkerSettings(image_id=image_id, podman_path=path)


def inspect_image(settings: CodeWorkerSettings):
    try:
        runtime = subprocess.run(
            [settings.podman_path, "info", "--format", "{{.Host.Security.Rootless}}"],
            capture_output=True, text=True, timeout=10, env=worker_environment(), check=True,
        )
        if runtime.stdout.strip().lower() != "true":
            raise PlannerStopped("code_isolation_unavailable", "The Podman worker must run rootless.")
        result = subprocess.run(
            [settings.podman_path, "image", "inspect", settings.image_id, "--format", "{{.Id}}"],
            capture_output=True, text=True, timeout=10, env=worker_environment(), check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PlannerStopped("code_isolation_unavailable", "Pinned worker image is not locally inspectable.") from exc
    observed_id = result.stdout.strip()
    if observed_id.removeprefix("sha256:") != settings.image_id.removeprefix("sha256:"):
        raise PlannerStopped(
            "code_isolation_unavailable",
            f"Local worker image ID does not match the pin: {observed_id[:80]!r}.",
        )


def _read_frames(stream, events):
    pending = bytearray()
    total = 0
    try:
        while chunk := os.read(stream.fileno(), 4096):
            total += len(chunk)
            if total > MAX_OUTPUT_BYTES:
                events.put(PlannerStopped("code_output_limit", "Worker output exceeded its byte ceiling."))
                return
            pending.extend(chunk)
            if len(pending) > MAX_LINE_BYTES and b"\n" not in pending:
                events.put(PlannerStopped("code_output_limit", "Worker frame exceeded its byte ceiling."))
                return
            while b"\n" in pending:
                line, _, pending = pending.partition(b"\n")
                if len(line) > MAX_LINE_BYTES:
                    events.put(PlannerStopped("code_output_limit", "Worker frame exceeded its byte ceiling."))
                    return
                events.put(bytes(line))
        if pending:
            events.put(PlannerStopped("code_protocol", "Worker ended with an incomplete frame."))
    except OSError:
        events.put(PlannerStopped("code_protocol", "Worker output stream failed."))
    finally:
        events.put(None)


def _cleanup_container(settings: CodeWorkerSettings, name: str):
    """Wait for Podman to release a killed client's container, then verify absence."""
    last_error = ""
    for attempt in range(5):
        try:
            removed = subprocess.run(
                [settings.podman_path, "rm", "--force", "--ignore", name],
                capture_output=True, timeout=10, env=worker_environment(), check=False,
            )
            exists = subprocess.run(
                [settings.podman_path, "container", "exists", name],
                capture_output=True, timeout=10, env=worker_environment(), check=False,
            )
            if removed.returncode == 0 and exists.returncode == 1:
                return
            last_error = (
                f"remove={removed.returncode}, exists={exists.returncode}, "
                f"stderr={removed.stderr.decode('utf-8', 'replace')[:160]}"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = type(exc).__name__
        if attempt < 4:
            time.sleep(0.5)
    raise PlannerStopped(
        "code_cleanup_failure", f"Disposable worker cleanup could not be verified ({last_error})."
    )


def execute_cell(code: str, observation: dict, bridge, settings: CodeWorkerSettings):
    """Execute one cell in a fresh container; all browser effects pass ToolBridge."""
    if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_CELL_BYTES:
        raise PlannerStopped("invalid_model_output", "Generated code cell exceeds its byte ceiling.")
    if not isinstance(observation, dict):
        raise PlannerStopped("context_limit", "Worker observation must be an object.")
    input_bytes = json.dumps(
        {"code": code, "observation": observation}, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    if len(input_bytes) > 32768 or len(json.dumps(observation).encode("utf-8")) > MAX_OBSERVATION_BYTES:
        raise PlannerStopped("context_limit", "Worker input exceeds its byte ceiling.")
    inspect_image(settings)
    name = "frictionlab-code-" + uuid4().hex
    try:
        process = subprocess.Popen(
            podman_command(settings, name), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=worker_environment(), bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        raise PlannerStopped("code_isolation_unavailable", "Isolated worker failed to start.") from exc
    events = queue.Queue()
    reader = threading.Thread(target=_read_frames, args=(process.stdout, events), daemon=True)
    reader.start()
    bridge.code_worker_started = True
    deadline = time.monotonic() + settings.timeout_seconds
    calls = 0
    outcome = None
    try:
        process.stdin.write(input_bytes + b"\n")
        process.stdin.flush()
        while True:
            if bridge.stopped:
                raise PlannerStopped("cancelled", "Isolated code worker was cancelled.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlannerStopped("code_runtime_limit", "Isolated code cell exceeded its wall-clock limit.")
            try:
                frame = events.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive():
                    raise PlannerStopped("code_protocol", "Worker exited without a terminal frame.")
                continue
            if isinstance(frame, PlannerStopped):
                raise frame
            if frame is None:
                break
            try:
                message = json.loads(frame)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Arbitrary print output is not an IPC instruction.
                continue
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "tool_call":
                bridge.code_executed = True
                if set(message) != {"type", "action"} or not isinstance(message["action"], dict):
                    raise PlannerStopped("code_protocol", "Worker tool-call frame is invalid.")
                if bridge.broker.finished:
                    raise PlannerStopped("post_completion_action", "Code requested an action after verified completion.")
                calls += 1
                if calls > bridge.limits.max_tool_calls:
                    raise PlannerStopped("tool_limit", "Worker exceeded the trusted tool-call ceiling.")
                # Worker text is untrusted; dispatch rechecks schema, observation, candidates,
                # finish assertion, protection, quotas, and current broker state.
                result = bridge.call(message["action"], final=message["action"].get("kind") == "finish")
                if not result["completion_verified"]:
                    result = {**result, "observation": bridge.memory.state}
                answer = json.dumps({"type": "tool_result", "result": result}, separators=(",", ":"))
                if len(answer.encode("utf-8")) > MAX_LINE_BYTES:
                    raise PlannerStopped("context_limit", "Filtered worker observation exceeds IPC ceiling.")
                process.stdin.write(answer.encode("utf-8") + b"\n")
                process.stdin.flush()
            elif kind == "done":
                bridge.code_executed = True
                if set(message) != {"type", "result"} or not isinstance(message["result"], str):
                    raise PlannerStopped("code_protocol", "Worker completion frame is invalid.")
                outcome = message["result"][:2048]
                break
            elif kind == "error":
                bridge.code_executed = True
                raise PlannerStopped("code_execution_error", str(message.get("detail", "Worker failed."))[:1024])
            else:
                raise PlannerStopped("code_protocol", "Worker emitted an unknown IPC instruction.")
        if outcome is None:
            raise PlannerStopped("code_protocol", "Worker finished without a completion frame.")
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise PlannerStopped("code_runtime_limit", "Worker did not exit after completion.") from exc
        if process.returncode != 0:
            raise PlannerStopped("code_execution_error", "Worker exited unsuccessfully after a result.")
        return {"result": outcome, "tool_calls": calls}
    finally:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        process.stdin.close()
        process.stdout.close()
        reader.join(timeout=2)
        # A killed Podman client may leave its container behind. Clean by our UUID name.
        _cleanup_container(settings, name)
