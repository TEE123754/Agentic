"""A host/image-specific boundary record is required before CodeAgent startup."""

import json
import platform

from frictionlab.configuration import ROOT
from frictionlab.planning.code_worker import inspect_image, local_settings
from frictionlab.planning.contracts import PlannerStopped

GATE_PATH = ROOT / "artifacts" / "phase3" / "worker-boundary-gate.json"
REQUIRED_CHECKS = frozenset(
    {
        "network_denied",
        "host_files_denied",
        "host_credentials_absent",
        "control_sockets_absent",
        "process_limit",
        "memory_limit",
        "cpu_limit",
        "wall_time_limit",
        "output_limit",
        "unapproved_code_rejected",
        "stale_ipc_rejected",
        "forged_ipc_rejected",
        "cleanup_verified",
        "sentinel_untouched",
    }
)


def require_worker_gate():
    if not GATE_PATH.is_file():
        raise PlannerStopped(
            "code_isolation_unavailable",
            "Generated Python remains disabled: no host/image boundary acceptance record exists.",
        )
    try:
        gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(gate, dict):
            raise TypeError("gate is not an object")
        if (
            gate.get("version") != 1
            or gate.get("status") != "passed"
            or gate.get("host") != platform.node()
            or not isinstance(gate.get("image_id"), str)
            or not isinstance(gate.get("passed_checks"), list)
            or set(gate.get("passed_checks", [])) < REQUIRED_CHECKS
            or gate.get("failed_checks")
        ):
            raise ValueError("gate is incomplete or belongs to another host")
        settings = local_settings(gate.get("image_id"))
        inspect_image(settings)
        return settings
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PlannerStopped(
            "code_isolation_unavailable",
            "Generated Python remains disabled: worker boundary record is invalid.",
        ) from exc
