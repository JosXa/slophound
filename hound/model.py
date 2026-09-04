"""Shared data types: rules, findings, and the document view all layers share."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SEVERITIES = ("error", "warning", "suggestion")
CATEGORIES = ("phrase", "template", "punct", "verb", "adj", "doc")
REGEX_CATEGORIES = ("phrase", "template", "punct")
SPACY_CATEGORIES = ("verb", "adj")
DOC_CATEGORIES = ("doc",)


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
    # spaCy layer: a DependencyMatcher pattern (list of node dicts).
    dependency: list[list[dict]] | None = None  # one or more DependencyMatcher patterns
    # Extra regex that must NOT match the matched sentence (regex layer only).
    unless: str | None = None
    # Document statistics layer: name of the metric function and its threshold.
    metric: str | None = None
    threshold: float | None = None
    min_sentences: int = 0
    min_paragraphs: int = 0
    # Informational provenance.
    most_common_in: list[str] = field(default_factory=list)
    # Whether the rule may fire inside Markdown headings (phrase rules only).
    headings: bool = False


@dataclass
class Finding:
    rule: Rule
    # Zero-based offsets into the original text; end is exclusive.
    start: int
    end: int
    # Optional override for the message (doc rules include computed values).
    detail: str | None = None

    @property
    def severity(self) -> str:
        return self.rule.severity

    @property
    def message(self) -> str:
        return self.detail or self.rule.message
