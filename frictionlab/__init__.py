"""FrictionLab: validated configuration and disposable local UX fixtures."""

import os

# Set before browser-use imports: no implicit usage reporting.
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["DO_NOT_TRACK"] = "1"

__version__ = "0.1.0"
