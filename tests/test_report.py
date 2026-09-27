"""Golden tests for the report format.

A finding is rendered as a header line, then every source line the match
touches with a caret line under it, then the message, then one blank line:

    path:line:col  severity  rule.id
      source line
      ^^^^^^ carets under the matched words
      message

A person reads the carets to see which words the rule counted. A machine reads
the header. Both must stay stable, so these tests compare whole strings.
Findings are built by hand: the format is what is under test, not the rules.
"""

from __future__ import annotations

import io
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from hound.masking import build_document
from hound.loader import RuleError, _build_rule, load_rules
from hound.model import BARK, BITE, SNIFF, Finding, Rule
from hound.report import Vocabulary, render


def _rule(rule_id: str, severity: str, message: str = "Message.") -> Rule:
    return Rule(
        id=rule_id,
        category=rule_id.split(".")[0],
        severity=severity,
        message=message,
        example=["x"],
        acceptable=["y"],
        source_file=Path("rules/test.toml"),
    )


def _render(text: str, *findings: Finding, formal: bool = False) -> str:
    doc = build_document("draft.md", text)
    buf = io.StringIO()
    render(doc, list(findings), stream=buf, vocab=Vocabulary(formal=formal))
    return buf.getvalue()


def _span(text: str, needle: str, occurrence: int = 1) -> tuple[int, int]:
    """Offsets of the n-th occurrence of `needle` in `text`."""
    start = -1
    for _ in range(occurrence):
        start = text.index(needle, start + 1)
    return start, start + len(needle)


HEADER = re.compile(r"^(?P<path>[^:\n]+):(?P<line>\d+):(?P<col>\d+)  (?P<severity>\S+)\s+(?P<rule>[a-z]+\.[a-z0-9-]+)$")


class SingleLineFindings(unittest.TestCase):
    def test_regex_finding_underlines_the_whole_match(self) -> None:
        text = "The retry logic is load-bearing.\n"
        finding = Finding(_rule("phrase.load-bearing", BITE, "Banned."), *_span(text, "load-bearing"))
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:20  bite   phrase.load-bearing\n"
            "  The retry logic is load-bearing.\n"
            "                     ^^^^^^^^^^^^\n"
            "  Banned.\n"
            "\n",
        )

    def test_grammar_finding_underlines_only_the_matched_tokens(self) -> None:
        # The parser bound "file", "holds" and "configuration". The words in
        # between are not part of the finding, so they get no carets.
        text = "The file holds the configuration.\n"
        marks = [_span(text, "file"), _span(text, "holds"), _span(text, "configuration")]
        finding = Finding(_rule("verb.holds-content", BARK), marks[0][0], marks[-1][1], marks=marks)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:5  bark   verb.holds-content\n"
            "  The file holds the configuration.\n"
            "      ^^^^ ^^^^^     ^^^^^^^^^^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_three_adjacent_nouns_read_as_three_words(self) -> None:
        text = "Check the database connection pool.\n"
        marks = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        finding = Finding(_rule("noun.cluster-three", SNIFF), marks[0][0], marks[-1][1], marks=marks)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:11  sniff  noun.cluster-three\n"
            "  Check the database connection pool.\n"
            "            ^^^^^^^^ ^^^^^^^^^^ ^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_zero_width_finding_still_shows_an_anchor(self) -> None:
        text = "Plain sentence.\n"
        finding = Finding(_rule("doc.anchor", SNIFF), 6, 6)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:7  sniff  doc.anchor\n"
            "  Plain sentence.\n"
            "        ^\n"
            "  Message.\n"
            "\n",
        )


class RepeatedGuidance(unittest.TestCase):
    def test_first_in_source_order_gets_full_message(self) -> None:
        text = "One.\nTwo.\n"
        rule = _rule("punct.test", BITE, "Full guidance with examples.")
        rule.repeat_message = "Short reminder."
        first = Finding(rule, 0, 3)
        second = Finding(rule, 5, 8)
        expected = (
            "draft.md:1:1  bite   punct.test\n"
            "  One.\n"
            "  ^^^\n"
            "  Full guidance with examples.\n\n"
            "draft.md:2:1  bite   punct.test\n"
            "  Two.\n"
            "  ^^^\n"
            "  Short reminder.\n\n"
        )
        self.assertEqual(_render(text, second, first), expected)
        self.assertEqual(_render(text, second, first), expected)

    def test_rules_without_reminders_and_finding_details_stay_complete(self) -> None:
        text = "One.\nTwo.\n"
        rule = _rule("doc.test", SNIFF)
        findings = [Finding(rule, 0, 3), Finding(rule, 5, 8)]
        self.assertEqual(_render(text, *findings).count("  Message.\n"), 2)
        rule.repeat_message = "Short reminder."
        findings[1].detail = "Measured value for this finding."
        out = _render(text, *findings)
        self.assertIn("  Message.\n", out)
        self.assertIn("  Measured value for this finding.\n", out)
        self.assertNotIn("Short reminder.", out)

    def test_cli_prints_em_dash_examples_once_across_files_and_resets_next_run(self) -> None:
        from hound.cli import main

        rule = next(r for r in load_rules() if r.id == "punct.em-dash")
        inputs = {
            "first.md": "We built it \u2014 and shipped it.\n\nIt failed\u2014twice.\nIt stopped\u2014again.\n",
            "second.md": "It failed\u2014again.\n",
        }
        for _ in range(2):
            buf = io.StringIO()
            with mock.patch("hound.cli.read_input", side_effect=lambda p: (p, inputs[p])), mock.patch("sys.stdout", buf):
                code = main(["--only", "punct.em-dash,punct.em-dash-and", "--no-footer", *inputs])
            out = buf.getvalue()
            self.assertEqual(code, 1)
            self.assertEqual(out.count(rule.message), 1)
            self.assertEqual(out.count(rule.repeat_message), 2)
            self.assertIn("first.md:3:10  bite   punct.em-dash\n", out)
            self.assertIn("second.md:1:10  bite   punct.em-dash\n", out)
            self.assertIn("4 bites, 0 barks, 0 sniffs", out)

    def test_loader_rejects_invalid_repeat_message(self) -> None:
        raw = dict(id="punct.test", severity=BITE, message="Message.", pattern="x", example=["x"], acceptable=["y"])
        for value in (None, "", "   ", 1, ["Reminder."]):
            with self.subTest(value=value), self.assertRaisesRegex(RuleError, "repeat_message"):
                _build_rule({**raw, "repeat_message": value}, "punct", Path("rules/test.toml"))


class FindingsAcrossLineBreaks(unittest.TestCase):
    def test_wrapped_phrase_prints_both_lines_with_their_own_carets(self) -> None:
        # Markdown is soft-wrapped; a phrase can straddle a line break. Both
        # halves are shown, each underlined, and the header points at the start.
        text = "The executive\nsummary repeats the recommendation.\n"
        finding = Finding(_rule("phrase.executive-summary", BITE), *_span(text, "executive\nsummary"))
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:5  bite   phrase.executive-summary\n"
            "  The executive\n"
            "      ^^^^^^^^^\n"
            "  summary repeats the recommendation.\n"
            "  ^^^^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_noun_cluster_split_over_two_lines_shows_each_noun_where_it_is(self) -> None:
        # The parser glued a slide title to its body and bound "AGENTS.md",
        # "root" and "file". The report has to show exactly those three words
        # so a reader can see what the rule counted and judge the parse.
        text = "Give every client platform its own AGENTS.md\nA root file with purpose and rules.\n"
        marks = [_span(text, "AGENTS.md"), _span(text, "root"), _span(text, "file")]
        finding = Finding(_rule("noun.cluster-three", SNIFF), marks[0][0], marks[-1][1], marks=marks)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:36  sniff  noun.cluster-three\n"
            "  Give every client platform its own AGENTS.md\n"
            "                                     ^^^^^^^^^\n"
            "  A root file with purpose and rules.\n"
            "    ^^^^ ^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_line_between_matched_tokens_is_shown_without_carets(self) -> None:
        # Subject on line one, verb and object on line three. Line two belongs
        # to the sentence and is printed for context, but none of its words
        # were matched, so it must not get a stray caret.
        text = "The file\nthat we shipped yesterday\nholds the configuration.\n"
        marks = [_span(text, "file"), _span(text, "holds"), _span(text, "configuration")]
        finding = Finding(_rule("verb.holds-content", BARK), marks[0][0], marks[-1][1], marks=marks)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:5  bark   verb.holds-content\n"
            "  The file\n"
            "      ^^^^\n"
            "  that we shipped yesterday\n"
            "  holds the configuration.\n"
            "  ^^^^^     ^^^^^^^^^^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_template_over_two_sentences_on_two_lines(self) -> None:
        text = "This is not a cache problem.\nIt is a consistency problem.\n"
        finding = Finding(_rule("template.not-x-but-y", BITE), *_span(text, "This is not a cache problem.\nIt is"))
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:1  bite   template.not-x-but-y\n"
            "  This is not a cache problem.\n"
            "  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
            "  It is a consistency problem.\n"
            "  ^^^^^\n"
            "  Message.\n"
            "\n",
        )


class CaretAlignment(unittest.TestCase):
    def test_tab_indented_source_keeps_carets_under_the_words(self) -> None:
        # The source line is printed with tabs expanded to four columns. The
        # caret line has to use the same expansion or it drifts left.
        text = "\tCheck the database connection pool.\n"
        marks = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        finding = Finding(_rule("noun.cluster-three", SNIFF), marks[0][0], marks[-1][1], marks=marks)
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:12  sniff  noun.cluster-three\n"
            "      Check the database connection pool.\n"
            "                ^^^^^^^^ ^^^^^^^^^^ ^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_wide_characters_before_the_match_are_counted_as_two_columns(self) -> None:
        # East Asian characters occupy two terminal columns. The header column
        # stays a character offset (what editors use); the caret line follows
        # what the terminal shows.
        text = "日本語 text is load-bearing.\n"
        finding = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "load-bearing"))
        self.assertEqual(
            _render(text, finding),
            "draft.md:1:13  bite   phrase.load-bearing\n"
            "  日本語 text is load-bearing.\n"
            "                 ^^^^^^^^^^^^\n"
            "  Message.\n"
            "\n",
        )

    def test_markdown_list_marker_is_part_of_the_source_line(self) -> None:
        text = "- Check the database connection pool.\n"
        marks = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        finding = Finding(_rule("noun.cluster-three", SNIFF), marks[0][0], marks[-1][1], marks=marks)
        out = _render(text, finding)
        self.assertIn("  - Check the database connection pool.\n              ^^^^^^^^ ^^^^^^^^^^ ^^^^\n", out)


class LongLines(unittest.TestCase):
    # A soft-wrapped paragraph is one long source line. Printed whole, the
    # terminal wraps it and the caret line at different places, and the carets
    # land under unrelated words. Long lines are cut to a window around the
    # marks instead.

    FILLER = "Clients send requests to the gateway, and the gateway forwards them. "

    def _render_width(self, text: str, finding: Finding, width: int) -> str:
        doc = build_document("draft.md", text)
        buf = io.StringIO()
        render(doc, [finding], stream=buf, vocab=Vocabulary(formal=False), width=width)
        return buf.getvalue()

    def test_marks_in_the_middle_of_a_long_line_get_a_window_with_ellipses(self) -> None:
        text = self.FILLER * 3 + "Check the database connection pool. " + self.FILLER * 3 + "\n"
        marks = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        finding = Finding(_rule("noun.cluster-three", SNIFF), marks[0][0], marks[-1][1], marks=marks)
        out = self._render_width(text, finding, 62)
        source, carets = out.splitlines()[1:3]
        self.assertEqual("  …them. Check the database connection pool. Clients send…", source)
        self.assertEqual("                   ^^^^^^^^ ^^^^^^^^^^ ^^^^", carets)

    def test_every_printed_line_fits_the_width(self) -> None:
        text = self.FILLER * 5 + "The retry logic is load-bearing. " + self.FILLER * 5 + "\n"
        finding = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "load-bearing"))
        for width in (40, 60, 100, 160):
            out = self._render_width(text, finding, width)
            source, carets = out.splitlines()[1:3]
            self.assertLessEqual(len(source), width, source)
            self.assertLessEqual(len(carets), width, carets)
            self.assertEqual("load-bearing", source[carets.index("^") : carets.rindex("^") + 1])

    def test_match_at_line_start_keeps_the_start_and_cuts_the_end(self) -> None:
        text = "Load-bearing retries. " + self.FILLER * 4 + "\n"
        finding = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "Load-bearing"))
        out = self._render_width(text, finding, 42)
        source, carets = out.splitlines()[1:3]
        self.assertEqual("  Load-bearing retries. Clients send…", source)
        self.assertEqual("  ^^^^^^^^^^^^", carets)

    def test_short_lines_are_printed_whole(self) -> None:
        text = "The retry logic is load-bearing.\n"
        finding = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "load-bearing"))
        self.assertIn("  The retry logic is load-bearing.\n", self._render_width(text, finding, 40))


class ReportShape(unittest.TestCase):
    def _three_findings(self) -> str:
        text = "The retry logic is load-bearing.\nThat buys us a week.\nCheck the database connection pool.\n"
        bite = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "load-bearing"))
        buys = [_span(text, "buys"), _span(text, "us")]
        bark = Finding(_rule("verb.buys-us", BARK), buys[0][0], buys[-1][1], marks=buys)
        cluster = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        sniff = Finding(_rule("noun.cluster-three", SNIFF), cluster[0][0], cluster[-1][1], marks=cluster)
        return _render(text, sniff, bite, bark)

    def test_headers_parse_and_rule_ids_align_across_severities(self) -> None:
        out = self._three_findings()
        headers = [line for line in out.splitlines() if HEADER.match(line)]
        self.assertEqual(3, len(headers))
        parsed = [HEADER.match(h) for h in headers]
        self.assertEqual(["bite", "bark", "sniff"], [m["severity"] for m in parsed])
        # Findings are ordered by position in the document.
        self.assertEqual(["1", "2", "3"], [m["line"] for m in parsed])
        # The severity word is padded so the rule id starts at the same offset
        # after it whatever the word: "bite   x", "bark   x", "sniff  x".
        gaps = {h.index(m["rule"]) - h.index(m["severity"]) for h, m in zip(headers, parsed)}
        self.assertEqual({len("sniff") + 2}, gaps)

    def test_findings_are_separated_by_exactly_one_blank_line(self) -> None:
        out = self._three_findings()
        self.assertNotIn("\n\n\n", out)
        self.assertTrue(out.endswith("Message.\n\n"))
        self.assertEqual(3, out.count("\n\n"))

    def test_no_trailing_whitespace_and_two_space_indent(self) -> None:
        out = self._three_findings()
        for line in out.splitlines():
            self.assertEqual(line, line.rstrip(), repr(line))
            if line and not HEADER.match(line):
                self.assertTrue(line.startswith("  "), repr(line))

    def test_formal_vocabulary_keeps_alignment(self) -> None:
        text = "The retry logic is load-bearing.\nCheck the database connection pool.\n"
        bite = Finding(_rule("phrase.load-bearing", BITE), *_span(text, "load-bearing"))
        cluster = [_span(text, "database"), _span(text, "connection"), _span(text, "pool")]
        sniff = Finding(_rule("noun.cluster-three", SNIFF), cluster[0][0], cluster[-1][1], marks=cluster)
        out = _render(text, bite, sniff, formal=True)
        headers = [line for line in out.splitlines() if HEADER.match(line)]
        self.assertEqual(
            ["draft.md:1:20  error       phrase.load-bearing", "draft.md:2:11  suggestion  noun.cluster-three"],
            headers,
        )
        for word in ("bite", "bark", "sniff"):
            self.assertNotIn(word, out)

    def test_no_escape_codes_without_a_tty(self) -> None:
        with mock.patch.dict(os.environ, {"NO_COLOR": "", "FORCE_COLOR": ""}, clear=False):
            out = self._three_findings()
        self.assertNotIn("\033[", out)


if __name__ == "__main__":
    unittest.main()
