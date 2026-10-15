"""Contrast variants and verification caveats from the user's session history."""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

from hound.engine import Engine
from hound.loader import load_rules
from hound.masking import build_document


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "research" / "contrastive-scope"
RULE_IDS = {
    "template.is-a-x-not-a-y",
    "template.evidence-scope-contrast",
    "template.residual-verification",
}


class ContrastiveScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = [rule for rule in load_rules() if rule.id in RULE_IDS]
        cls.engine = Engine(cls.rules)

    def findings(self, text):
        return self.engine.lint_deterministic(build_document("example.md", text))

    def test_all_five_user_seeds_fail(self):
        for line in (STUDY / "seeds.jsonl").read_text().splitlines():
            text = json.loads(line)["text"]
            with self.subTest(text=text):
                self.assertTrue(self.findings(text))
                self.assertTrue(all(f.severity == "bite" for f in self.findings(text)))

    def test_subjects_contractions_and_article_free_complements(self):
        for subject in (
            "It is", "It's", "It’s", "They are", "They're", "They’re",
            "These are", "Those were", "We are", "We're", "You're",
            "These callbacks are", "Those results were",
        ):
            text = f"{subject} separate measurements, not a combined run."
            with self.subTest(subject=subject):
                self.assertTrue(self.findings(text))

    def test_plural_predicates_and_evidence_verbs(self):
        for positive, negative in (
            ("This supports", "It does not independently validate"),
            ("Those establish", "They do not prove"),
            ("That confirmed", "It did not establish"),
            ("These demonstrate", "They don't guarantee"),
        ):
            text = f"{positive} the registered prediction. {negative} browser parity."
            with self.subTest(text=text):
                self.assertTrue(self.findings(text))

    def test_wrapping_and_exact_offsets(self):
        text = "The runner stopped. These are separate\nresults, not one run. Recovery remains\nuntested."
        findings = self.findings(text)
        self.assertEqual(
            ["These are separate\nresults, not", "remains\nuntested"],
            [text[f.start:f.end] for f in findings],
        )

    def test_does_not_join_separate_paragraphs(self):
        for text in (
            "These are separate results.\n\nThis is not a combined run.",
            "These are\n\nseparate results, not one run.",
            "This establishes the local result.\n\nIt does not establish browser parity.",
            "- This establishes the local result.\n- It does not establish browser parity.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_honest_rewrites_and_literal_controls(self):
        for text in (
            "These results came from separate runs. I did not test recovery.",
            "The value is a string, not a number, so the comparison fails.",
            "The lock, not the cache, causes the stall.",
            "The logs do not establish which request acquired the lock.",
            "This establishes a connection. It does not validate user input.",
            "I did not test physical display parity because the fixture was unavailable.",
            "The cause remains unclear because the log omits the lock owner.",
            "This RFC only supports the platform's native ABI, not any other ABI.",
            "The registry that can support older versions does not validate the index.",
            "These are concrete types, not variables.",
            "This is big churn on a major feature, not long before 1.0.",
            "It's nice as a user, too, not to need an additional type.",
            "This is another difference: the implementation owns the conversion, not the caller.",
            "This is not a nice solution: it requires a standard-library trait, not language support.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_code_and_optional_blockquote_masking(self):
        for text in (
            '`They are results, not a timing pass.`',
            '```text\nRecovery remains untested.\n```',
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))
        quote = "> These are results, not a timing pass."
        self.assertEqual([], self.engine.lint_deterministic(
            build_document("example.md", quote, skip_quotes=True),
        ))

    def test_corpus_has_eighty_additional_distinct_examples(self):
        records = [json.loads(line) for line in (STUDY / "corpus.jsonl").read_text().splitlines()]
        examples = [record for record in records if record["usage"] == "example"]
        self.assertGreaterEqual(len(examples), 80)
        self.assertEqual(len(records), len({record["id"] for record in records}))
        for record in records:
            with self.subTest(id=record["id"]):
                self.assertRegex(record["session_id"], r"^ses_")
                self.assertRegex(record["message_id"], r"^msg_")
                self.assertEqual(len(record["text"]), record["end"] - record["start"])
                key = re.sub(r"\s+", " ", record["text"]).strip()
                self.assertEqual(hashlib.sha256(key.encode()).hexdigest()[:12], record["id"])

    def test_collector_excludes_user_and_tool_text_and_deduplicates(self):
        spec = importlib.util.spec_from_file_location("collect_contrasts", STUDY / "collect.py")
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)
        text = "Recovery remains untested."
        messages = [
            {"id": "msg_user", "role": "user", "parts": [{"type": "text", "text": text}]},
            {"id": "msg_tool", "role": "assistant", "parts": [{"type": "tool", "output": text}]},
            {"id": "msg_real", "role": "assistant", "sourceId": "v2", "parts": [{"type": "text", "text": "First.\n\n" + text}]},
            {"id": "msg_copy", "role": "assistant", "sourceId": "v2", "parts": [{"type": "text", "text": text}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ses_test.jsonl"
            path.write_text("".join(json.dumps(message) + "\n" for message in messages))
            records = collector.collect(Path(directory))
        self.assertEqual(1, len(records))
        self.assertEqual("msg_real", records[0]["message_id"])
        self.assertEqual(8, records[0]["start"])
        self.assertEqual(text, records[0]["text"])


if __name__ == "__main__":
    unittest.main()
