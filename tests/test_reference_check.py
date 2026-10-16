"""Offline constructed probes; semantic controls use labelled fake answers."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from hound import reference_check as references
from hound.engine import Engine
from hound.loader import load_rules
from hound.masking import build_document
from hound.layer_spacy import load_model


class ReferenceCandidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nlp = load_model('en')

    def collect(self, text, **kwargs):
        collect = getattr(references, 'collect_reference_paragraphs', None)
        self.assertIsNotNone(collect, 'paragraph reference collection is missing')
        return collect(build_document('probe', text, **kwargs), self.nlp)

    def test_privacy_edge_cases(self):
        import json
        rule = next(r for r in load_rules() if r.id == 'noun.unclear-reference')
        cases = [
            '<!-- PRIVATE_SENTINEL ` --> A queue uses `writes`.\n\nThis works.',
            '<span data-note = "PRIVATE_SENTINEL `">A queue</span> uses `writes`.\n\nThis works.',
            '<script type = "application/json">PRIVATE_SENTINEL</script>\n\nThis works.',
            '<style>PRIVATE_SENTINEL</style>\n\nThis works.',
            '---\napi_key: PRIVATE_SENTINEL\n\nprivate_notes: PRIVATE_SENTINEL\n---\n\nThis works.',
            '---\n# PRIVATE_SENTINEL\napi_key: PRIVATE_SENTINEL\n---\n\nThis works.',
            '---\ntitle: Public heading # PRIVATE_SENTINEL\n---\n\nThis works.',
            "---\ntitle: The worker's queue # PRIVATE_SENTINEL\n---\n\nThis works.",
            '---\ntitle: A 6" pipe # PRIVATE_SENTINEL\n---\n\nThis works.',
            '[docs]: https://example.invalid/PRIVATE_SENTINEL\n\nThis works.',
            '[docs](https://example.invalid/foo(bar)/PRIVATE_SENTINEL)\n\nThis works.',
            '<script>\n# PRIVATE_SENTINEL\n</script>\n\nThis works.',
            'A queue stores writes.\n\n<!-- PRIVATE_SENTINEL without closing',
        ]
        for text in cases:
            with self.subTest(text=text):
                view = references.reader_visible(build_document('probe', text))
                self.assertEqual(len(view), len(text))
                self.assertEqual(view.count('\n'), text.count('\n'))
                self.assertNotIn('PRIVATE_SENTINEL', view)
                for row in self.collect(text):
                    self.assertNotIn('PRIVATE_SENTINEL', row.heading)
                    if row.status == 'pending' and row.candidates:
                        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(references.reference_request(row, rule, [0])))

    def test_quoted_yaml_hashes_and_reader_offsets_are_preserved(self):
        values = [
            "'The worker''s # queue'",
            '"A \\"quoted\\" # queue"',
        ]
        for value in values:
            with self.subTest(value=value):
                text = f'---\ntitle: {value} # PRIVATE_SENTINEL\n---\n\nThis works.'
                view = references.reader_visible(build_document('probe', text))
                start = text.index(value)
                self.assertEqual(view[start:start + len(value)], value)
                self.assertNotIn('PRIVATE_SENTINEL', view)
                self.assertEqual(len(view), len(text))
                self.assertEqual([i for i, c in enumerate(view) if c == '\n'],
                                 [i for i, c in enumerate(text) if c == '\n'])
                row = self.collect(text)[-1]
                self.assertIn(value, row.preceding_context)
                self.assertFalse(row.context_truncated)
                candidate = row.candidates[0]
                self.assertEqual(candidate.start, text.index('This'))
                self.assertEqual(text[candidate.start:candidate.end], 'This')

    def test_indented_literal_comments_are_reader_context(self):
        rows = self.collect('    <!-- A queue stores writes -->\n\nThis works.')
        self.assertIn('<!-- A queue stores writes -->', rows[-1].preceding_context)
        self.assertEqual([c.text for row in rows for c in row.candidates], ['This'])

    def test_unsupported_rendered_yaml_marks_context_incomplete(self):
        row = self.collect('---\ntitle: |\n  A queue stores writes\n---\n\nThis works.')[-1]
        self.assertTrue(row.context_truncated)

    def test_indented_code_is_context_not_target(self):
        rows = self.collect('    The system runs.\n\nThis works.')
        self.assertEqual([c.text for row in rows for c in row.candidates], ['This'])
        self.assertIn('The system runs', rows[-1].preceding_context)

    def test_possessives_and_escaped_quotes_are_not_targets(self):
        cases = [
            '"Use \\"the system\\" here" This works.',
            "'The worker's queue stores writes.' This works.",
            "'The workers' queue stores writes.' This works.",
            "'The queue doesn't drain.' This works.",
            '“The worker’s queue stores writes.” This works.',
        ]
        for text in cases:
            with self.subTest(text=text):
                rows = self.collect(text)
                candidates = [c for row in rows for c in row.candidates]
                self.assertEqual([c.text for c in candidates], ['This'])
                self.assertEqual(candidates[0].start, text.index('This'))
                self.assertIn('queue' if 'queue' in text else 'system', rows[0].paragraph)

    def test_empty_hidden_heading_falls_back(self):
        row = self.collect('# Public heading\n\n# <!-- hidden --> ##\n\nThis works.')[-1]
        self.assertEqual(row.heading, 'Public heading')

    def test_heading_does_not_hide_candidates(self):
        text = '# Request latency metrics\n\nRecord request durations in the histogram. The monitoring system computes p95.'
        rows = self.collect(text)
        self.assertEqual([c.text for c in rows[0].candidates], ['the histogram', 'The monitoring system'])
        self.assertEqual(rows[0].heading, 'Request latency metrics')
        self.assertEqual(rows[0].paragraph, text.split('\n\n')[1])

    def test_antecedents_forward_explanations_and_generic_uses_are_candidates(self):
        for text in ('Create a histogram. The histogram stores durations.',
                     'This works: a queue serializes writes.',
                     'The sun heats the Earth.',
                     'These changes help. That works. Those fail.'):
            with self.subTest(text=text):
                self.assertTrue(self.collect(text)[0].candidates)

    def test_only_ordinary_paragraphs_are_targets(self):
        prefix = '# The heading\n\n> This is quoted.\n\n```\nThe system\n```\n\n| The table |\n| --- |\n\n- This is listed.\n\n'
        rows = self.collect(prefix + 'This works.')
        self.assertEqual(len(rows), 1)
        self.assertEqual([c.text for c in rows[0].candidates], ['This'])
        self.assertIn('The system', rows[0].preceding_context)
        self.assertIn('This is quoted', rows[0].preceding_context)
        self.assertIn('The table', rows[0].preceding_context)

    def test_quote_context_survives_skip_quotes(self):
        row = self.collect('> A queue serializes writes.\n\nThis works.', skip_quotes=True)[0]
        self.assertIn('A queue serializes writes', row.preceding_context)

    def test_hidden_comments_and_machine_metadata_are_not_context(self):
        text = '---\nclass: the monitoring system\n---\n\n<!-- the histogram -->\n\nThis works.'
        row = self.collect(text)[0]
        self.assertEqual(row.preceding_context.strip(), '')
        self.assertEqual(row.paragraph, 'This works.')

    def test_comment_syntax_in_rendered_code_is_context(self):
        row = self.collect('```\n<!-- the queue -->\n```\n\nThis works.')[0]
        self.assertIn('<!-- the queue -->', row.preceding_context)
        row = self.collect('`<!-- the queue -->`\n\nThis works.')[0]
        self.assertIn('<!-- the queue -->', row.preceding_context)

    def test_hidden_comment_cannot_wrap_code_into_context(self):
        row = self.collect('<!--\n```\nthe queue\n```\n-->\n\nThis works.')[0]
        self.assertEqual(row.preceding_context.strip(), '')

    def test_strict_character_boundary_and_unicode_offsets(self):
        for length in (299, 300):
            text = 'This works. ' + 'x' * (length - len('This works. '))
            rows = self.collect(text)
            self.assertEqual(rows[0].status, 'pending' if length == 299 else 'skipped_length')
            self.assertEqual(bool(rows[0].candidates), length == 299)
        text = '# Café 🚀\n\nÉlodie checks the queue.'
        row = self.collect(text)[0]
        c = row.candidates[0]
        self.assertEqual(text[c.start:c.end], 'the queue')

    def test_bounded_context_reports_truncation(self):
        row = self.collect('a' * 5000 + '\n\nThis works.')[1]
        self.assertLessEqual(len(row.preceding_context), 2000)
        self.assertTrue(row.context_truncated)

    def test_inline_quotes_are_context_not_targets(self):
        row = self.collect('“The queue stores writes.” This works.')[0]
        self.assertEqual([c.text for c in row.candidates], ['This'])
        self.assertIn('The queue stores writes', row.paragraph)

    def test_hidden_text_inside_paragraph_never_enters_request(self):
        row = self.collect('This <!-- SECRET --> works.')[0]
        self.assertNotIn('SECRET', row.paragraph)
        self.assertEqual(row.candidates[0].text, 'This')

    def test_rendered_field_is_context_not_target(self):
        row = self.collect('---\nheading: A queue stores writes\nclass: SECRET value\n---\n\nThis works.')[0]
        self.assertIn('A queue stores writes', row.preceding_context)
        self.assertNotIn('SECRET', row.preceding_context)

    def test_unknown_front_matter_is_not_assumed_reader_visible(self):
        row = self.collect('---\napi_key: DO NOT SEND\nprivate_notes: KEEP HIDDEN\n---\n\nThis works.')[0]
        self.assertNotIn('DO NOT SEND', row.preceding_context)
        self.assertNotIn('KEEP HIDDEN', row.preceding_context)

    def test_complementizer_that_is_not_a_reference(self):
        self.assertFalse(self.collect('We know that requests fail.')[0].candidates)


class ReferenceJudgments(ReferenceCandidates):
    def rule(self):
        rules = [r for r in load_rules() if r.id == 'noun.unclear-reference']
        self.assertEqual(len(rules), 1, 'reference rule metadata is missing')
        return rules[0]

    def evaluate(self, text, answers, *, model='jev-1.13.0', enabled=True, error=False):
        rows = self.collect(text)
        calls = []
        class Client:
            def evaluate(self, **kwargs):
                calls.append(kwargs)
                if error:
                    raise RuntimeError('offline failure')
                return SimpleNamespace(model=model, choices=answers)
        client = Client()
        client.enabled = enabled
        evaluate = getattr(references, 'evaluate_reference_paragraphs', None)
        self.assertIsNotNone(evaluate, 'paragraph reference judgment is missing')
        findings, outcomes = evaluate(rows, self.rule(), client)
        return findings, outcomes, calls

    @staticmethod
    def answer(choice, confidence=.95, **overrides):
        fields = dict(type='choice', choice=choice, confidence=confidence,
                      probabilities={label: .96 if label == choice else .02 for label in ('clear', 'unclear', 'uncertain')})
        fields.update(overrides)
        return SimpleNamespace(**fields)

    def test_mixed_clear_and_unclear_in_same_paragraph(self):
        text = 'Create a histogram. The histogram stores durations. The monitoring system computes p95.'
        findings, outcomes, calls = self.evaluate(text, {'reference_0': self.answer('clear'), 'reference_1': self.answer('unclear')})
        self.assertEqual([text[f.start:f.end] for f in findings], ['The monitoring system'])
        self.assertEqual([o['status'] for o in outcomes], ['clear', 'unclear'])
        self.assertEqual(calls[0]['state']['paragraph'], text)
        self.assertEqual(len(calls[0]['questions']), 2)
        self.assertEqual(calls[0]['questions']['reference_0']['type'], 'choice')

    def test_semantic_controls_can_be_clear(self):
        for text in ('Create a queue. The queue serializes writes.',
                     'This works: a queue serializes writes.', 'The sun heats Earth.'):
            with self.subTest(text=text):
                findings, outcomes, calls = self.evaluate(text, {'reference_0': self.answer('clear')})
                self.assertEqual(findings, [])
                self.assertEqual(outcomes[0]['status'], 'clear')
                self.assertIn('generic', calls[0]['questions']['reference_0']['criteria']['clear'].lower())

    def test_abstentions_do_not_claim_clarity(self):
        cases = [({}, 'missing_answer'),
                 ({'reference_0': self.answer('uncertain')}, 'uncertain'),
                 ({'reference_0': self.answer('unclear', .79)}, 'low_confidence'),
                 ({'reference_0': self.answer('unclear', True)}, 'invalid_answer'),
                 ({'reference_0': self.answer('unclear', float('nan'))}, 'invalid_answer'),
                 ({'reference_0': self.answer('unknown')}, 'invalid_answer'),
                 ({'reference_0': self.answer('unclear', probabilities={})}, 'invalid_answer'),
                 ({'reference_0': self.answer('unclear', probabilities={'clear': .96, 'unclear': .02, 'uncertain': .02})}, 'invalid_answer')]
        for answers, status in cases:
            with self.subTest(status=status):
                findings, outcomes, _ = self.evaluate('This works.', answers)
                self.assertEqual(findings, [])
                self.assertEqual(outcomes[0]['status'], status)

    def test_confidence_floor_is_inclusive(self):
        findings, _, _ = self.evaluate('This works.', {'reference_0': self.answer('unclear', .8)})
        self.assertEqual(len(findings), 1)

    def test_missing_key_errors_and_model_mismatch(self):
        for kwargs, status in (({'enabled': False}, 'missing_key'),
                               ({'error': True}, 'request_failed'),
                               ({'model': 'jev-latest'}, 'model_mismatch')):
            findings, outcomes, calls = self.evaluate('This works.', {'reference_0': self.answer('unclear')}, **kwargs)
            self.assertEqual(findings, [])
            self.assertEqual(outcomes[0]['status'], status)
            if not kwargs.get('enabled', True):
                self.assertFalse(calls)

    def test_long_paragraph_is_skipped_without_request(self):
        findings, outcomes, calls = self.evaluate('This works. ' + 'x' * 288, {})
        self.assertFalse(calls)
        self.assertEqual(outcomes[0]['status'], 'skipped_length')

    def test_truncation_is_explicit_in_request_and_rubric(self):
        _, _, calls = self.evaluate('x' * 5000 + '\n\nThis works.', {'reference_0': self.answer('uncertain')})
        self.assertTrue(calls[0]['state']['context_truncated'])
        self.assertIn('truncated', calls[0]['questions']['reference_0']['criteria']['uncertain'])

    def test_repeated_reference_text_has_distinct_source_offsets(self):
        rule = next(r for r in load_rules() if r.id == 'noun.unclear-reference')
        row = self.collect('This is necessary. This is sufficient.')[0]
        request = references.reference_request(row, rule, list(range(len(row.candidates))))
        spans = request['state']['references']
        self.assertEqual(len(spans), 2)
        self.assertNotEqual(spans[0]['start'], spans[1]['start'])
        for span in spans:
            self.assertEqual(row.paragraph[span['start']:span['end']], span['text'])

    def test_truncated_context_cannot_prove_an_unintroduced_reference(self):
        findings, outcomes, _ = self.evaluate('x' * 2100 + '\n\nThis works.',
                                             {'reference_0': self.answer('unclear')})
        self.assertEqual(findings, [])
        self.assertEqual(outcomes[-1]['status'], 'context_incomplete')

    def test_yaml_continuations_after_blank_or_comment_cannot_warn(self):
        for separator in ('\n', '# metadata comment\n',
                          '\n  # metadata comment\n\n'):
            with self.subTest(separator=separator):
                text = f'---\ntitle: A queue\n{separator}  stores writes\n---\n\nThis works.'
                row = self.collect(text)[-1]
                self.assertTrue(row.context_truncated)
                self.assertEqual(row.candidates[0].start, text.index('This'))
                findings, outcomes, calls = self.evaluate(
                    text, {'reference_0': self.answer('unclear')})
                self.assertEqual(findings, [])
                self.assertEqual(outcomes[-1]['status'], 'context_incomplete')
                self.assertTrue(calls[0]['state']['context_truncated'])

    def test_questions_batched_at_six_and_requests_capped(self):
        _, outcomes, calls = self.evaluate('This helps. ' * 8, {})
        self.assertEqual([len(c['questions']) for c in calls], [6, 2])
        _, outcomes, calls = self.evaluate('\n\n'.join(['This works.'] * 45), {})
        self.assertEqual(len(calls), 40)
        self.assertEqual(outcomes[-1]['status'], 'request_budget')


class ReferenceIntegration(unittest.TestCase):
    def test_long_paragraph_skips_credential_lookup(self):
        rule = next(r for r in load_rules() if r.id == 'noun.unclear-reference')
        doc = build_document('probe', 'This works. ' + 'x' * 288)
        with patch('hound.reference_check.JevClient') as factory:
            findings, outcomes = references.run(doc, rule, load_model('en'))
            factory.assert_not_called()
        self.assertEqual(findings, [])
        self.assertEqual(outcomes[0]['status'], 'skipped_length')

    def test_any_noun_is_considered_without_a_word_list(self):
        rows = references.collect_reference_paragraphs(build_document('probe',
            '# Repairs\n\nThe capacitor is damaged. The otter swims. These paddles broke.'), load_model('en'))
        self.assertEqual([c.text for c in rows[0].candidates],
                         ['The capacitor', 'The otter', 'These paddles'])

    def test_reference_word_list_rules_are_removed(self):
        ids = {r.id for r in load_rules()}
        self.assertNotIn('phrase.orphan-definite-abstraction', ids)
        self.assertNotIn('phrase.orphan-demonstrative-abstraction', ids)

    def test_cli_reports_missing_key_without_claiming_clear(self):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        from hound.cli import main
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('hound.reference_check.JevClient') as factory, patch('sys.stdin', io.StringIO('The otter swims.')):
            factory.return_value.__enter__.return_value.enabled = False
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main(['--check-references', '--only', 'noun.unclear-reference', '-'])
        self.assertIn('missing API key', stderr.getvalue())
        self.assertIn('not reviewed', stderr.getvalue())

    def test_default_does_not_collect_or_judge_references(self):
        from hound import reference_check
        with patch.object(reference_check, 'collect_reference_paragraphs', side_effect=AssertionError('must be opt-in')):
            Engine(load_rules()).lint(build_document('probe', '# Latency\n\nThis works.'))

    def test_opt_in_engine_and_cli(self):
        from hound.cli import build_parser
        self.assertTrue(build_parser().parse_args(['--check-references', '-']).check_references)
        engine = Engine(load_rules(), check_references=True)
        doc = build_document('probe', '# Request latency metrics\n\nRecord request durations in the histogram. The monitoring system computes p95.')
        with patch('hound.reference_check.JevClient') as factory:
            client = factory.return_value.__enter__.return_value
            client.enabled = True
            client.evaluate.return_value = SimpleNamespace(model='jev-1.13.0', choices={
                'reference_0': ReferenceJudgments.answer('clear'),
                'reference_1': ReferenceJudgments.answer('unclear')})
            findings = engine.lint(doc)
            self.assertTrue(any(f.rule.id == 'noun.unclear-reference' and doc.text[f.start:f.end] == 'The monitoring system' for f in findings))
            self.assertEqual(factory.call_args.kwargs, {'max_retries': 0})
            self.assertEqual(engine.reference_outcomes[-1]['status'], 'unclear')


if __name__ == '__main__':
    unittest.main()
