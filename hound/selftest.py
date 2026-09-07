"""`slophound test`: validate every rule against its own examples and check the corpus.

Per rule:
- every `example` sentence must produce a finding for exactly that rule;
- no `acceptable` sentence may produce a finding for that rule.

Corpus (`tests/corpus/`):
- every file in `generated/` must produce at least one bite;
- every file in `human/` must produce zero bites, and stays under a warning
  density ceiling so grammar rules cannot drift into a word blacklist.

Extra checks: masking keeps offsets, output renders, and the repository's own
Markdown passes.
"""

from __future__ import annotations

import io
import sys
import time
import traceback
from pathlib import Path

from .engine import Engine
from .loader import RULES_DIR, RuleError, load_rules
from .masking import build_document
from .model import BITE, DOC_CATEGORIES, SPACY_CATEGORIES, Finding, Rule
from .report import Vocabulary, render, summary_line

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "corpus"
HUMAN_WARNING_DENSITY_CEILING = 1.0  # warnings + suggestions per 100 words


def _lint_snippet(engine: Engine, text: str) -> list[Finding]:
    # Wrap the snippet as a paragraph so doc rules see a document and phrase
    # rules see a sentence. A trailing newline keeps the block splitter happy.
    doc = build_document("<snippet>", text.rstrip("\n") + "\n")
    return engine.lint(doc)


def check_rule(engine: Engine, rule: Rule) -> list[str]:
    # Run the rule in isolation. The full engine drops a finding that another
    # rule already covers on the same span, which would hide a working rule
    # behind a stronger one and make this check lie.
    solo = Engine([rule], engine.lang)
    if rule.category in SPACY_CATEGORIES:
        solo._nlp = engine.nlp
    problems: list[str] = []
    for sentence in rule.example:
        if not _lint_snippet(solo, sentence):
            problems.append(f"example did not fire: {sentence!r}")
    for sentence in rule.acceptable:
        if _lint_snippet(solo, sentence):
            problems.append(f"acceptable fired: {sentence!r}")
    return problems


def check_corpus(engine: Engine) -> list[str]:
    problems: list[str] = []
    generated = sorted((CORPUS / "generated").glob("*.md"))
    human = sorted((CORPUS / "human").glob("*.md"))
    if not generated:
        problems.append("tests/corpus/generated has no files")
    if not human:
        problems.append("tests/corpus/human has no files")
    for path in generated:
        doc = build_document(str(path), path.read_text(encoding="utf-8"))
        findings = engine.lint(doc)
        if not any(f.severity == BITE for f in findings):
            problems.append(f"{path.relative_to(ROOT)}: generated text produced no bite")
    for path in human:
        doc = build_document(str(path), path.read_text(encoding="utf-8"))
        findings = engine.lint(doc)
        bites = [f for f in findings if f.severity == BITE]
        for f in bites:
            line, col = doc.line_col(f.start)
            problems.append(f"{path.relative_to(ROOT)}:{line}:{col}: human text hit {f.rule.id}: {doc.text[f.start:f.end]!r}")
        soft = [f for f in findings if f.severity != BITE]
        density = len(soft) / max(doc.word_count(), 1) * 100
        if density > HUMAN_WARNING_DENSITY_CEILING:
            ids = sorted({f.rule.id for f in soft})
            problems.append(
                f"{path.relative_to(ROOT)}: {density:.1f} warnings per 100 words exceeds {HUMAN_WARNING_DENSITY_CEILING} ({', '.join(ids)})"
            )
    return problems


def check_own_docs(engine: Engine) -> list[str]:
    problems: list[str] = []
    for path in sorted(ROOT.glob("*.md")):
        doc = build_document(str(path), path.read_text(encoding="utf-8"))
        bites = [f for f in engine.lint(doc) if f.severity == BITE]
        for f in bites:
            line, col = doc.line_col(f.start)
            problems.append(f"{path.relative_to(ROOT)}:{line}:{col}: own docs hit {f.rule.id}")
    return problems


def check_masking() -> list[str]:
    problems: list[str] = []
    sample = (
        "---\ntitle: x\n---\n# Heading\n\nText with `code` and a [link](https://x.y/z) and\n\n```\nnot prose\n```\n"
        "> quote here\n\n| a | b |\n|---|---|\n\n<!-- comment --> tail\n\n"
        "---\nlayout: slide\n---\n\nSee [Artifact Centric Approach](https://x.y/a) and [the guide](https://x.y/g).\n\n"
        "<RepoTree\n  eyebrow=\"Repo layout\"\n  :depth=\"2\"\n/>\n\n"
        "::: tip\nInside the container.\n:::\n\n"
        "Costs are 3 < 5 here and stay visible.\n"
    )
    doc = build_document("<sample>", sample)
    if len(doc.masked) != len(sample) or len(doc.prose) != len(sample):
        problems.append("masking changed text length")
    for needle in (
        "title: x", "code", "https://x.y/z", "not prose", "| a | b |", "comment",
        "layout: slide", "Artifact Centric", "eyebrow", "Repo layout", "::: tip",
    ):
        if needle in doc.masked:
            problems.append(f"masking left {needle!r} visible")
    for needle in ("the guide", "Inside the container", "3 < 5 here and stay visible"):
        if needle not in doc.prose:
            problems.append(f"{needle!r} is prose and must stay visible")
    if "quote here" not in doc.prose:
        problems.append("blockquote text should stay visible by default")
    skipped = build_document("<sample>", sample, skip_quotes=True)
    if "quote here" in skipped.prose or "quote here" in skipped.masked:
        problems.append("--skip-quotes should hide blockquote text from every layer")
    kinds = [b.kind for b in doc.blocks]
    if kinds[:3] != ["heading", "paragraph", "quote"]:
        problems.append(f"unexpected block kinds {kinds}")
    return problems


def check_render(engine: Engine) -> list[str]:
    doc = build_document("<r>", "This isn't just fast. It's correct. Full stop.\n")
    findings = engine.lint(doc)
    buf = io.StringIO()
    render(doc, findings, stream=buf)
    out = buf.getvalue()
    problems = []
    if findings and "<r>:1:" not in out:
        problems.append("render did not print location")
    if findings and "^" not in out:
        problems.append("render did not underline")
    summary = summary_line(findings, doc.word_count())
    if findings and "bite" not in summary:
        problems.append(f"default summary should count bites: {summary!r}")
    formal = Vocabulary(formal=True)
    buf = io.StringIO()
    render(doc, findings, stream=buf, vocab=formal)
    formal_out = buf.getvalue()
    formal_summary = summary_line(findings, doc.word_count(), formal)
    for hound_word in ("bite", "bark", "sniff"):
        if hound_word in formal_out or hound_word in formal_summary:
            problems.append(f"--formal output still contains {hound_word!r}")
    if findings and "error" not in formal_summary:
        problems.append(f"--formal summary should count errors: {formal_summary!r}")
    return problems


def check_severity_aliases() -> list[str]:
    """Rule files may say error/warning/suggestion; the loader maps them to bite/bark/sniff."""
    from .loader import SEVERITY_ALIASES

    expected = {"error": "bite", "warning": "bark", "suggestion": "sniff", "violation": "bite"}
    return [f"alias {k!r} maps to {SEVERITY_ALIASES.get(k)!r}, expected {v!r}" for k, v in expected.items() if SEVERITY_ALIASES.get(k) != v]


def main(argv: list[str], rules_dir: Path | None = None) -> int:
    verbose = "-v" in argv or "--verbose" in argv
    started = time.monotonic()
    try:
        rules = load_rules(rules_dir or RULES_DIR)
    except RuleError as exc:
        print(f"FAIL rules: {exc}")
        return 2
    engine = Engine(rules)

    failures = 0
    total = 0

    def report(name: str, problems: list[str]) -> None:
        nonlocal failures, total
        total += 1
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     {p}")
        elif verbose:
            print(f"ok   {name}")

    try:
        report("masking", check_masking())
        for rule in rules:
            report(rule.id, check_rule(engine, rule))
        report("render", check_render(engine))
        report("severity-aliases", check_severity_aliases())
        report("corpus", check_corpus(engine))
        report("own-docs", check_own_docs(engine))
    except Exception:
        traceback.print_exc()
        return 2

    elapsed = time.monotonic() - started
    print(f"{total - failures} passed, {failures} failed, {len(rules)} rules, {elapsed:.1f}s")
    return 1 if failures else 0
