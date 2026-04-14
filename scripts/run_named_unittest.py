#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run selected unittest names with an optional tests directory on sys.path")
    parser.add_argument("--tests-dir", help="Directory to prepend to sys.path before loading tests")
    parser.add_argument("--name", dest="names", action="append", required=True, help="Test name to load; repeat for multiple names")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.tests_dir:
        sys.path.insert(0, str(Path(args.tests_dir).resolve()))
    suite = unittest.TestLoader().loadTestsFromNames(list(args.names))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
