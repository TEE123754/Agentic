# Phase 3 generated-code worker: construction checkpoint

The supported autonomous product path is still the reviewed `typed_tools` mode. `isolated_code` remains blocked before starting a browser or model. The new OCI worker files are preparation for that path, **not evidence that arbitrary generated Python is safe to enable**.

## Built boundary

- `frictionlab/planning/container_worker.py` receives one bounded code cell and a filtered observation over stdin, runs it in a fresh process, and exposes only a `tool(action)` function for browser operations. It rejects direct imports, attribute access, and unapproved calls as defense in depth; Python itself is not a sandbox.
- `frictionlab/planning/code_worker.py` constructs a rootless Podman invocation with an immutable local image ID, no network, no host mounts, read-only root, no Linux capabilities, no new privileges, private IPC/PID/UTS, an unprivileged UID, 16 MiB temporary scratch, and CPU, memory, process, wall-time, input, and output ceilings. It verifies the local image ID and rootless runtime before launch.
- The only action channel is bounded newline JSON over the worker's stdin/stdout. The host treats frames as untrusted and sends each proposed action through the existing `ToolBridge`, which rechecks current observation, candidate, action contract, independent finish, quotas, and browser protection policy. No Playwright handle, application credential, provider token, host socket, or target URL is provided to the worker.
- The launcher kills a timed-out process and attempts forced removal by its random container name. Cleanup failure is an infrastructure failure, never a UX diagnosis.
- `Containerfile.code-worker` copies only the worker module into an operator-supplied pinned base image. The resulting image must itself be pinned by its local SHA-256 image ID. No registry pull occurs when running cells.
- `.containerignore` limits the build context to this one module and its Containerfile, excluding models, reports, credentials, and local environments from the image build transfer.
- `frictionlab/planning/code_agent.py` connects `smolagents.CodeAgent` to the disposable worker. A local Qwen decision is a bounded Python cell; the agent cannot send Python variables or unreviewed tools into the worker. The existing persona memory, model token/step ceilings, broker checks, independent completion, and terminal report path remain authoritative. The runner checks a host/image-specific boundary record **before** starting a browser or model. No such record is present on this host, so this branch has not executed.

## Remaining gate before enabling generated Python

1. Provision a supported **free, rootless Podman** runtime on a host that can run Linux containers. This Windows machine currently has no Podman, Docker, or installed WSL. Installing WSL/Podman changes the host and may require administrator rights and restart; this task has not done so.
2. Build a worker image from a reviewed, digest-pinned open-source Python base; record the base provenance, final image ID, Podman version, rootless status, kernel/runtime configuration, and host identifier. The [GitHub-built uv Python 3.12 Alpine image](https://github.com/astral-sh/uv/blob/main/docs/guides/integration/docker.md) is one free GHCR source; resolve and record its actual digest before using it as `BASE_IMAGE`. [Podman's run reference](https://docs.podman.io/en/latest/markdown/podman-run.1.html) defines the network, root filesystem, resource, and no-pull flags. No paid account is required.

   From the project root on that host, the build shape is `podman build -f Containerfile.code-worker --build-arg BASE_IMAGE=ghcr.io/astral-sh/uv@sha256:<reviewed-digest> --iidfile artifacts/phase3/worker-image-id.txt .`. Replace the placeholder with the verified digest; do not use a floating tag. The `.containerignore` must be applied, and the resulting image ID must match the acceptance record. This command has **not** been run on the current machine.
3. After runtime/image construction, run **one dedicated boundary acceptance batch** in that real runtime: process/file/network/IPC escape attempts; arbitrary imports and child processes; output and memory exhaustion; stale/forged tool requests; timeout and container cleanup; and preserved zero-request sentinel plus unchanged synthetic data. Keep every failed report. Only a passing batch for the exact runtime/image may create the host/image acceptance record that unlocks `isolated_code`.
4. Run at least one owned-fixture `CodeAgent` journey through the real worker and independently review its detailed terminal report. Record image ID, host, worker startup, tool calls, and actual generated-code execution. The typed-tools journeys need not be repeated.
5. Separately validate stronger browser isolation before accepting any user-supplied staging/replica URL. The worker boundary alone does not authorize external targets.

## Review of this checkpoint

Construction preceded the offline worker check batch. **Twenty new worker/adapter checks and two existing blocked-mode guards passed**; only affected checks were repeated after small source changes. Targeted Ruff checks pass. The checks cover the command's intended isolation flags/no host mounts, immutable image-ID rejection, invalid names, input limits before launch, absent-runtime fail-closed behavior, excluded API keys, oversized output rejection, direct unauthorized code syntax, host/image gate checks, and the CodeAgent adapter's tool/state restrictions. They do not execute generated Python or a container. The reviewed runner still rejects `isolated_code` before browser/model startup on this host.

| Review item | Evidence from this checkpoint | Still unverified |
|---|---|---|
| App protection | OCI command requests `--network=none`, no host mounts, no image pull; every worker action is sent to `ToolBridge`. Existing isolated-mode guards reject execution before browser/model startup without a gate. | Kernel enforcement under the actual host/runtime/image, sentinel counts during a real CodeAgent journey, and browser isolation for external replicas. |
| Code containment | Rootless check, read-only filesystem, non-root UID, dropped capabilities, private namespaces, bounded tmpfs, CPU/RAM/PID ceilings, and direct import/attribute/call rejection are in source. | Real escape attempts, resource exhaustion behavior, runtime flag support, and a clean container teardown on the target host. |
| IPC and reporting | Strict frame/input/output bounds, current-observation broker dispatch, host/image gate, and worker metadata are in source. | End-to-end CodeAgent tool protocol, detailed terminal report with an actual generated cell, and exact image/runtime provenance. |
| Build inputs | Only the worker file is selected in `.containerignore`; `Containerfile.code-worker` has no application credentials or model weights. | The chosen digest-pinned base, build-context behavior, resulting image ID, and image inspection. |

No code-mode UX result or isolation success is claimed. Existing typed-tools Phase 3 reports remain the only executed autonomous evidence. No deployed website was contacted during this checkpoint; only local source checks ran.

The product execution path remains closed by the missing host/image acceptance record. Phase 3 remains partial; no verified sandbox or external-target safety claim is made.
