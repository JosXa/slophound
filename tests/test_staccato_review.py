"""Independent regression checks for staccato advisory false positives."""
import unittest
from hound.engine import Engine
from hound.loader import load_rules
from hound.masking import build_document


class StaccatoReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rules = [r for r in load_rules() if r.id == "doc.staccato-beats"]
        assert len(rules) == 1
        cls.engine = Engine(rules)

    def test_card_reader_instructions_are_not_beats(self):
        text = "Follow these steps to configure your card reader. Insert the card. Press Start. Select English. Enter your PIN."
        self.assertEqual([], self.engine.lint_deterministic(build_document("test.md", text)))

    def test_quoted_slogan_does_not_count(self):
        for left, right in [('"', '"'), ('“', '”')]:
            text = f"The reviewer cited a slogan as an example. {left}Safe. Food. Easy. Simple.{right} We removed the slogan from the document."
            with self.subTest(left=left):
                self.assertEqual([], self.engine.lint_deterministic(build_document("test.md", text)))

    def test_soft_wrapped_quoted_slogan_does_not_count(self):
        text = 'The reviewer cited a slogan as an example. "Safe.\nFood.\nEasy.\nSimple." We removed the slogan from the document.'
        self.assertEqual([], self.engine.lint_deterministic(build_document("test.md", text)))


if __name__ == "__main__":
    unittest.main()
