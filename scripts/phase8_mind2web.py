"""Remote-only pinned Mind2Web train-shard loader and lexical reference smoke."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.request import urlopen

from frictionlab.evaluation.mind2web import (
    DATASET,
    REVISION,
    TRAIN_SMOKE,
    TRAIN_SMOKE_SHA256,
    lexical_reference,
    load_actions,
    score_actions,
)


def main():
    target = Path(tempfile.gettempdir()) / "frictionlab-mind2web" / TRAIN_SMOKE
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{TRAIN_SMOKE}"
    if not target.is_file():
        with urlopen(url, timeout=60) as response, target.open("wb") as stream:
            copied = 0
            while chunk := response.read(1024 * 1024):
                copied += len(chunk)
                if copied > 40 * 1024 * 1024:
                    raise ValueError("Pinned training smoke shard exceeded its size ceiling")
                stream.write(chunk)
    with target.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != TRAIN_SMOKE_SHA256:
            raise ValueError("Pinned training smoke shard checksum mismatch")
    tasks = load_actions(target, split="train", sha256=TRAIN_SMOKE_SHA256, max_tasks=25)
    score = score_actions(tasks, lexical_reference(tasks))
    result = {
        "dataset": DATASET,
        "revision": REVISION,
        "split": "train",
        "file": TRAIN_SMOKE,
        "sha256": TRAIN_SMOKE_SHA256,
        "predictor": "untuned lexical reference, not the production browser agent",
        "interpretation": "Training-shard integration diagnostic only; not held-out Mind2Web generalization or a UX metric.",
        "metrics": score,
    }
    output = Path("artifacts/phase8/validation/mind2web-smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
