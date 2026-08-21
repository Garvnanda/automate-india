"""Thin wrapper around seed.py — the "run constantly" reset command."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed import seed

if __name__ == "__main__":
    n = seed()
    print(f"reset complete — {n} label rows restored")
