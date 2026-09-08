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
from .model import BARK, BITE, DOC_CATEGORIES, SPACY_CATEGORIES, Finding, Rule
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
        "---\nlayout: slide\nclass: text-center mt-4\nheading: Both sit at the top of the list\n"
        "tiles:\n  - icon: gear\n    detail: Handles structured calls reliably.\n---\n\n"
        "See [Artifact Centric Approach](https://x.y/a) and [the guide](https://x.y/g).\n\n"
        "<RepoTree\n  eyebrow=\"Repo layout\"\n  :depth=\"2\"\n/>\n\n"
        "::: tip\nInside the container.\n:::\n\n"
        "Costs are 3 < 5 here and stay visible.\n"
    )
    doc = build_document("<sample>", sample)
    if len(doc.masked) != len(sample) or len(doc.prose) != len(sample):
        problems.append("masking changed text length")
    for needle in (
        "title: x", "code", "https://x.y/z", "not prose", "| a | b |", "comment",
        "layout: slide", "text-center mt-4", "heading:", "icon: gear", "Artifact Centric",
        "eyebrow", "Repo layout", "::: tip",
    ):
        if needle in doc.masked:
            problems.append(f"masking left {needle!r} visible")
    for needle in (
        "the guide", "Inside the container", "3 < 5 here and stay visible",
        # Front-matter values the reader sees are prose; keys and settings are not.
        "Both sit at the top of the list", "Handles structured calls reliably.",
    ):
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
    if kinds.count("field") != 2:
        problems.append(f"expected two field blocks for the exposed YAML values, got {kinds}")
    wrapped_list = "- We checked\n  five things.\n- We fixed\ntwo things.\n"
    list_doc = build_document("<wrapped-list>", wrapped_list)
    items = list_doc.blocks_of("list")
    if len(items) != 2 or any("\n" not in list_doc.prose[b.start:b.end] for b in items):
        problems.append("list continuations must stay in their list item")
    if len(list_doc.prose) != len(wrapped_list):
        problems.append("list continuation masking changed text length")
    # A fenced block indented inside a list item is still code (CommonMark allows
    # up to three spaces, list continuation allows more). docs/adding-rules.md
    # had one with "That holds" in it and verb.holds fired on the code.
    indented_fence = "1. Run it:\n\n   ```sh\n   tools/parse.py \"That holds.\"\n   ```\n\n   Then read.\n"
    fence_doc = build_document("<indented-fence>", indented_fence)
    if "That holds" in fence_doc.masked:
        problems.append("indented fenced code inside a list item must be masked")
    if "Then read." not in fence_doc.prose:
        problems.append("text after an indented fence must stay visible")
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


def check_regex_context(engine: Engine) -> list[str]:
    """Check rule interaction, sentence boundaries, and offsets after masking."""
    from . import layer_regex
    from .loader import _build_rule

    ids = {"phrase.patronizing", "phrase.easy-part", "phrase.rhetorical-prompts", "phrase.formula-heading", "phrase.strategy-buzzwords", "template.count-opener", "punct.em-dash", "punct.em-dash-and"}
    rules = [rule for rule in engine.rules if rule.id in ids]
    cases = [
        ("We built it \u2014 and shipped it.", [("punct.em-dash-and", BITE)]),
        ("We built it\u2014and shipped it.", [("punct.em-dash-and", BITE)]),
        ("We built it \u2014\nAND shipped it.", [("punct.em-dash-and", BITE)]),
        ("We built it \u2014 and shipped it \u2014 yesterday.", [("punct.em-dash-and", BITE), ("punct.em-dash", BITE)]),
        ("Installation is the easy part.", [("phrase.easy-part", BARK)]),
        ("Nobody explains the plan. Everyone agrees anyway.", [("phrase.patronizing", BITE), ("phrase.patronizing", BITE)]),
        ("**Five things** remain.  Two options remain.", [("template.count-opener", BITE), ("template.count-opener", BITE)]),
        ("We checked\nFive Things Incorporated.\nFive things remain.", [("template.count-opener", BITE)]),
        ("We checked. five things remain.", [("template.count-opener", BITE)]),
        ("Five\nthings remain.", [("template.count-opener", BITE)]),
        ("- We checked\n  five things.\n- Two things remain.", [("template.count-opener", BITE)]),
        ("- We checked\nfive things.\n- Two things remain.", [("template.count-opener", BITE)]),
        ("## Five things\n\n- Five things remain.", [("template.count-opener", BITE)]),
        ("We shipped it and checked five things.", []),
        ("`Nobody explains` and `Everyone agrees` are example phrases.", []),
        ("The line items follow Acme Inc. invoice numbering.", []),
        ("The invoice came from Acme Inc. Our north star metric is retention.", [("phrase.strategy-buzzwords", BITE)]),
        ("We deploy at 9 a.m. Five workers restart.", [("template.count-opener", BITE)]),
        ("Why this matters: retries can duplicate writes.", [("phrase.rhetorical-prompts", BITE)]),
        ("## Why this matters so much for AI", [("phrase.rhetorical-prompts", BITE)]),
    ]
    problems = []
    for text, expected in cases:
        doc = build_document("<regex-context>", text)
        # Inspect raw findings so deduplication cannot hide overlapping rules.
        findings = sorted(layer_regex.run(doc, rules), key=lambda f: f.start)
        actual = [(f.rule.id, f.severity) for f in findings]
        if actual != expected:
            problems.append(f"{text!r}: expected {expected!r}, got {actual!r}")
        for finding in findings:
            if finding.rule.id == "template.count-opener" and text[finding.start:finding.end] not in {"Five", "five", "Two"}:
                problems.append(f"count opener has incorrect source offsets in {text!r}")

    raw = {
        "id": "template.test", "severity": BITE, "pattern": "test", "message": "Test.",
        "example": ["test"], "acceptable": ["other"], "sentence_start": "true",
    }
    try:
        _build_rule(raw, "template", Path("<test>"))
    except RuleError:
        pass
    else:
        problems.append("loader accepted a non-boolean sentence_start")
    return problems


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
        report("regex-context", check_regex_context(engine))
        report("corpus", check_corpus(engine))
        report("own-docs", check_own_docs(engine))
    except Exception:
        traceback.print_exc()
        return 2

    elapsed = time.monotonic() - started
    print(f"{total - failures} passed, {failures} failed, {len(rules)} rules, {elapsed:.1f}s")
    return 1 if failures else 0
