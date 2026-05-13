#!/usr/bin/env python3
"""Scan Claude/Cursor JSONL transcripts for repo Harness failure candidates.

This script intentionally emits candidates, not final judgments. A human or
agent should validate each candidate with the evidence-chain standard from the
skill reference.

Implementation lives under `scan_lib/`. This file is just a thin entry point
so the bundled command path stays stable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan_lib.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
