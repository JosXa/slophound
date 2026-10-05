"""Local chopped rhythm, rather than a ban on brief sentences or instructions."""
import unittest
from hound.engine import Engine
from hound.loader import load_rules
from hound.masking import build_document

FISH = "Every fish wants three things. Don’t get eaten. Eat. And don’t get tired."
CONTEXT = "The current brings food to fish resting behind the rocks."
BEATS = CONTEXT + " Safe. Food. Easy."
ALTERNATING = (
    "The branches protect small fish from predators moving through the open water. A hiding place. "
    "The current delivers insects to fish waiting near the edge of the channel. A free meal. "
    "The rocks slow the current enough for fish to rest without swimming upstream. Less effort."
)

class StaccatoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()
        cls.engine = Engine([r for r in cls.rules if r.id == 'doc.staccato-beats'])

    def lint(self, text):
        return self.engine.lint_deterministic(build_document('probe.md', text))

    def test_registered_advisory(self):
        self.assertEqual(['doc.staccato-beats'], [r.id for r in self.engine.rules])
        self.assertEqual('sniff', self.engine.rules[0].severity)

    def test_contextual_labels_and_fish_script(self):
        for text in (BEATS, FISH + ' ' + BEATS, ALTERNATING):
            with self.subTest(text=text):
                self.assertEqual(1, len(self.lint(text)))

    def test_supporting_locations_and_exact_span(self):
        text = CONTEXT + '\n\nSafe.\n\nFood.\n\nEasy.'
        findings = self.lint(text)
        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual('Safe.', text[finding.start:finding.end])
        self.assertIn('3:1, 5:1, 7:1', finding.message)
        self.assertIn('3 short beats', finding.message)
        self.assertIn('related', finding.message)
        self.assertNotIn('with a verb', finding.message)

    def test_reflow(self):
        for separator in (' ', '\n', '\n\n', '\t'):
            text = separator.join(BEATS.split(' ')) if separator != '\n\n' else BEATS.replace('. ', '.\n\n')
            with self.subTest(separator=separator):
                self.assertEqual(1, len(self.lint(text)))

    def test_useful_short_prose(self):
        cases = [
            FISH,  # Complete imperatives alone are not sufficient evidence.
            'Stop. Wait. Restart. Check the logs. Repeat if necessary.',
            'The server needs restarting. Stop it. Wait. Start it. Check the logs.',
            'Little fish follow the bugs. Big fish follow the little fish. Birds follow the bass.',
            'The disk fills. Writes fail. Clients retry. The queue grows.',
            CONTEXT + ' Easy. ' + CONTEXT,
            CONTEXT + ' Safe. Food.',
            'Fish seek shelter, food, and water where they can rest without fighting the current.',
            'Safe. Food. Easy.',  # Labels alone have no running-prose context.
            '# Safe.\n\n# Food.\n\n# Easy.\n\n' + CONTEXT,
            CONTEXT + '\n\n- Safe.\n- Food.\n- Easy.',
            CONTEXT + '\n\n1. Stop.\n2. Wait.\n3. Restart.',
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual([], self.lint(text))

    def test_masks_and_structure_barriers(self):
        for text in ('```text\n' + BEATS + '\n```', '`' + BEATS + '`', '<!-- ' + BEATS + ' -->',
                     CONTEXT + ' Safe. Food.\n\n# New section\n\nEasy.',
                     CONTEXT + ' Safe. Food.\n\n- A real list item.\n\nEasy.'):
            with self.subTest(text=text):
                self.assertEqual([], self.lint(text))

    def test_species_initials_are_not_detached_beats(self):
        # Reduced from Ghostbuster essay/claude/12; the shared splitter treats
        # genus initials as sentence endings. This metric must not count them.
        text = ('The culture contained several species under the microscope. '
                'It included E. coli, P. mirabilis, and S. epidermidis. '
                'The control contained E. coli and P. mirabilis. '
                'The final sample contained a small amount of S. epidermidis.')
        self.assertEqual([], self.lint(text))

    def test_repeated_dramatic_emphasis_is_not_varied_chopping(self):
        # Verbatim human-authored passage, Ghostbuster wp/human/2 (CC BY 3.0).
        text = ('And, by coincidence, more cracks appear at that very moment. '
                'And then more. And more. And more. And more...')
        self.assertEqual([], self.lint(text))

    def test_local_window_and_distant_emphases(self):
        # Three beats within eight sentences, even late in a long document.
        inside = CONTEXT + ' Safe. ' + CONTEXT + ' Food. ' + ' '.join([CONTEXT] * 3) + ' Easy.'
        outside = CONTEXT + ' Safe. ' + CONTEXT + ' Food. ' + ' '.join([CONTEXT] * 5) + ' Easy.'
        self.assertEqual(1, len(self.lint(inside)))
        self.assertEqual(1, len(self.lint(' '.join([CONTEXT] * 30) + ' ' + BEATS)))
        self.assertEqual([], self.lint(outside))

if __name__ == '__main__':
    unittest.main()
