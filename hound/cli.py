"""Command-line interface.

    slophound FILE [FILE...]      lint files (Markdown or plain text)
    slophound -                   lint stdin
    slophound test                run the rule self-tests and the corpus checks
    slophound auth set-key        store a Jev key from a hidden prompt or stdin

Exit codes: 0 no bites, 1 at least one bite (or bark with --strict),
2 the tool itself failed (bad rule file, missing model, unreadable input).

Severities are bite / bark / sniff by default; --formal or SLOPHOUND_FORMAL=1
prints error / warning / suggestion instead for CI logs and reporters.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import Engine
from .loader import RuleError, load_rules
from .masking import build_document
from .model import BARK, BITE, CATEGORIES, Finding, Rule
from .report import Vocabulary, footer, formal_requested, render, summary_line

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_FAILURE = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slophound",
        description="A linter for prose written by language models.",
        epilog=(
            "Severities: bite (fixed phrase or template, must reach zero), bark (grammar-inferred), "
            "sniff (document rhythm). Exit codes: 0 no bites, 1 bites found, 2 tool failure."
            " Use 'auth set-key' to let Jev review ambiguous findings automatically."
        ),
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
    p.add_argument("--strict", action="store_true", help="barks count as bites for the exit code")
    p.add_argument(
        "--formal",
        action="store_true",
        help="print error/warning/suggestion instead of bite/bark/sniff (also SLOPHOUND_FORMAL=1); for CI",
    )
    p.add_argument("--lang", default="en", metavar="XX", help="language code for the grammar layer (default en)")
    p.add_argument("--skip-quotes", action="store_true", help="do not lint Markdown blockquotes")
    p.add_argument(
        "--no-emoji",
        action="store_true",
        help="also flag emoji in prose (punct.emoji is off by default; it is a taste, not a tell)",
    )
    p.add_argument("--no-footer", action="store_true", help="omit the false-positive instructions")
    p.add_argument("--rules", type=Path, default=None, help=argparse.SUPPRESS)
    return p


def _split(values: list[str]) -> set[str]:
    out: set[str] = set()
    for v in values:
        out.update(x.strip() for x in v.split(",") if x.strip())
    return out


EMOJI_RULE = "punct.emoji"


def select_rules(
    rules: list[Rule],
    disable: set[str],
    disable_category: set[str],
    only: set[str],
    no_emoji: bool = False,
) -> list[Rule]:
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
        # Emoji are a taste, not a machine tell: the rule runs only on request.
        if r.id == EMOJI_RULE and not (no_emoji or r.id in only):
            continue
        selected.append(r)
    return selected


def read_input(path: str) -> tuple[str, str]:
    if path == "-":
        return "<stdin>", sys.stdin.read()
    p = Path(path)
    return str(p), p.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "auth":
        return auth_main(argv[1:])
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
        rules = select_rules(
            rules, _split(args.disable), _split(args.disable_category), _split(args.only), args.no_emoji
        )
    except RuleError as exc:
        print(f"slophound: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    vocab = Vocabulary(args.formal or formal_requested())
    engine = Engine(rules, lang=args.lang)
    all_findings: list[Finding] = []
    total_words = 0
    rule_files: dict[str, None] = {}
    seen_rules: set[str] = set()
    try:
        for path in args.paths:
            name, text = read_input(path)
            doc = build_document(name, text, skip_quotes=args.skip_quotes)
            findings = engine.lint(doc)
            render(doc, findings, vocab=vocab, seen_rules=seen_rules)
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

    print(summary_line(all_findings, total_words, vocab))
    if all_findings and not args.no_footer:
        print(footer(sorted(rule_files)))

    failing = {BITE, BARK} if args.strict else {BITE}
    return EXIT_FINDINGS if any(f.severity in failing for f in all_findings) else EXIT_CLEAN


def auth_main(argv: list[str]) -> int:
    import getpass
    import warnings

    from .config import ConfigError, save_jev_key

    parser = argparse.ArgumentParser(prog="slophound auth", description="Store a Jev key for all harnesses.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("set-key", help="read a key from a hidden prompt or piped stdin")
    parser.parse_args(argv)
    try:
        if sys.stdin.isatty():
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("TypeSafe API key: ")
        else:
            key = sys.stdin.read()
        path = save_jev_key(key)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print("slophound: could not read a hidden key; pipe it on stdin instead.", file=sys.stderr)
        return EXIT_FAILURE
    except (OSError, UnicodeError):
        print("slophound: could not read the API key.", file=sys.stderr)
        return EXIT_FAILURE
    except ConfigError as exc:
        print(f"slophound: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    print(f"Saved Jev key to {path}")
    return EXIT_CLEAN
