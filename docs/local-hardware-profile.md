# Phase 0 hardware profile

Collected September 29, 2026. Raw inventory: `docs/hardware.json`.

| Item | Observed value |
|---|---|
| OS | Windows 11 Home Single Language, x64, build 10.0.26200 |
| RAM | 34,053,414,912 bytes, approximately 31.71 GiB |
| CPU | Intel Core i7-14700HX, 20 cores / 28 logical processors |
| GPU | NVIDIA GeForce RTX 5050 Laptop GPU |
| GPU memory | 8,151 MiB according to nvidia-smi; CIM's 32-bit AdapterRAM value is truncated |
| Initial free disk | Approximately 46.4 GiB on C: before runtime/model downloads |
| Python | Bundled CPython 3.12.14, project `.venv` |
| Package manager | uv 0.11.18 |
| Containers | Neither Podman nor Docker found on PATH |
| Existing Chrome | 153.0.8010.53 |
| Existing Edge | 154.0.4258.37 |

## Selected initial resource configuration

- CPU-only Qwen3-4B Q4_K_M, one shared llama.cpp process.
- 4,096-token context, at most 192 output tokens and one inference request at a time.
- Eight inference threads initially; measure rather than assume throughput.
- One browser session and an 8 GiB combined monitored process-memory budget.
- 180-second per-request timeout; 240-second model startup deadline.
- SmolVLM is an optional disabled path, using local files only. No vision quality claim is made without a measured run.

Playwright's dedicated Chromium download timed out repeatedly. The spike uses the installed Chrome executable with a fresh project-owned profile; it does not attach to the user's existing browser or read their cookies. Record the actual browser version in every validation report. A dedicated pinned browser binary remains desirable for future reproducibility.

The measured NVIDIA capacity could support a later GPU configuration, but Phase 0 intentionally avoids an unmeasured CUDA/model combination. No system-wide container installation, firewall change, or OS virtualization change has been performed.

