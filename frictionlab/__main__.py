"""Single documented entry point: local serve or offline configuration validation."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from frictionlab.configuration import (
    CONFIG_DIRECTORY,
    PACKAGE_DIRECTORY,
    ROOT,
    ConfigurationRejected,
    read_json,
    resolve_run,
)
from frictionlab.reporting import blocked_report, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="frictionlab")
    parser.add_argument("--version", action="version", version="FrictionLab 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a local workspace without downloads")
    init.add_argument("directory", type=Path)
    diagnostic = commands.add_parser(
        "doctor", help="Offline setup checks; no browser or model launch"
    )
    diagnostic.add_argument("--inference-config", type=Path)
    cohort = commands.add_parser(
        "cohort", help="Run an owned-fixture cohort and generate a detailed audit"
    )
    cohort.add_argument("--config", type=Path, default=CONFIG_DIRECTORY / "run.quickstart.json")
    cohort.add_argument(
        "--variant",
        choices=(
            "healthy",
            "dead_button",
            "generic_validation",
            "delayed_feedback",
            "hidden_shipping",
            "focus_trap",
        ),
        default="healthy",
    )
    serve = commands.add_parser("serve", help="Serve the bundled fixture and local cohort API")
    serve.add_argument("--port", type=int, default=8765)
    dashboard = commands.add_parser("dashboard", help="Open the local Streamlit command center")
    dashboard.add_argument("--port", type=int, default=8501)
    static_export = commands.add_parser(
        "export-static", help="Export a saved audit as a self-contained offline viewer"
    )
    static_export.add_argument("run_id")
    static_export.add_argument("--root", type=Path, default=ROOT / "artifacts" / "phase5")
    static_export.add_argument("--output", type=Path, required=True)
    static_export.add_argument("--public-fixture", action="store_true")
    validate = commands.add_parser("validate", help="Review JSON configuration offline")
    validate.add_argument("path", type=Path)
    browser_demo = commands.add_parser(
        "browser-demo", help="Run a deterministic probe against a disposable bundled fixture"
    )
    browser_demo.add_argument(
        "--variant",
        choices=(
            "healthy",
            "generic_validation",
            "dead_button",
            "delayed_feedback",
            "hidden_shipping",
            "focus_trap",
        ),
        default="healthy",
    )
    browser_demo.add_argument(
        "--persona",
        choices=("impatient_mobile", "keyboard_low_vision", "enterprise_evaluator"),
        default="impatient_mobile",
    )
    for command_name in ("autonomous", "behavioral"):
        command = commands.add_parser(
            command_name,
            help="Run one local model-driven persona on an owned fixture"
            + (" with evidence-grounded patience" if command_name == "behavioral" else ""),
        )
        command.add_argument(
            "--persona",
            choices=("impatient_mobile", "keyboard_low_vision", "enterprise_evaluator"),
            default="impatient_mobile",
        )
        command.add_argument(
            "--journey",
            choices=("checkout_review", "delivery_information", "keyboard_checkout"),
            default="checkout_review",
        )
        command.add_argument(
            "--variant",
            choices=(
                "healthy",
                "generic_validation",
                "dead_button",
                "delayed_feedback",
                "hidden_shipping",
                "focus_trap",
            ),
            default="healthy",
        )
        command.add_argument(
            "--mode", choices=("typed_tools", "isolated_code"), default="typed_tools"
        )
        command.add_argument("--inference-config", type=Path)
    args = parser.parse_args(argv)
    if args.command == "init":
        from frictionlab.product import initialize

        try:
            print(json.dumps(initialize(args.directory), indent=2))
        except (OSError, ValueError):
            parser.error("Workspace initialization failed; choose a new writable directory")
        return 0
    if args.command == "doctor":
        from frictionlab.product import doctor

        result = doctor(args.inference_config)
        print(json.dumps(result, indent=2))
        return 0 if result["ready_for_audit"] else 2
    if args.command == "cohort":
        from uuid import uuid4

        from frictionlab.cohorts.coordinator import CohortCoordinator, CohortSettings

        async def run_cohort():
            payload = read_json(args.config)
            payload["id"] = str(uuid4())
            resolved = resolve_run(payload)
            coordinator = CohortCoordinator(settings=CohortSettings(workers=1))
            try:
                await coordinator.submit(resolved, variant=args.variant)
                await coordinator.wait(payload["id"])
                result = coordinator.status(payload["id"])
                print(
                    json.dumps(
                        {
                            "run_id": payload["id"],
                            "status": result,
                            "report_root": str(coordinator.root / "reports" / payload["id"]),
                        }
                    )
                )
                return 0 if result["run"]["status"] == "completed" else 1
            finally:
                await coordinator.close()

        try:
            return asyncio.run(run_cohort())
        except (ConfigurationRejected, ValueError):
            parser.error(
                "Cohort configuration rejected; use an owned fixture and documented limits"
            )
        return 0
    if args.command == "export-static":
        from frictionlab.sharing.bundle import export_bundle

        try:
            destination = export_bundle(
                args.root, args.run_id, args.output, public_fixture=args.public_fixture
            )
        except (ValueError, FileExistsError, OSError) as exc:
            parser.error(str(exc))
        print(
            json.dumps(
                {
                    "viewer": str(destination / "index.html"),
                    "bundle": str(destination / "bundle.json"),
                }
            )
        )
        return 0
    if args.command == "dashboard":
        if not 1024 <= args.port <= 65535:
            parser.error("Use an unprivileged dashboard port between 1024 and 65535")
        if importlib.util.find_spec("streamlit") is None:
            parser.error("Install the optional dashboard with `uv sync --extra dashboard`")
        path = PACKAGE_DIRECTORY / "dashboard" / "app.py"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(path),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(args.port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            env=environment,
        )
    if args.command in {"autonomous", "behavioral"}:
        from frictionlab.planning.runner import autonomous_cli

        return asyncio.run(
            autonomous_cli(
                args.persona,
                args.journey,
                args.variant,
                args.mode,
                behavioral=args.command == "behavioral",
                inference_path=args.inference_config,
            )
        )
    if args.command == "browser-demo":
        from frictionlab.browser.demo import demo

        return asyncio.run(demo(args.variant, args.persona))
    if args.command == "serve":
        if not 1024 <= args.port <= 65535:
            parser.error("Use an unprivileged port between 1024 and 65535")
        import uvicorn

        from frictionlab.api import create_app

        uvicorn.run(
            create_app(origin=f"http://127.0.0.1:{args.port}", enable_cohorts=True),
            host="127.0.0.1",
            port=args.port,
        )
        return 0
    try:
        resolved = resolve_run(read_json(args.path))
    except ConfigurationRejected as exc:
        report = blocked_report(str(exc))
        directory = write_report(report, ROOT / "artifacts" / "phase1" / "configuration")
        print(
            json.dumps(
                {
                    "valid": False,
                    "execution_enabled": False,
                    "diagnostics": exc.diagnostics,
                    "report_directory": str(directory),
                },
                indent=2,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "valid": True,
                "execution_enabled": False,
                "configuration_hash": resolved.configuration_hash,
                "requested_sessions": resolved.requested_sessions,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
