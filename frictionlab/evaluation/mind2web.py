"""Pinned, split-aware Mind2Web projection and offline action scoring.

The protected test archive is never bundled, downloaded implicitly, or exported.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

DATASET = "osunlp/Mind2Web"
REVISION = "17ece8eb89862368edc0cc806acee6fca5163474"
TRAIN_SMOKE = "data/train/train_10.json"
TRAIN_SMOKE_SHA256 = "182542d7947b3fa9e90fc57a3d82d4d8f2997ca5a06664217720d7a78a956e33"
TEST_ARCHIVE_SHA256 = "8f5fbe72afab942fe97cdf7fb397e179885d89b5c16862288e9a14bc6d41ca89"
SPLITS = {"train", "test_task", "test_website", "test_domain"}
TOKENS = re.compile(r"[a-z0-9]+")


def load_actions(path: Path, *, split: str, sha256: str, max_tasks: int = 25):
    """Read an explicitly supplied official JSON shard, never a URL or pickle."""
    path = Path(path)
    if split not in SPLITS or not 1 <= max_tasks <= 1009:
        raise ValueError("Unknown Mind2Web split or task ceiling")
    if path.name != f"{split}_{path.stem.rsplit('_', 1)[-1]}.json" or path.parent.name != split:
        raise ValueError("Mind2Web file must be inside its declared split directory")
    if not path.is_file() or path.stat().st_size > 800 * 1024 * 1024:
        raise ValueError("Mind2Web shard is absent or exceeds the file ceiling")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != sha256:
        raise ValueError("Mind2Web shard checksum does not match the pinned manifest")
    tasks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise TypeError("Mind2Web shard must contain a JSON task array")
    selected = []
    for task in tasks[:max_tasks]:
        if not isinstance(task, dict) or not task.get("annotation_id"):
            raise ValueError("Mind2Web task shape is invalid")
        actions = []
        for action in task.get("actions", []):
            if not isinstance(action, dict) or not action.get("action_uid"):
                raise ValueError("Mind2Web action shape is invalid")
            operation = action.get("operation") or {}
            positives = [str(item["backend_node_id"]) for item in action.get("pos_candidates", [])]
            candidates = []
            for candidate in action.get("pos_candidates", []) + action.get("neg_candidates", []):
                attributes = candidate.get("attributes", "{}")
                if isinstance(attributes, str):
                    try:
                        attributes = json.loads(attributes)
                    except json.JSONDecodeError:
                        attributes = {}
                candidates.append(
                    {
                        "id": str(candidate["backend_node_id"]),
                        "tag": str(candidate.get("tag", "")),
                        "attributes": attributes if isinstance(attributes, dict) else {},
                    }
                )
            actions.append(
                {
                    "action_uid": str(action["action_uid"]),
                    "operation": str(operation.get("op", "")).upper(),
                    "value": str(operation.get("value", "")),
                    "positive_ids": positives,
                    "candidates": candidates,
                }
            )
        selected.append(
            {
                "annotation_id": str(task["annotation_id"]),
                "task": str(task.get("confirmed_task", "")),
                "actions": actions,
            }
        )
    return selected


def lexical_reference(tasks):
    """Untuned diagnostic baseline, deliberately distinct from the browser planner."""
    predictions = {}
    for task in tasks:
        words = set(TOKENS.findall(task["task"].lower()))
        for action in task["actions"]:
            ranked = []
            for candidate in action["candidates"]:
                attrs = candidate["attributes"]
                searchable = " ".join(
                    str(attrs.get(name, ""))
                    for name in ("aria-label", "title", "name", "placeholder", "value")
                )
                overlap = len(words & set(TOKENS.findall(searchable.lower())))
                ranked.append((overlap, candidate["id"]))
            choice = min(ranked, key=lambda item: (-item[0], item[1]))[1] if ranked else None
            predictions[(task["annotation_id"], action["action_uid"])] = {
                "candidate_id": choice,
                "operation": "CLICK",
            }
    return predictions


def score_actions(tasks, predictions):
    """Report candidate recall, element/action accuracy, and macro/micro task rates."""
    total = available = element = operation = joint = task_success = 0
    task_rates = []
    for task in tasks:
        task_total = task_joint = 0
        for action in task["actions"]:
            total += 1
            task_total += 1
            if not action["positive_ids"]:
                continue
            available += 1
            guess = predictions.get((task["annotation_id"], action["action_uid"]), {})
            element_ok = guess.get("candidate_id") in action["positive_ids"]
            operation_ok = guess.get("operation") == action["operation"]
            element += element_ok
            operation += operation_ok
            joint += element_ok and operation_ok
            task_joint += element_ok and operation_ok
        if task_total:
            task_rates.append(task_joint / task_total)
            task_success += task_joint == task_total
    return {
        "tasks": len(task_rates),
        "steps": total,
        "grounded_steps": available,
        "missing_positive_steps": total - available,
        "element_correct": element,
        "operation_correct": operation,
        "joint_correct": joint,
        "element_accuracy": element / available if available else None,
        "operation_accuracy": operation / available if available else None,
        "joint_micro_accuracy": joint / total if total else None,
        "joint_macro_accuracy": sum(task_rates) / len(task_rates) if task_rates else None,
        "task_success": task_success / len(task_rates) if task_rates else None,
    }
