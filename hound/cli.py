"""Command-line interface.

    slophound FILE [FILE...]      lint files (Markdown or plain text)
    slophound -                   lint stdin
    slophound test                run the rule self-tests and the corpus checks

Exit codes: 0 no errors, 1 at least one error (or warning with --strict),
2 the tool itself failed (bad rule file, missing model, unreadable input).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import Engine
from .loader import RuleError, load_rules
from .masking import build_document
from .model import CATEGORIES, Finding, Rule
from .report import footer, render, summary_line

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_FAILURE = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slophound",
        description="A linter for prose written by language models.",
        epilog="Exit codes: 0 no errors, 1 errors found, 2 tool failure.",
    )
    p.add_argument("paths", nargs="*", help="Markdown or text files; '-' reads stdin. 'test' runs the self-tests.")
    p.add_argument("--disable", action="append", default=[], metavar="ID[,ID]", help="skip these rule ids for this run")
    p.add_argument(
        "--disable-category",
        action="append",
        default=[],
        metavar="CAT[,CAT]",
        help=f"skip a whole category for this run; one of {', '.join(CATEGORIES)}",
    )
    p.add_argument("--only", action="append", default=[], metavar="ID[,ID]", help="run only these rule ids")
    p.add_argument("--strict", action="store_true", help="warnings count as errors for the exit code")
    p.add_argument("--lang", default="en", metavar="XX", help="language code for the grammar layer (default en)")
    p.add_argument("--skip-quotes", action="store_true", help="do not lint Markdown blockquotes")
    p.add_argument("--no-footer", action="store_true", help="omit the false-positive instructions")
    p.add_argument("--rules", type=Path, default=None, help=argparse.SUPPRESS)
    return p


def _split(values: list[str]) -> set[str]:
    out: set[str] = set()
    for v in values:
        out.update(x.strip() for x in v.split(",") if x.strip())
    return out


def select_rules(rules: list[Rule], disable: set[str], disable_category: set[str], only: set[str]) -> list[Rule]:
    known = {r.id for r in rules}
    for rid in disable | only:
        if rid not in known:
            raise RuleError(f"unknown rule id {rid!r}")
    for cat in disable_category:
        if cat not in CATEGORIES:
            raise RuleError(f"unknown category {cat!r}; expected one of {', '.join(CATEGORIES)}")
    selected = []
    for r in rules:
        if only and r.id not in only:
            continue
        if r.id in disable or r.category in disable_category:
            continue
        selected.append(r)
    return selected


def read_input(path: str) -> tuple[str, str]:
    if path == "-":
        return "<stdin>", sys.stdin.read()
    p = Path(path)
    return str(p), p.read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.paths and args.paths[0] == "test":
        from .selftest import main as selftest_main

        return selftest_main(args.paths[1:], rules_dir=args.rules)

    if not args.paths:
        parser.print_usage(sys.stderr)
        print("slophound: give at least one file, or '-' for stdin", file=sys.stderr)
        return EXIT_FAILURE

    try:
        rules = load_rules(args.rules) if args.rules else load_rules()
        rules = select_rules(rules, _split(args.disable), _split(args.disable_category), _split(args.only))
    except RuleError as exc:
        print(f"slophound: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    engine = Engine(rules, lang=args.lang)
    all_findings: list[Finding] = []
    total_words = 0
    rule_files: dict[str, None] = {}
    try:
        for path in args.paths:
            name, text = read_input(path)
            doc = build_document(name, text, skip_quotes=args.skip_quotes)
            findings = engine.lint(doc)
            render(doc, findings)
            all_findings.extend(findings)
            total_words += doc.word_count()
            for f in findings:
                rule_files.setdefault(str(f.rule.source_file), None)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"slophound: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except Exception as exc:  # model download, matcher errors: still a tool failure
        from .layer_spacy import ModelError

        if isinstance(exc, (ModelError, ValueError)):
            print(f"slophound: {exc}", file=sys.stderr)
            return EXIT_FAILURE
        raise

    print(summary_line(all_findings, total_words))
    if all_findings and not args.no_footer:
        print(footer(sorted(rule_files)))

    failing = {"error", "warning"} if args.strict else {"error"}
    return EXIT_FINDINGS if any(f.severity in failing for f in all_findings) else EXIT_CLEAN
