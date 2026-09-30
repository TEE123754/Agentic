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

from frictionlab.configuration import ROOT, ConfigurationRejected, read_json, resolve_run
from frictionlab.reporting import blocked_report, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m frictionlab")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Serve the bundled fixture and local cohort API")
    serve.add_argument("--port", type=int, default=8765)
    dashboard = commands.add_parser("dashboard", help="Open the local Streamlit command center")
    dashboard.add_argument("--port", type=int, default=8501)
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
    args = parser.parse_args(argv)
    if args.command == "dashboard":
        if not 1024 <= args.port <= 65535:
            parser.error("Use an unprivileged dashboard port between 1024 and 65535")
        if importlib.util.find_spec("streamlit") is None:
            parser.error("Install the optional dashboard with `uv sync --extra dashboard`")
        path = ROOT / "frictionlab" / "dashboard" / "app.py"
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
