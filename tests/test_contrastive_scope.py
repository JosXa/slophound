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
    "template.contrastive-negation",
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

    def test_operator_review_of_missed_constructions(self):
        records = {json.loads(line)["id"]: json.loads(line) for line in
                   (STUDY / "corpus.jsonl").read_text().splitlines()}
        for line in (STUDY / "operator-review.jsonl").read_text().splitlines():
            case = json.loads(line)
            with self.subTest(number=case["number"]):
                self.assertIn(case["text"], records[case["corpus_id"]]["text"])
                findings = self.findings(case["text"])
                # The subsequent operator decision bans every reviewed contrast,
                # superseding the original acceptable/borderline judgments.
                self.assertEqual(["bite"], [f.severity for f in findings])
                self.assertTrue(self.findings(records[case["corpus_id"]]["text"]))
                if case["number"] == 10:
                    rule = next(r for r in load_rules() if r.id == "punct.semicolon-splice")
                    self.assertTrue(Engine([rule]).lint_deterministic(
                        build_document("example.md", case["text"])))

    def test_reviewed_constructions_generalize_and_wrap(self):
        for text in (
            "The saved report was a baseline, not evidence of current readiness.",
            "The checks are the initial scope, not exhaustive coverage.",
            "The list below is the minimum\nscope, not the complete checklist.",
            "The recorded measurements confirm crop timing, but they do not prove picture parity.",
            "The evidence supports continuous crop\nevaluation, but matching that clock does not prove picture parity.",
        ):
            with self.subTest(text=text):
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
            ["These are separate\nresults, not one run.", "remains\nuntested"],
            [text[f.start:f.end] for f in findings],
        )

    def test_does_not_join_separate_paragraphs(self):
        for text in (
            "These are separate results.\n\nThis is not a combined run.",
            "This establishes the local result.\n\nIt does not establish browser parity.",
            "- This establishes the local result.\n- It does not establish browser parity.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_honest_rewrites_and_literal_controls(self):
        for text in (
            "These results came from separate runs. I did not test recovery.",
            "The logs do not establish which request acquired the lock.",
            "I did not test physical display parity because the fixture was unavailable.",
            "The cause remains unclear because the log omits the lock owner.",
            "The registry that can support older versions does not validate the index.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_all_operator_approved_factual_corrections_are_bites(self):
        for text in (
            "The timeout is measured in milliseconds, not seconds.",
            "This command deletes the local branch, not the remote branch.",
            "The function returns a copy, not a reference.",
            "The permission applies to this folder, not its descendants.",
            "The invoice total is €120, not €120 per user.",
            "The lock, not the cache, causes the stall.",
            "The test confirms that expired tokens are rejected, but does not check revoked tokens.",
            "The backup completed, but restoration has not been tested.",
        ):
            with self.subTest(text=text):
                self.assertEqual(["bite"], [f.severity for f in self.findings(text)])

    def test_content_words_do_not_determine_matching(self):
        for subject in ("The frobnicator", "Zephyrs", "A red widget", "They"):
            for verb in ("emits", "recombines", "sketches", "returns"):
                for text in (
                    f"{subject} {verb} amber, not cobalt.",
                    f"{subject} {verb} amber but cannot tessellate cobalt.",
                    f"{subject} {verb} amber; the cobalt has not tessellated.",
                    f"{subject} {verb} amber. It doesn't tessellate cobalt.",
                    f"{subject} does not tessellate cobalt but {verb} amber.",
                ):
                    with self.subTest(text=text):
                        self.assertEqual(["bite"], [f.severity for f in self.findings(text)])

    def test_negation_without_a_paired_contrast_passes(self):
        for text in (
            "Do not deploy before the restore test passes.",
            "The lock is not held.",
            "The lock is small but reliable.",
            "The lock is small but reliable. The cache does not retain errors.",
            "Not all requests require a lock.",
            "We haven't tested restoration because the backup is still running.",
            "The query contains `not`, but it completes.",
            "The identifier is button, the field is notification.",
            "Sources report unavailable, not-generated-output, or gated status.",
            "The bureau does not yet have data, although the outlook is positive.",
            "The job finished. It appears that the cache is not empty.",
            "Tighten the bolts, don't strip the thread.",
            "The service responds (but slowly), and the cache does not retain failures.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_surface_construction_needs_no_statistical_parser(self):
        engine = Engine([r for r in self.rules if r.construction])
        engine.lint_deterministic(build_document("example.md", "Widgets emit amber, not cobalt."))
        self.assertIsNone(engine._nlp)

    def test_introductory_adverbs_do_not_supply_an_alternative(self):
        for text in (
            "Therefore, not every person is capable of performing the functions of a supervisor.",
            "Consequently, not all requests reach the worker.",
            "Unfortunately, not every backup can be restored.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_supplementary_participles_describe_the_subject(self):
        for text in (
            "The reptiles, not knowing what to, simply watched along with the crowd as a giant holoscreen appread in the sky.",
            "The worker, not receiving a response, tried again.",
            "The guards, not recognizing the visitor, quietly closed the gate.",
            "She, not having a key, waited outside.",
            "The worker, not receiving a response, waited but stayed calm.",
            "The worker, not\nreceiving a response,\ntried again.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_negated_cessation_asserts_continuation(self):
        for text in (
            "I may be a demon, Ascalon, but I never stopped being Uriel.",
            "She moved away, but she never stopped caring about them.",
            "The interface changed, but it has not stopped serving requests.",
            "The device is old, but it never ceased to function.",
            "The storm ended. It never stopped raining in the hills.",
        ):
            with self.subTest(text=text):
                self.assertEqual([], self.findings(text))

    def test_similar_constructions_still_reject_alternatives(self):
        for text in (
            "Quickly, not slowly, turn the handle.",
            "Today, not tomorrow, is the deadline.",
            "The worker is waiting, not receiving a response.",
            "Waiting, not receiving, consumed the time.",
            "The recording, not the broadcast, contains the error.",
            "This may prove extraction, but it does not validate recovery.",
            "The process finished, but it never stopped the worker.",
            "The service is live, but it never stopped crashing and it cannot validate signatures.",
            "The worker, not receiving a response, tried again, not once but twice.",
            "It never stopped working, but it does not validate recovery.",
            "The device is old, but it never stopped not responding.",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.findings(text))

    def test_human_findings_are_assertions_not_suppressions(self):
        from unittest.mock import patch
        from hound import selftest

        text = "The timeout uses milliseconds, not seconds."
        entry = {"rule": "template.contrastive-negation", "text": text}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "generated").mkdir()
            (root / "human").mkdir()
            (root / "generated" / "example.md").write_text(text)
            human = root / "human" / "example.md"
            human.write_text(text)
            expected = root / "human-findings.json"
            expected.write_text(json.dumps({"example.md": [entry]}))
            with patch.object(selftest, "CORPUS", root):
                self.assertEqual([], selftest.check_corpus(self.engine))
                human.write_text("The timeout uses milliseconds.")
                self.assertTrue(any("missing reviewed" in p for p in selftest.check_corpus(self.engine)))
                human.write_text(text + "\n\nWidgets emit amber, not cobalt.")
                self.assertTrue(any("unexpected human" in p for p in selftest.check_corpus(self.engine)))

    def test_construction_loader_rejects_ambiguous_configuration(self):
        from hound.loader import _build_rule, RuleError

        raw = dict(id="template.test", severity="bite", message="Test.",
                   example=["A, not B."], acceptable=["A."],
                   construction="contrastive-negation")
        for extra in ({"pattern": "not"}, {"unless": "type"},
                      {"sentence_start": True}, {"opening_reference": True},
                      {"construction": "unknown"}):
            with self.subTest(extra=extra), self.assertRaises(RuleError):
                _build_rule(raw | extra, "template", Path("test.toml"))

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
