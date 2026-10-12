"""Run every active layer over a document and return findings."""

from __future__ import annotations

from . import layer_doc, layer_jev, layer_regex, layer_spacy
from .masking import Document
from .model import DOC_CATEGORIES, REGEX_CATEGORIES, SEVERITIES, SPACY_CATEGORIES, Finding, Rule


class Engine:
    def __init__(self, rules: list[Rule], lang: str = "en", *, check_references: bool = False):
        self.rules = rules
        self.check_references = check_references
        self.reference_outcomes: list[dict] = []
        self.lang = lang
        self._nlp = None

    @property
    def nlp(self):
        if self._nlp is None:
            self._nlp = layer_spacy.load_model(self.lang)
        return self._nlp

    def lint(self, doc: Document) -> list[Finding]:
        self.reference_outcomes = []
        # Existing sentence-level veto behavior is unchanged. Reference review
        # settles its own required candidates rather than feeding them to noul.
        local = self.lint_deterministic(doc, include_references=False)
        findings = layer_jev.run(doc, [f for f in local if f.rule.reference_check is None])
        if self.check_references:
            for rule in self.rules:
                if rule.reference_check is not None:
                    reviewed, outcomes = layer_jev.run_references(doc, rule, self.nlp)
                    findings.extend(reviewed)
                    self.reference_outcomes.extend(outcomes)
        return _dedupe(findings)

    def lint_deterministic(self, doc: Document, *, include_references: bool = True) -> list[Finding]:
        """Run local detection alone, including when testing rule examples."""
        findings: list[Finding] = []
        regex_rules = [r for r in self.rules if r.category in REGEX_CATEGORIES]
        spacy_rules = [r for r in self.rules if r.category in SPACY_CATEGORIES and r.reference_check is None]
        doc_rules = [r for r in self.rules if r.category in DOC_CATEGORIES]
        if regex_rules:
            findings.extend(layer_regex.run(doc, regex_rules, lambda: self.nlp))
        if spacy_rules:
            findings.extend(layer_spacy.run(doc, spacy_rules, self.nlp))
        if doc_rules:
            findings.extend(layer_doc.run(doc, doc_rules, lambda: self.nlp))
        if self.check_references and include_references:
            from .reference_check import collect_reference_paragraphs
            for rule in self.rules:
                if rule.reference_check is not None:
                    for row in collect_reference_paragraphs(doc, self.nlp):
                        findings.extend(Finding(rule, c.start, c.end) for c in row.candidates)
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
