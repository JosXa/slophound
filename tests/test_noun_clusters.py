"""Keep parser corrections local to a candidate noun cluster."""

import unittest

from hound.engine import Engine
from hound.loader import load_rules
from hound.masking import build_document


class NounClusterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine([r for r in load_rules() if r.category == "noun"])

    def test_participle_correction_keeps_other_cluster_in_sentence(self):
        text = (
            "CSV releases contain text, a binary label, and source information encoding domain, "
            "generation method, and model; the build cache eviction policy changed."
        )
        findings = self.engine.lint_deterministic(build_document("mixed.md", text))
        self.assertEqual(["noun.cluster-four"], [f.rule.id for f in findings])
        self.assertEqual("build cache eviction policy", text[findings[0].start:findings[0].end])

    def test_lexical_correction_keeps_other_cluster_in_paragraph(self):
        text = (
            "Deduplicate against HC3 and other components before combining corpora. "
            "Scraped responses and incomplete component documentation weaken attribution. "
            "The build cache eviction policy changed."
        )
        findings = self.engine.lint_deterministic(build_document("mixed.md", text))
        self.assertEqual(["noun.cluster-four"], [f.rule.id for f in findings])
        self.assertEqual("build cache eviction policy", text[findings[0].start:findings[0].end])


if __name__ == "__main__":
    unittest.main()
