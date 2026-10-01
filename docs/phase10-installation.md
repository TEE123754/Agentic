# Local installation and BYOK operator guide

FrictionLab 0.1.0 is a local Python tool. Install Python 3.12 and uv. Browser automation requires your own local Chromium/Chrome executable; inference uses either your own eligible free-account API key or separately downloaded local weights. No browser/model is downloaded during init, doctor, report export or audit execution.

## Source installation

```sh
git clone https://github.com/TEE123754/Agentic.git
cd Agentic
uv sync --locked --extra dashboard
uv run frictionlab --help
uv run frictionlab init ../frictionlab-workspace
```

Use a new empty directory. Init copies non-secret configuration, site, synthetic sample and guides; it never overwrites an existing workspace. Set `FRICTIONLAB_HOME` to the absolute path of that workspace. Source checkout mode otherwise uses the checkout root; installed wheel mode otherwise uses your current directory. All writable artifacts, database files and browser profiles stay under that workspace, never under site-packages.

## Downloaded archive installation

The Phase 10 GitHub Actions artifact contains a wheel, source archive and `SHA256SUMS`. Download/extract it from the completed workflow using an account with repository access. These are development build downloads, not a public package-index release.

```sh
uv venv --python 3.12
uv pip install --python .venv/bin/python ./frictionlab-0.1.0-py3-none-any.whl
.venv/bin/frictionlab init ./workspace
```

On Windows use `.venv\Scripts\python.exe` and `.venv\Scripts\frictionlab.exe`. Installing the dashboard extra from the wheel uses `uv pip install --python .venv/bin/python './frictionlab-0.1.0-py3-none-any.whl[dashboard]'`. The source archive includes `uv.lock` for reproducible dependency installation; a wheel-only installation resolves its declared dependency constraints unless you also supply the source lock. No model weights or run evidence are in either archive. Public GitHub Releases/PyPI publication and repository visibility remain separate release actions.

## Resource-light BYOK setup

PowerShell:

```powershell
$env:FRICTIONLAB_HOME = 'C:\path\to\workspace'
$env:FRICTIONLAB_BROWSER_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:GROQ_API_KEY = 'your-own-key'
```

Linux/macOS shell:

```sh
export FRICTIONLAB_HOME="$PWD/workspace"
export FRICTIONLAB_BROWSER_PATH=/usr/bin/google-chrome
export GROQ_API_KEY='your-own-key'
```

Set secrets only in your own terminal or secret manager. FrictionLab does not read `.env`, accept keys on the CLI or save them to configuration. Never paste a real key into a GitHub issue, static site or report. `doctor` reports presence only and makes no API request.

Edit `frictionlab.local.json` inside your workspace:

```json
{
  "provider": "groq",
  "model": "openai/gpt-oss-20b",
  "allow_remote": true,
  "share_sanitized_state": true,
  "free_tier_confirmed": true,
  "max_requests": 24,
  "max_tokens": 180000,
  "max_input_bytes": 20000,
  "max_runtime_seconds": 240,
  "request_timeout_seconds": 30,
  "max_retries": 0,
  "fallback": "pause",
  "paid_fallback": false
}
```

For Gemini, use `provider: "gemini"`, an eligible model such as `gemini-2.5-flash-lite`, and `GEMINI_API_KEY` instead. Check your account's free eligibility before opting in. As checked October 2, 2026, [Groq's free-plan limits](https://console.groq.com/docs/rate-limits) list GPT-OSS models and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) lists a free tier for Flash-Lite. Availability, account/region eligibility and quotas can change; these IDs are examples, not baked-in choices or live-validated recommendations. The original Llama 3.3/Gemini 2.0 assumptions are not defaults.

The transports use documented [Groq OpenAI compatibility](https://console.groq.com/docs/openai) and [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai) with fixed HTTPS endpoints, no redirects or environment proxy inheritance. Currently they send only bounded sanitized semantic state, persona prompts and action schema. Full DOM, screenshots, keys, browser handles and raw traces are not inference inputs. The selected provider receives these inputs; Gemini free-tier data handling is described on its pricing page. Fully offline inference requires local weights and `provider: "local"`.

There is no FrictionLab billing, automatic upgrade or paid fallback. `free_tier_confirmed` is your acknowledgement, not an API-verified account billing status. Use a free-only account/project without paid billing. The tool cannot undo provider charges on an already-paid account. Request/token/runtime/retry ceilings are local safeguards; tokens are reserved conservatively using UTF-8 byte counts plus framing/output allowance and checked against reported usage. Missing usage or unexpectedly high usage pauses execution. Models that cannot produce a valid bounded decision stop with an infrastructure result; live model quality remains unverified until an opted-in smoke/behavioral run.

## Run and inspect

```sh
frictionlab doctor
frictionlab cohort --variant dead_button
# Or one persona, with the same configured inference backend:
frictionlab behavioral --persona impatient_mobile --journey checkout_review --variant dead_button
```

Use `uv run frictionlab` in a source checkout. The cohort command defaults to one profile, one journey, one worker; provider budget and deadline are shared across the cohort. Missing key is checked before browser navigation. A 429 or exhausted quota pauses; unavailable fallback never triggers a large local download. There is no automatic provider switch. Reports record requested/actual model identity and retries. Strict comparisons reject mixed/unverified identities. Provider failures are excluded from UX abandonment.

For the dashboard, start `frictionlab serve` and `frictionlab dashboard` in separate terminals. Both bind loopback. `--inference-config PATH` is available for single-persona commands and doctor; cohort/API use the workspace's `frictionlab.local.json` so the shared budget has one declared configuration.

Terminal cohort audits are under `artifacts/phase5/reports/RUN_UUID/revisions/`; session evidence is under `artifacts/phase5/runs/`. Export with `frictionlab export-static RUN_UUID --output NEW_DIRECTORY`. Opening reports stays offline. Local-model setup remains available through the source archive's explicit `scripts/setup_resources.py --download` step; verify its pinned paths and hardware guide before downloading several GB. No cloud key is needed for local inference.

## Stop and cleanup

Use cancellation in the local dashboard, or Ctrl+C in the cohort terminal. Owned browser/model processes are closed and a factual terminal/partial report is retained. Stop API/dashboard terminals with Ctrl+C. After stopping, you may remove selected `artifacts/` run directories under your workspace; retain reports you need and do not remove evidence while a run/review is active. Remove the dedicated workspace/virtual environment to uninstall workspace data and dependencies; optional weights stay in that workspace. No cleanup touches a deployed product.

Current supported targets remain bundled disposable fixtures. External staging/deployed URLs stay blocked until separate replica isolation is proven. No telemetry/report upload is enabled. GitHub Actions build/validation is an optional development task, not hosted production execution.
