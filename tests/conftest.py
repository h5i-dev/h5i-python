from __future__ import annotations

import sys
from pathlib import Path

# src-layout + sibling test helpers importable without installation.
ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "src"), str(ROOT / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
