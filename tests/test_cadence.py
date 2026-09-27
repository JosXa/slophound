"""Regression boundaries for repeated assertions and appended references."""

import unittest
from unittest.mock import Mock

from hound.cadence import clause_parts, parallel_assertions
from hound.engine import Engine
from hound.layer_spacy import load_model
from hound.loader import load_rules
from hound.masking import build_document


ORIGINAL = "Red means fix it, green means done, and the same text produces the same findings on every run."
CLAUDE = "Conversations felt forced, laughter felt less frequent, and intimacy felt routine."
GPT = "Days turn into nights, nights turn into days, and you lose track of your own existence."
FILLER = "The worker reads the queue."


class CadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = load_model("en")
        rules = load_rules()
        cls.rule = next(r for r in rules if r.id == "doc.parallel-clause-repeats")
        cls.reference = next(r for r in rules if r.id == "template.appended-backreference")

    def lint(self, text, rule=None):
        engine = Engine([rule or self.rule])
        engine._nlp = self.nlp
        return engine.lint_deterministic(build_document("test.md", text))

    def test_actual_generated_sentences(self):
        # Check recognition separately from frequency: one occurrence is allowed.
        for text in (ORIGINAL, CLAUDE, GPT):
            with self.subTest(text=text):
                parts = clause_parts(text)
                self.assertIsNotNone(parts)
                self.assertTrue(parallel_assertions(parts, list(self.nlp.pipe(parts))))
                self.assertEqual([], self.lint(text))

    def test_two_different_predicates_across_sentences_and_locations(self):
        text = "# Status\n\n" + "\n\n".join((ORIGINAL, CLAUDE))
        finding, = self.lint(text)
        self.assertEqual("sniff", finding.severity)
        self.assertEqual(ORIGINAL, text[finding.start:finding.end])
        self.assertIn("3:1, 5:1", finding.message)

    def test_window_boundary_and_dilution(self):
        inside = " ".join([ORIGINAL] + [FILLER] * 48 + [CLAUDE])
        outside = " ".join([ORIGINAL] + [FILLER] * 49 + [CLAUDE])
        self.assertEqual(1, len(self.lint(inside)))
        self.assertEqual([], self.lint(outside))
        self.assertEqual(1, len(self.lint(" ".join([FILLER] * 60 + [ORIGINAL, CLAUDE]))))

    def test_repeated_counterexamples_stay_silent(self):
        cases = [
            "The rate for October was 14.9 million, and the rate for November 1995 was 14.8 million.",
            "Her daughter needed medicine, and Jill needed a miracle.",
            "Venison is a phrase that relates to deer meat, which is a type of red meat.",
            "Venison is a phrase that relates to deer meat, which is a type of red meat, and which is sold in the market.",
            "If the cache saves time, the queue saves work, and the service stays available when a worker restarts.",
            "The worker reads the queue, writes the record, and waits for the next scheduled job to arrive.",
            "The API supports long names, short names for aliases, and names imported from the local configuration file.",
            "The cache saves time, the queue records work, and the service stays available when a worker restarts.",
            "Days turned into weeks, weeks into months, and the memory of that fleeting connection remained etched in their hearts.",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual([], self.lint(" ".join([text] * 2)))

    def test_masked_examples_do_not_count(self):
        text = "\n".join((ORIGINAL, CLAUDE, GPT))
        for masked in (f"```text\n{text}\n```", f"<!-- {text} -->", f"`{ORIGINAL}`\n\n`{CLAUDE}`"):
            with self.subTest(masked=masked):
                self.assertEqual([], self.lint(masked))
        self.assertEqual([], self.lint(ORIGINAL + "\n\n```text\n" + CLAUDE + "\n```"))
        quoted = "\n".join(f"> {sentence}" for sentence in (ORIGINAL, CLAUDE))
        engine = Engine([self.rule])
        engine._nlp = self.nlp
        self.assertEqual([], engine.lint_deterministic(build_document("quoted.md", quoted, skip_quotes=True)))

    def test_parser_stays_lazy_without_recurrence(self):
        engine = Engine([self.rule])
        engine._nlp = Mock()
        engine._nlp.pipe.side_effect = AssertionError("unnecessary parsing")
        text = " ".join([ORIGINAL] + [FILLER] * 3)
        self.assertEqual([], engine.lint_deterministic(build_document("short.md", text)))
        engine._nlp.pipe.assert_not_called()

    def test_backreference_examples_and_shared_subject(self):
        for text in self.reference.example:
            with self.subTest(text=text):
                self.assertEqual(1, len(self.lint(text, self.reference)))
        for text in self.reference.acceptable:
            with self.subTest(text=text):
                self.assertEqual([], self.lint(text, self.reference))
        image = "[Jev](https://example.com) is the one exception, and it stays outside the core: it answers typed questions."
        self.assertEqual(1, len(self.lint(image, self.reference)))
        self.assertEqual([], self.lint('`' + self.reference.example[0] + '`', self.reference))

    def test_backreference_after_another_paragraph(self):
        text = "The first paragraph ends here.\n\n" + self.reference.example[0]
        finding, = self.lint(text, self.reference)
        self.assertEqual(text.index("Those"), finding.start)


if __name__ == "__main__":
    unittest.main()
