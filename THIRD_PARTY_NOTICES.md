# Third-party notices and distribution scope

FrictionLab project code is MIT licensed. Third-party software, model weights and datasets retain their licenses; the project MIT license does not relicense them.

## Bundled component

The unchanged `vendor/axe-core/axe.min.js` is axe-core 4.13.0 under MPL-2.0. Its original `LICENSE` and `LICENSE-3RD-PARTY.txt` are retained in every archive. Corresponding upstream source is available at [dequelabs/axe-core v4.13.0](https://github.com/dequelabs/axe-core/tree/v4.13.0). Version and integrity are pinned in `configs/axe-manifest.json`. No modifications are made to this bundle.

## Installed dependencies

Playwright Python and browser-use (Apache-2.0 and MIT respectively), smolagents (Apache-2.0), DuckDB (MIT), httpx (BSD-3-Clause), Pydantic (MIT), FastAPI (MIT), uvicorn (BSD-3-Clause), OpenTelemetry SDK (Apache-2.0), psutil (BSD-3-Clause), optional Streamlit (Apache-2.0) and Plotly (MIT) are installed from pinned dependencies rather than vendored in our wheel. Their installed distribution metadata/notices remain with them. Hatchling (MIT) is a build dependency only. See `uv.lock` and the local `docs/dependency-manifest.json` inventory; that earlier inventory is not a legal clearance for every future version.

## Separately downloaded resources

llama.cpp (MIT) and Qwen3-4B-GGUF (Apache-2.0) are optional downloads, never included in FrictionLab wheels or source archives. Preserve their notices when redistributing them separately. Optional SmolVLM weights and vision packages are neither bundled nor verified in this phase. Mind2Web's [dataset card](https://huggingface.co/datasets/osunlp/Mind2Web) states CC-BY-4.0; its pinned data is an optional evaluation input, not bundled here. Keep attribution and source revision in any evaluation publication. Do not assume captured third-party website content is relicensed by the dataset or this project.

Groq and Gemini are optional remote services subject to their own terms and free-account eligibility. API transports use our existing httpx dependency; no hosted browser, gateway subscription or paid provider SDK is required. Selecting a model that is unavailable in a free account pauses the run; the tool cannot independently certify the user's billing configuration.

## Release boundary

Wheel/source delivery includes project code, synthetic fixtures, configuration, local report viewer/site, documentation and the licensed axe bundle. It excludes keys, `.env` files, local inference configuration, run evidence, downloaded weights/runtime, virtual environments and Git history. Public visibility/package-index publication is a separate release action. Dependency license updates and optional redistribution still need review at each release.

## Local desktop and credential storage

- [jaraco/keyring](https://github.com/jaraco/keyring): MIT; the tool selects only core native OS credential backends. No plaintext fallback.
- [PyInstaller](https://github.com/pyinstaller/pyinstaller): GPL with the stated distribution/bootloader exception; some components retain their separately stated licenses. A frozen FrictionLab app is distributed under the project's MIT license with third-party notices retained. The desktop archive includes available dependency LICENSE/COPYING files and build-environment metadata.
- Tkinter/Tcl/Tk: Python standard GUI bindings and Tcl/Tk libraries retain their respective PSF/Tcl/Tk notices; PyInstaller collects the required runtime components.

The frozen launcher excludes local model runtimes and development dashboards. It includes Playwright's driver resources and bundled axe-core; Chrome/Edge is supplied by the operator and is not redistributed in this archive. API keys, models, uploaded source and personal reports are never part of the desktop build.
