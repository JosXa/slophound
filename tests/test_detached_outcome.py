"""Detached outcome endings in prose, headings, and wrapped sentences."""

from pathlib import Path
import unittest
from unittest.mock import patch

from hound.engine import Engine
from hound.loader import RuleError, _build_rule, load_rules
from hound.masking import build_document


class DetachedOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rule = next(r for r in load_rules() if r.id == "phrase.detached-outcome")
        cls.engine = Engine([cls.rule])

    def findings(self, text):
        return self.engine.lint_deterministic(build_document("example.md", text))

    def test_user_examples_and_arbitrary_openers(self):
        for text in (
            "the same submission, answered",
            "all the same process, verified",
            "Your workflow, simplified.",
            "## The architecture, demystified",
            "### One workflow, perfected",
        ):
            with self.subTest(text=text):
                findings = self.findings(text)
                self.assertEqual(["bark"], [f.severity for f in findings])

    def test_attested_heading_and_colon_label(self):
        # Trace Commons row 25/messages[812].content, session model label
        # claude-opus-4-8. The introductory "carries" must not veto the prefix.
        for text in (
            "## What this MR carries — the whole arc, verified",
            "Outcome: the whole process, verified.",
        ):
            with self.subTest(text=text):
                self.assertEqual(1, len(self.findings(text)))

    def test_finite_clauses_do_not_become_partial_matches(self):
        for text in (
            "The patch is small, verified.",
            "The reviewer explained the workflow, simplified.",
            "Outcome: the patch is small, verified.",
            "The issue, solved by the maintainer, stayed closed.",
            "The process, verified against the audit log.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_faq_and_identifier_status_labels(self):
        for text in (
            "## Your questions, answered",
            "Frequently asked questions, answered.",
            "Order 123, verified.",
            "Ticket ABC-123, answered.",
            "Build #17, verified.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_offsets_for_multiple_sentences_and_wrapping(self):
        text = "We shipped the patch. The same\nsubmission, answered. Your workflow, simplified."
        findings = self.findings(text)
        self.assertEqual(
            ["The same\nsubmission, answered.", "Your workflow, simplified."],
            [text[f.start:f.end] for f in findings],
        )

    def test_paragraphs_cannot_supply_an_earlier_prefix(self):
        text = "The reviewer signed\n\nYour workflow, simplified."
        findings = self.findings(text)
        self.assertEqual(["Your workflow, simplified."], [text[f.start:f.end] for f in findings])

    def test_frontmatter_and_lists(self):
        for text in (
            "---\ntitle: Your workflow, simplified\n---\n",
            "- Your workflow, simplified.",
        ):
            with self.subTest(text=text):
                self.assertEqual(1, len(self.findings(text)))

    def test_code_and_quotations_stay_masked(self):
        for text in (
            "`Your workflow, simplified.`",
            "```text\nYour workflow, simplified.\n```",
            'The article quotes "Your workflow, simplified." as an example.',
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_no_parser_load_without_an_eligible_lexical_candidate(self):
        for text in ("The reviewer answered the submission.", "## Your questions, answered"):
            with self.subTest(text=text), patch("hound.engine.layer_spacy.load_model") as load:
                findings = Engine([self.rule]).lint_deterministic(build_document("plain.md", text))
                self.assertEqual([], findings)
                load.assert_not_called()


class NominalPrefixLoaderTests(unittest.TestCase):
    raw = {
        "id": "phrase.test", "severity": "bark", "message": "Use a complete clause.",
        "pattern": r"(?P<prefix>.+), verified", "nominal_prefix": True,
        "example": ["The process, verified"], "acceptable": ["The process was verified"],
    }

    def test_named_prefix_is_required(self):
        with self.assertRaisesRegex(RuleError, "named prefix"):
            _build_rule({**self.raw, "pattern": r".+, verified"}, "phrase", Path("<test>"))

    def test_flag_is_a_phrase_boolean(self):
        self.assertTrue(_build_rule(self.raw, "phrase", Path("<test>")).nominal_prefix)
        for raw, category in (
            ({**self.raw, "nominal_prefix": "yes"}, "phrase"),
            ({**self.raw, "id": "template.test"}, "template"),
            ({**self.raw, "id": "verb.test"}, "verb"),
        ):
            with self.subTest(category=category), self.assertRaises(RuleError):
                _build_rule(raw, category, Path("<test>"))


if __name__ == "__main__":
    unittest.main()
