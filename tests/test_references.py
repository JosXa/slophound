"""Synthetic reference probes, not independently collected corpus evidence."""
import unittest

from hound.engine import Engine
from hound.loader import load_rules, _build_rule, RuleError
from hound.masking import build_document
from pathlib import Path


CASES = {
    'phrase.orphan-demonstrative-verdict': [
        'This is necessary.', 'That was useful.', 'These are essential.',
        'Those were effective.', 'This is problematic.',
    ],
    'phrase.orphan-demonstrative-consequence': [
        'This causes delays.', 'That prevents recovery.',
        'These reduce latency.', 'Those increase costs.',
    ],
    'phrase.orphan-demonstrative-abstraction': [
        'This approach requires coordination.', 'That strategy relies on retries.',
        'These mechanisms support recovery.', 'Those principles guide deployment.',
    ],
    'phrase.orphan-definite-abstraction': [
        'The approach requires coordination.', 'The strategy depends on retries.',
        'The framework supports recovery.', 'The tradeoff affects availability.',
        'The solution assumes reliable delivery.', 'The mechanism prevents races.',
        'The system requires coordination.', 'The configuration supports recovery.',
        'The change reduces latency.', 'The design depends on retries.',
        'The decision affects availability.',
    ],
    'phrase.orphan-reference-comparison': [
        'Unlike this, the queue persists messages.',
        'Compared with that, the queue is slower.',
        'In contrast to these, the workers are stateless.',
        'Unlike those, the queue preserves order.',
    ],
    'verb.demonstrative-enables': [
        'This enables teams to ship faster.', 'That allows workers to retry.',
        'These ensure consistency.', 'Those allow recovery.',
    ],
}


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()
        cls.engine = Engine([r for r in cls.rules if r.id in CASES])

    def lint(self, text, rid=None, skip_quotes=False):
        engine = self.engine if rid is None else Engine([r for r in self.rules if r.id == rid])
        engine._nlp = self.engine.nlp
        return engine.lint_deterministic(
            build_document('references.md', text, skip_quotes=skip_quotes))

    def test_preceding_quotes_remain_reader_context_when_skipped(self):
        for rid, examples in CASES.items():
            for sentence in examples:
                for skip_quotes in (False, True):
                    with self.subTest(rid=rid, sentence=sentence, skip_quotes=skip_quotes):
                        self.assertEqual([], self.lint(
                            '> A queue stores messages.\n\n' + sentence,
                            rid, skip_quotes=skip_quotes))

    def test_hidden_quotes_do_not_supply_reader_context(self):
        contexts = [
            '<!--\n> A queue stores messages.\n-->\n\n',
            '---\nclass: "> A queue stores messages."\n---\n\n',
        ]
        for rid, examples in CASES.items():
            for context in contexts:
                for skip_quotes in (False, True):
                    with self.subTest(rid=rid, context=context, skip_quotes=skip_quotes):
                        self.assertEqual([rid], [f.rule.id for f in self.lint(
                            context + examples[0], rid, skip_quotes=skip_quotes)])

    def test_registered_advisory_families(self):
        self.assertEqual(set(CASES), {r.id for r in self.engine.rules})
        self.assertTrue(all(r.severity == 'bark' for r in self.engine.rules))

    def test_opening_positives_solo_and_combined(self):
        for rid, examples in CASES.items():
            for text in examples:
                with self.subTest(rid=rid, text=text):
                    self.assertEqual([rid], [f.rule.id for f in self.lint(text, rid)])
                    self.assertEqual([rid], [f.rule.id for f in self.lint(text)])

    def test_previous_context_preserves_synonyms_and_bridging(self):
        for examples in CASES.values():
            for sentence in examples:
                for context in [
                    'A queue stores messages. ',
                    'A queue stores messages.\n\n',
                    '# Durable delivery\n\n',
                    '- A queue stores messages.\n\n',
                    'The broker acknowledges each write.\n\nA replica retains it.\n\n',
                ]:
                    with self.subTest(sentence=sentence, context=context):
                        self.assertEqual([], self.lint(context + sentence))

    def test_layout_quotes_and_code_are_not_assertions(self):
        for examples in CASES.values():
            for sentence in examples:
                for text in [f'# {sentence}', f'- {sentence}', f'1. {sentence}',
                             f'> {sentence}', f'"{sentence}"', f'“{sentence}”',
                             f'`{sentence}`', f'```text\n{sentence}\n```',
                             f'"{sentence} Another sentence."',
                             f'“{sentence}\nAnother sentence.”']:
                    with self.subTest(text=text):
                        self.assertEqual([], self.lint(text))

    def test_explicit_references_definitions_and_literal_directives(self):
        for text in [
            'This queue enables retries.', 'That flag allows retries.',
            'This approach to retries requires a queue.',
            'The strategy for durable delivery depends on replication.',
            'The retry mechanism prevents races.',
            'The framework described in RFC 7231 supports caching.',
            'The approach is to persist every message.',
            'This is necessary because the broker may restart.',
            'This is necessary: persist every message before acknowledging it.',
            'This is necessary to recover unacknowledged messages.',
            'These are the messages awaiting acknowledgement.',
            'That is, the broker retries the write.',
            'This causes delays when the queue is full.',
            'Select this option.', 'Delete those files.', 'Restart the process.',
            'The sun rises at six.', 'The database stores messages.',
            'This document describes the retry mechanism.',
            'Unlike this queue, the worker forgets completed jobs.',
            'Compared with that implementation, the queue is slower.',
        ]:
            with self.subTest(text=text):
                self.assertEqual([], self.lint(text))

    def test_offsets_reflow_and_document_builder(self):
        for rid, examples in CASES.items():
            text = examples[0]
            for rendered in [text, text.replace(' ', '\n', 1), '\n\n' + text,
                             '**' + text.split()[0] + '**' + text[len(text.split()[0]):]]:
                with self.subTest(rid=rid, rendered=rendered):
                    doc = build_document('probe.md', rendered)
                    self.assertEqual(len(rendered), len(doc.prose))
                    self.assertEqual(['paragraph'], [b.kind for b in doc.blocks])
                    findings = self.lint(rendered, rid)
                    self.assertEqual(1, len(findings))
                    finding = findings[0]
                    self.assertGreater(finding.end, finding.start)
                    self.assertIn(rendered[finding.start:finding.end].split()[0].strip('*'),
                                  text.split()[0:2])
                    self.assertEqual(rendered.index(text.split()[0]), finding.start)

    def test_benefit_explanation_and_relative_pronoun(self):
        for text in ['This enables retries because every write is persisted.',
                     'This ensures recovery: the broker persists every write.',
                     'Which enables retries?']:
            with self.subTest(text=text):
                self.assertEqual([], self.lint(text, 'verb.demonstrative-enables'))

    def test_rendered_context_is_preserved(self):
        contexts = [
            '```python\nqueue.persist(message)\n```\n\n',
            '`queue.persist(message)`\n\n',
            '```text\nvisible context\n<!-- note -->\n```\n\n',
            '```html\n<!-- note -->\n```\n\n',
            '`<!-- note -->`\n\n',
            '| Policy | Setting |\n| --- | --- |\n| Retry | Three attempts |\n\n',
            '[Durable Delivery](https://example.org)\n\n',
            'https://example.org/delivery\n\n',
        ]
        for context in contexts:
            for rid, examples in CASES.items():
                with self.subTest(context=context, rid=rid):
                    self.assertEqual([], self.lint(context + examples[0], rid))

    def test_hidden_content_is_not_reference_context(self):
        contexts = [
            '<!-- `queue.persist(message)` -->\n\n',
            '<!-- [Durable Delivery](https://example.org) -->\n\n',
            '---\nclass: "`retry`"\n---\n\n',
        ]
        for context in contexts:
            with self.subTest(context=context):
                findings = self.lint(context + 'This prevents data loss.')
                self.assertEqual(['phrase.orphan-demonstrative-consequence'],
                                 [f.rule.id for f in findings])

    def test_reference_gate_validation(self):
        raw = dict(id='phrase.test', severity='bark', message='Name the referent.',
                   pattern='this', example=['this'], acceptable=['queue'], opening_reference='yes')
        with self.assertRaises(RuleError):
            _build_rule(raw, 'phrase', Path('test.toml'))


if __name__ == '__main__':
    unittest.main()
