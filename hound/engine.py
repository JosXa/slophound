"""Run every active layer over a document and return findings."""

from __future__ import annotations

from . import layer_doc, layer_regex, layer_spacy
from .masking import Document
from .model import DOC_CATEGORIES, REGEX_CATEGORIES, SEVERITIES, SPACY_CATEGORIES, Finding, Rule


class Engine:
    def __init__(self, rules: list[Rule], lang: str = "en"):
        self.rules = rules
        self.lang = lang
        self._nlp = None

    @property
    def nlp(self):
        if self._nlp is None:
            self._nlp = layer_spacy.load_model(self.lang)
        return self._nlp

    def lint(self, doc: Document) -> list[Finding]:
        findings: list[Finding] = []
        regex_rules = [r for r in self.rules if r.category in REGEX_CATEGORIES]
        spacy_rules = [r for r in self.rules if r.category in SPACY_CATEGORIES]
        doc_rules = [r for r in self.rules if r.category in DOC_CATEGORIES]
        if regex_rules:
            findings.extend(layer_regex.run(doc, regex_rules))
        if spacy_rules:
            findings.extend(layer_spacy.run(doc, spacy_rules, self.nlp))
        if doc_rules:
            findings.extend(layer_doc.run(doc, doc_rules))
        return _dedupe(findings)


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """When a phrase rule and a template rule cover the same span, keep the more
    severe one so the report does not say the same thing twice."""
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (f.start, -(f.end - f.start), order[f.severity]))
    kept: list[Finding] = []
    for f in findings:
        if f.rule.category == "doc":
            kept.append(f)
            continue
        shadowed = any(
            k.rule.category != "doc"
            and k.start <= f.start
            and f.end <= k.end
            and (k.start, k.end) != (f.start, f.end)
            and order[k.severity] <= order[f.severity]
            for k in kept
        )
        if not shadowed:
            kept.append(f)
    return kept
