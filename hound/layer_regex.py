"""Layer 1: regex rules (categories phrase, template, punct).

Phrase and template rules run on the prose view. Punctuation rules run on the
masked view because they care about the literal characters (curly quotes are
normalised away in the prose view). Patterns are compiled case-insensitive and
multiline. `\\b` works as expected because the prose view is plain text.
"""

from __future__ import annotations

import re

from .masking import Document
from .model import Finding, Rule
from .sentences import containing_sentence, sentence_spans

_compiled: dict[str, re.Pattern] = {}


def _compile(pattern: str, flags: int = re.I | re.M) -> re.Pattern:
    key = f"{flags}:{pattern}"
    if key not in _compiled:
        _compiled[key] = re.compile(pattern, flags)
    return _compiled[key]


def run(doc: Document, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []
    spans = sentence_spans(doc, ("paragraph", "list", "quote", "heading", "field"))
    sentence_starts = {start for start, _ in spans}
    headings = doc.blocks_of("heading")

    def in_heading(offset: int) -> bool:
        return any(b.start <= offset < b.end for b in headings)

    for rule in rules:
        text = doc.masked if rule.category == "punct" else doc.prose
        regex = _compile(rule.pattern)
        unless = _compile(rule.unless, re.I) if rule.unless else None
        for m in regex.finditer(text):
            if m.end() == m.start():
                continue
            if rule.sentence_start and m.start() not in sentence_starts:
                continue
            if not rule.headings and in_heading(m.start()):
                continue
            if unless is not None:
                sent = containing_sentence(spans, m.start())
                context = text[sent[0] : sent[1]] if sent else m.group(0)
                if unless.search(context):
                    continue
            findings.append(Finding(rule, m.start(), m.end()))
    return findings
