# Local website assessment workspace

FrictionLab runs on your computer and keeps reports there. The dashboard and native launcher share the same assessment engine. Neither installs models nor downloads a browser automatically. AI advice is optional and requires your own eligible Groq or Gemini key and an explicitly selected model.

## Quick start

From this repository, with Python 3.12 and uv installed:

```sh
uv sync --locked
uv run frictionlab start
```

The CLI prints a `http://127.0.0.1:<port>` address and opens the dashboard. A free port is selected automatically. Use `--no-open` or `--port 9080` when desired. Ctrl+C stops the service. Reports default to `~/FrictionLab/assessments`; `--workspace PATH` changes the local storage folder.

Paste a URL, choose the evidence source, select individual categories or all six, and start. Progress, cancellation and saved reports appear in the dashboard. Choose JSON, Markdown, HTML or ZIP to export. ZIP includes report files and available viewport screenshots; uploaded source and credentials are excluded.

For desktop mode:

```sh
uv run frictionlab desktop
```

The native Tkinter window has masked key setup and start/open/stop controls. Assessments appear in its localhost dashboard. Tkinter is included in normal Python Windows/macOS installations; Linux may need its distribution's `python3-tk` package. The Windows build workflow produces a portable ZIP, which you extract and open `FrictionLab.exe`. It does not include Chrome, models or API keys. macOS/Linux frozen downloads are not yet qualified. Source desktop mode uses the same engine on those platforms.

## Your key

Connect the key in the dashboard or native window. The default keeps it in this process's memory until exit. Optional “Remember” uses Windows Credential Manager, macOS Keychain or Linux Secret Service through the core native keyring backend. If native storage is unavailable, remembering is disabled; no plaintext fallback is allowed. Delete remembered credentials in your OS credential manager under the FrictionLab service when needed. Environment keys override saved keys.

The CLI can use a masked prompt and native storage:

```sh
uv run frictionlab configure --provider groq --model YOUR_AVAILABLE_MODEL --share-findings --free-tier-confirmed
uv run frictionlab start
```

Add `--session-only` to configure and immediately start the dashboard in the same process. Never place a key in a command argument, source file or committed configuration. Nonsecret app settings contain provider, model and opt-ins. The UI never reads a key back. Provider acknowledgements mean you verified account eligibility; they do not guarantee a free API model or prevent your own account's billing outside this tool. One bounded advice request, no retries and no paid fallback are used per assessment. Provider outages/quota failures leave measured findings intact and mark AI review incomplete. No real-key call is made by automated acceptance.

## Evidence modes and production protection

| Mode | Contact with submitted website | Supported evidence | Limitations |
|---|---|---|---|
| URL only | None; no DNS resolution | URL syntax and HTTPS scheme | Cannot inspect content, server TLS, flows or performance. Most checks skipped. |
| Uploaded HTML / ZIP | None | Static structure, axe checks, three viewports, HTML size | Application scripts, forms, frames, workers and external requests disabled. Missing assets lower confidence. |
| Approved public capture | At most one GET | Public HTML and selected original response headers, then offline checks | Even GET can modify logs/state. No redirects, authentication or subresources. Requires permission for the read-only endpoint. |
| Existing owned-fixture cohort CLI | Bundled disposable local fixtures only | Autonomous synthetic journeys, patience/friction, replay/comparison | Not available for arbitrary URLs. Does not predict real user churn. |

**Browser isolation alone does not prevent production side effects.** Cookies, form submissions, API calls, tracking endpoints, GET handlers and connected services can change production even from an isolated browser. This dashboard never navigates its inspection browser to the submitted URL; it renders only allowlisted snapshot resources on a synthetic origin, with application JavaScript and network access disabled. The JavaScript engine is available for trusted axe-core evaluation and its callbacks. Uploaded application scripts are removed and blocked by restrictive CSP; enabling trusted tool code is not permission to run uploaded application code. Capture is a separate explicitly approved acquisition, validates all resolved IP addresses and pins one public address; it blocks credentials, query parameters, nonstandard ports and redirects. This protection is not permission to contact an endpoint with unknown side effects: use a snapshot for guaranteed zero target contact.

An uploaded ZIP needs root `index.html` with relative CSS/images/fonts. Limits: 10 MB ZIP, 256 entries, 20 MB expansion, 2 MB per file; traversal, symlinks and compression bombs are rejected. Do not upload sensitive content. Rendered screenshot pixels may still expose supplied content and need human review before sharing.

## Category coverage

| Category | Static/URL evidence | Needs additional access |
|---|---|---|
| Functionality | Declared link destinations (heuristic) | Full flows, form validation, API/integration outcomes: verified isolated application/backend, synthetic accounts and sandboxed integrations. |
| Usability | Page title and primary heading | Cognitive journeys, abandonment and interaction friction: isolated interactive replica; human calibration for churn claims. |
| Accessibility | Alt/label declarations, offline axe | Keyboard focus flows, screen readers, meaningful alt text and WCAG conclusions: interactive replica plus assistive/manual review. |
| Responsiveness | Viewport declaration and horizontal overflow at 360/768/1440px | Dynamic layout/menu interactions and faithful rendering when assets are missing: complete local replica. |
| Performance | HTML size budget | Network/load benchmarks, LCP/CLS/INP and Core Web Vitals: controlled replica with real assets and a benchmark. Offline timing is not reported as production performance. |
| Security | HTTPS URL scheme; CSP/nosniff presence on approved capture | TLS deployment validation, auth/authorization, dependency/source review and exploit testing: source/access and explicitly authorized isolated security environment. No active attack runs here. |

Unsupported checks are **skipped** with the missing prerequisite. Attempted checks that fail to execute are **incomplete**. Failed checks have severity, observations, reproduction and recommendations. Scores are weighted pass fractions among executed checks, accompanied by coverage and confidence; unassessed categories show no score. They are not release approval, human usability prediction, WCAG certification or security certification.

The loopback API rejects foreign Host/Origin headers and requires a per-process dashboard token. It binds only 127.0.0.1, disables API documentation/CORS and serves local assets with a restrictive CSP. This is a single-user local tool; malware or other processes acting as your OS user are outside its trust boundary.

## Browser and shutdown

Install Chrome/Edge normally or explicitly run `uv run playwright install chromium` if you want the separate Playwright browser download. Set `FRICTIONLAB_BROWSER_PATH` to an existing executable if discovery misses it. Without a browser, static checks still run and browser checks are incomplete. No model is needed for offline snapshot checks. Cancellation stops queued work and halts between bounded stages; a provider request or capture read already in flight may take its timeout to return. Interrupted runs retain partial reports after restart; resume by creating a new assessment.

## Technology and licensing

Python 3.12; FastAPI/uvicorn/Pydantic; vanilla local HTML/CSS/JavaScript; Playwright Chromium and bundled axe-core; Tkinter/ttk; [keyring](https://github.com/jaraco/keyring); existing bounded Groq/Gemini transports; JSON report storage with atomic writes. Existing cohort telemetry remains DuckDB/OpenTelemetry. [PyInstaller](https://github.com/pyinstaller/pyinstaller) packages the Windows launcher on a disposable GitHub Actions runner, not the operator laptop. Project MIT, keyring MIT; PyInstaller GPL with its distribution/bootloader exception. Bundled third-party notices accompany the desktop download. No subscription, remote database, hosted dashboard or infrastructure payment is required. AI inference sends the opted-in findings to the chosen provider and is not fully offline.

Validation results and remaining platform/provider qualification are recorded in IMPLEMENTATION_PLAN.md and docs/phase-status.md. The GitHub Release is a development download with SHA256SUMS; it is not a signed binary or a claim of macOS/Linux frozen support.
