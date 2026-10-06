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


def _matches(text, regex, spans, nominal_prefix):
    if not nominal_prefix:
        yield from ((match, 0) for match in regex.finditer(text))
        return
    # A prefix must cover its sentence, so an ordinary finite clause cannot be
    # bypassed by matching only its last few words. Sentence windows also keep
    # wrapped phrases together without joining separate paragraphs.
    for start, end in spans:
        match = regex.fullmatch(text[start:end])
        if match is not None:
            yield match, start


def _is_nominal_prefix(prefix, nlp):
    if not prefix:
        return False
    parsed = nlp(prefix)
    if any(token.tag_ in {"VBD", "VBP", "VBZ", "MD"} for token in parsed):
        return False
    return any(token.dep_ == "ROOT" and token.pos_ in {"NOUN", "PROPN", "PRON"} for token in parsed)


def run(doc: Document, rules: list[Rule], get_nlp=None) -> list[Finding]:
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
        for m, offset in _matches(text, regex, spans, rule.nominal_prefix):
            if m.end() == m.start():
                continue
            start, end = offset + m.start(), offset + m.end()
            if rule.sentence_start and start not in sentence_starts:
                continue
            if not rule.headings and in_heading(start):
                continue
            if rule.heading_only and not in_heading(start):
                continue
            if unless is not None:
                sent = containing_sentence(spans, start)
                context = text[sent[0] : sent[1]] if sent else m.group(0)
                if unless.search(context):
                    continue
            if rule.nominal_prefix and not _is_nominal_prefix(m["prefix"], get_nlp()):
                continue
            findings.append(Finding(rule, start, end))
    return findings
