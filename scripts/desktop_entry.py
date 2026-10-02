"""Frozen entry point with noninteractive CI failure handling."""

import json
import sys
from pathlib import Path

from frictionlab.desktop import main

if __name__ == "__main__":
    if any(flag in sys.argv for flag in ("--self-check", "--serve-smoke")):
        try:
            result = main()
        except Exception as exc:  # noqa: BLE001 - Exit smoke mode without a blocking native error dialog.
            Path("packaged-failure.json").write_text(
                json.dumps({"status": "failed", "exception_type": type(exc).__name__}),
                encoding="utf-8",
            )
            result = 1
        raise SystemExit(result)
    raise SystemExit(main())
