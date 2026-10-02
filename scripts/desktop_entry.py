"""Frozen desktop entry point; optional development dashboards are excluded."""
from frictionlab.desktop import main
if __name__ == "__main__":
    raise SystemExit(main())
