#!/usr/bin/env python3
"""Run from the checkout: uv run python tools/structural_eval.py DATASET.jsonl.

Default: offline request preview. Add --live for paid external inference.
Exit 0: valid report (including review/flagged); exit 2: input/request failure.
Reports include source text and raw valid responses: keep private for private data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hound.structural import DEFAULT_TIMEOUT, evaluate_dataset, load_dataset


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="JSONL: id, text, expected, split, provenance; 1–40 rows; text <=20000 chars")
    parser.add_argument("--live", action="store_true", help="explicitly allow network and credential lookup")
    parser.add_argument("--output", type=Path, help="write JSON report here instead of stdout")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="socket-operation timeout in seconds, not an overall deadline; >0 and <=60 (default 30)")
    args = parser.parse_args(argv)
    try:
        with args.dataset.open(encoding="utf-8") as stream:
            rows = load_dataset(stream)
        report = evaluate_dataset(rows, live=args.live, timeout=args.timeout)
        exit_code = 2 if any(row["status"] == "error" for row in report["rows"]) else 0
    except (OSError, ValueError):
        report = {"status": "error", "errors": ["invalid_or_unreadable_dataset_or_options"]}
        exit_code = 2
    rendered = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    try:
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    except OSError:
        sys.stderr.write("Could not write report.\n")
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
