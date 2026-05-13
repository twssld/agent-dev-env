#!/usr/bin/env python3
"""Zero-dependency test runner — works with any stock Python 3.9+."""

from __future__ import annotations

import pathlib
import sys
import unittest


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(here / "tests"), top_level_dir=str(here))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
