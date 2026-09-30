"""One real, disposable Podman boundary batch on the current Linux host/image."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from uuid import uuid4

from frictionlab.configuration import ROOT
from frictionlab.planning.code_worker import (
    CodeWorkerSettings,
    execute_cell,
    inspect_image,
    local_settings,
    podman_command,
    worker_environment,
)
from frictionlab.planning.contracts import AgentLimits, PlannerStopped
from frictionlab.planning.tools import ToolBridge
from frictionlab.planning.worker_gate import GATE_PATH, REQUIRED_CHECKS

OUTPUT = ROOT / "artifacts" / "phase3"


def probe(settings, source, *, timeout=25):
    """Use the exact worker flags but replace its program with an OS-level probe."""
    name = "frictionlab-code-" + uuid4().hex
    command = podman_command(settings, name)
    image_position = command.index(settings.image_id)
    command = command[: image_position + 1] + ["-I", "-u", "-c", source]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=worker_environment(),
            check=False,
        )
    finally:
        subprocess.run(
            [settings.podman_path, "rm", "--force", "--ignore", name],
            capture_output=True,
            timeout=10,
            env=worker_environment(),
            check=True,
        )


def checked_probe(settings, source, expected="DENIED"):
    result = probe(settings, source)
    if result.returncode or result.stdout.strip() != expected:
        raise RuntimeError(
            f"Probe did not establish {expected}: exit={result.returncode}, "
            f"stdout={result.stdout[:300]!r}, stderr={result.stderr[:300]!r}"
        )


def check_network(settings):
    checked_probe(
        settings,
        "import socket\n"
        "s=socket.socket(); s.settimeout(2)\n"
        "try: s.connect(('1.1.1.1',53)); print('CONNECTED')\n"
        "except OSError: print('DENIED')\n",
    )


def check_host_files(settings):
    with tempfile.NamedTemporaryFile(dir=ROOT / ".runtime", prefix="host-canary-", delete=True) as file:
        file.write(b"fixture-only-canary")
        file.flush()
        checked_probe(
            settings,
            "import os\n"
            f"print('EXPOSED' if os.path.exists({file.name!r}) else 'DENIED')\n",
        )


def check_credentials(settings):
    checked_probe(
        settings,
        "import os\n"
        "keys={'GITHUB_TOKEN','GH_TOKEN','HF_TOKEN','GOOGLE_API_KEY','GROQ_API_KEY'}\n"
        "print('EXPOSED' if keys.intersection(os.environ) else 'DENIED')\n",
    )


def check_sockets(settings):
    checked_probe(
        settings,
        "import os\n"
        "paths=['/var/run/docker.sock','/run/podman/podman.sock','/run/docker.sock']\n"
        "print('EXPOSED' if any(os.path.exists(p) for p in paths) else 'DENIED')\n",
    )


def check_process_limit(settings):
    checked_probe(
        settings,
        "import os,time,signal\n"
        "children=[]; denied=False\n"
        "try:\n"
        " for i in range(40):\n"
        "  try: pid=os.fork()\n"
        "  except OSError: denied=True; break\n"
        "  if pid==0: time.sleep(8); os._exit(0)\n"
        "  children.append(pid)\n"
        "finally:\n"
        " for pid in children:\n"
        "  try: os.kill(pid,signal.SIGKILL); os.waitpid(pid,0)\n"
        "  except OSError: pass\n"
        "print('DENIED' if denied and len(children)<32 else 'UNLIMITED')\n",
    )


def check_memory_limit(settings):
    result = probe(
        settings,
        "try:\n"
        " x=bytearray(384*1024*1024); print('UNLIMITED')\n"
        "except MemoryError: print('DENIED')\n",
        timeout=25,
    )
    if result.stdout.strip() == "DENIED" or result.returncode == 137:
        return
    raise RuntimeError(
        f"Memory ceiling was not observed: exit={result.returncode}, output={result.stdout[:200]!r}"
    )


def check_cpu_limit(settings):
    checked_probe(
        settings,
        "from pathlib import Path\n"
        "value=Path('/sys/fs/cgroup/cpu.max').read_text().split()\n"
        "quota,period=value\n"
        "print('DENIED' if quota!='max' and int(quota)<=int(period)//2 else 'UNLIMITED')\n",
    )


def no_action_bridge():
    return SimpleNamespace(
        stopped=False,
        broker=SimpleNamespace(finished=False),
        limits=AgentLimits(),
        memory=SimpleNamespace(state={"observation_id": str(uuid4()), "candidates": []}),
        call=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("Unexpected trusted tool dispatch")
        ),
    )


def check_wall_time(settings):
    limited = CodeWorkerSettings(settings.image_id, settings.podman_path, timeout_seconds=5)
    try:
        execute_cell("while True: pass", {}, no_action_bridge(), limited)
    except PlannerStopped as exc:
        if exc.category == "code_runtime_limit":
            return
        raise
    raise RuntimeError("Infinite code cell did not reach the wall-time ceiling")


def check_output_limit(settings):
    bridge = no_action_bridge()
    code = "result=tool({'kind':'click','noise':'x'*140000})"
    try:
        execute_cell(code, {}, bridge, settings)
    except PlannerStopped as exc:
        if exc.category == "code_output_limit":
            return
        raise
    raise RuntimeError("Oversized worker frame was accepted")


def check_unapproved_code(settings):
    try:
        execute_cell("import os", {}, no_action_bridge(), settings)
    except PlannerStopped as exc:
        if exc.category == "code_execution_error":
            return
        raise
    raise RuntimeError("Unapproved import executed inside the worker")


async def check_ipc(settings, *, stale):
    current = uuid4()
    broker = SimpleNamespace(closed=False, finished=False, current=SimpleNamespace(id=current))
    memory = SimpleNamespace(state={"candidates": []})
    bridge = ToolBridge(broker, memory, AgentLimits(), asyncio.get_running_loop())
    observation_id = str(uuid4() if stale else current)
    code = (
        "result=tool({'kind':'click','observation_id':"
        + repr(observation_id)
        + ",'candidate_id':9999})"
    )
    try:
        await asyncio.to_thread(execute_cell, code, {}, bridge, settings)
    except PlannerStopped as exc:
        if exc.category == "grounding_failure":
            return
        raise
    raise RuntimeError("Unperceived or stale worker action was accepted")


def check_cleanup(settings):
    result = subprocess.run(
        [settings.podman_path, "ps", "-a", "--filter", "name=frictionlab-code-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=10,
        env=worker_environment(),
        check=True,
    )
    if result.stdout.strip():
        raise RuntimeError("Disposable code-worker containers remain after the batch")


def check_sentinel(settings):
    state = {"requests": 0, "value": "unchanged"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"] += 1
            state["value"] = "changed"
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        checked_probe(
            settings,
            "import urllib.request\n"
            f"try: urllib.request.urlopen('http://127.0.0.1:{port}/',timeout=2); print('EXPOSED')\n"
            "except Exception: print('DENIED')\n",
        )
        if state != {"requests": 0, "value": "unchanged"}:
            raise RuntimeError("Worker reached or altered the host sentinel")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def write_review(results, settings):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 3 OCI worker boundary review",
        "",
        f"Host: `{platform.node()}`; image ID: `{settings.image_id}`.",
        "",
        "This batch uses a disposable local container and owned host canary/sentinel only.",
        "No staging or production site is contacted. Failed checks are retained below.",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, result in results.items():
        detail = result["detail"].replace("|", "\\|").replace("\n", " ")[:400]
        lines.append(f"| `{name}` | {result['status']} | {detail} |")
    lines.extend(
        [
            "",
            "Passing this boundary is necessary for the fixture CodeAgent journey; it does not authorize external replicas.",
        ]
    )
    (OUTPUT / "worker-boundary-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUTPUT / "worker-boundary-results.json").write_text(
        json.dumps({"host": platform.node(), "image_id": settings.image_id, "checks": results}, indent=2)
        + "\n",
        encoding="utf-8",
    )


async def main():
    settings = local_settings()
    (ROOT / ".runtime").mkdir(parents=True, exist_ok=True)
    try:
        inspect_image(settings)
    except Exception as exc:
        write_review(
            {"image_preflight": {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}},
            settings,
        )
        raise
    checks = {
        "network_denied": check_network,
        "host_files_denied": check_host_files,
        "host_credentials_absent": check_credentials,
        "control_sockets_absent": check_sockets,
        "process_limit": check_process_limit,
        "memory_limit": check_memory_limit,
        "cpu_limit": check_cpu_limit,
        "wall_time_limit": check_wall_time,
        "output_limit": check_output_limit,
        "unapproved_code_rejected": check_unapproved_code,
        "cleanup_verified": check_cleanup,
        "sentinel_untouched": check_sentinel,
    }
    results = {}
    for name, check in checks.items():
        try:
            check(settings)
            results[name] = {"status": "passed", "detail": "Observed expected isolated behavior."}
        except Exception as exc:  # noqa: BLE001 -- preserve every failed boundary observation
            results[name] = {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
    for name, stale in (("stale_ipc_rejected", True), ("forged_ipc_rejected", False)):
        try:
            await check_ipc(settings, stale=stale)
            results[name] = {"status": "passed", "detail": "Trusted broker rejected the worker request."}
        except Exception as exc:  # noqa: BLE001 -- preserve every failed boundary observation
            results[name] = {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        check_cleanup(settings)
    except Exception as exc:  # noqa: BLE001 -- final cleanup check is authoritative
        results["cleanup_verified"] = {"status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
    write_review(results, settings)
    passed = {name for name, result in results.items() if result["status"] == "passed"}
    if passed != REQUIRED_CHECKS:
        raise SystemExit("Worker boundary gate failed; review saved evidence. Code mode remains disabled.")
    runtime = await asyncio.to_thread(
        subprocess.run,
        [settings.podman_path, "version", "--format", "{{.Client.Version}}"],
        capture_output=True,
        text=True,
        timeout=10,
        env=worker_environment(),
        check=True,
    )
    GATE_PATH.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "passed",
                "host": platform.node(),
                "image_id": settings.image_id,
                "podman_version": runtime.stdout.strip(),
                "passed_checks": sorted(passed),
                "failed_checks": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Worker boundary gate passed for this host and image ID.")


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Run the real worker boundary batch on a Linux host.")
    asyncio.run(main())
