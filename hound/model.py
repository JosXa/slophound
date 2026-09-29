"""Shared data types: rules, findings, and the document view all layers share."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Severity tiers, strongest first. The hound bites when a fixed phrase or template
# matched, barks when the grammar layer inferred the problem, and sniffs at
# document-level rhythm. Only bites fail the run (barks too under --strict).
BITE, BARK, SNIFF = "bite", "bark", "sniff"
SEVERITIES = (BITE, BARK, SNIFF)
# The professional vocabulary used by --formal (and SLOPHOUND_FORMAL=1) so CI
# systems and reporters that parse linter output see familiar words.
FORMAL_NAMES = {BITE: "error", BARK: "warning", SNIFF: "suggestion"}
# Rule files may use either vocabulary; the loader normalises to the hound words.
SEVERITY_ALIASES = {v: k for k, v in FORMAL_NAMES.items()} | {"violation": BITE}
CATEGORIES = ("phrase", "template", "punct", "verb", "adj", "noun", "doc")
REGEX_CATEGORIES = ("phrase", "template", "punct")
SPACY_CATEGORIES = ("verb", "adj", "noun")
DOC_CATEGORIES = ("doc",)


@dataclass(frozen=True)
class JevVeto:
    instructions: str
    true: str
    false: str
    threshold: float
    # A required review reports the finding only after Jev answered for it.
    # Without a key, or when the request fails, the rule is silent.
    required: bool = False


@dataclass
class Rule:
    id: str
    category: str
    severity: str
    message: str
    example: list[str]
    acceptable: list[str]
    source_file: Path
    # Regex layer.
    pattern: str | None = None
    # Require the match to start a sentence, rather than merely a wrapped line.
    sentence_start: bool = False
    # "sentence": test the pattern in each sentence and report the whole sentence once.
    scope: str = "match"
    # spaCy layer: a DependencyMatcher pattern (list of node dicts).
    dependency: list[list[dict]] | None = None  # one or more DependencyMatcher patterns
    # Extra regex that must NOT match the matched sentence.
    unless: str | None = None
    # spaCy-only regex that must NOT match the dependency-match span.
    match_unless: str | None = None
    # Document statistics layer: name of the metric function and its threshold.
    metric: str | None = None
    threshold: float | None = None
    min_sentences: int = 0
    min_paragraphs: int = 0
    # Informational provenance.
    most_common_in: list[str] = field(default_factory=list)
    # Whether the rule may fire inside Markdown headings (phrase rules only).
    headings: bool = False
    # A high-confidence yes can remove a sniff after deterministic detection.
    jev_veto: JevVeto | None = None
    # Short reminder after the full message has appeared in the current report.
    repeat_message: str | None = None


@dataclass
class Finding:
    rule: Rule
    # Zero-based offsets into the original text; end is exclusive.
    start: int
    end: int
    # Optional override for the message (doc rules include computed values).
    detail: str | None = None
    # The exact words the rule matched, as (start, end) offsets. A parser match
    # binds a few tokens that may sit apart ("AGENTS.md ... root file"); the
    # report underlines those words and not the stretch between them. Empty
    # means the whole span is the match.
    marks: list[tuple[int, int]] = field(default_factory=list)

    @property
    def severity(self) -> str:
        return self.rule.severity

    def marked_spans(self) -> list[tuple[int, int]]:
        return self.marks or [(self.start, self.end)]

    @property
    def message(self) -> str:
        return self.detail or self.rule.message
