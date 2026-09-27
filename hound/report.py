"""Human-readable report in the eslint / rustc style.

Severity words come in two vocabularies. The default is the hound's: bite,
bark, sniff. `--formal` (or SLOPHOUND_FORMAL=1) swaps in error, warning,
suggestion for CI logs and reporters that parse linter output. Nothing else
about the report changes between the two.
"""

from __future__ import annotations

import os
import sys
import unicodedata
from collections import Counter

from .masking import Document
from .model import BARK, BITE, FORMAL_NAMES, SEVERITIES, SNIFF, Finding

_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
_COLORS = {BITE: "31", BARK: "33", SNIFF: "36"}
_INDENT = "  "
_ELLIPSIS = "…"
# Width used when no terminal is attached. Narrow enough for tool panes in
# agent harnesses, where a wider line would wrap and push the carets away from
# the words they mark.
DEFAULT_WIDTH = 100
MIN_WIDTH = 40


class Vocabulary:
    """Maps internal severities to the words printed in the report."""

    def __init__(self, formal: bool):
        self.formal = formal
        self.names = dict(FORMAL_NAMES) if formal else {s: s for s in SEVERITIES}
        self.pad = max(len(n) for n in self.names.values())

    def word(self, severity: str) -> str:
        return self.names[severity]

    def count(self, n: int, severity: str) -> str:
        word = self.word(severity)
        return f"{n} {word}{'' if n == 1 else 's'}"

    def plural(self, severity: str) -> str:
        return self.word(severity) + "s"


def formal_requested() -> bool:
    return os.environ.get("SLOPHOUND_FORMAL", "").strip().lower() not in ("", "0", "false", "no")


def _use_color(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class Palette:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def severity(self, severity: str, word: str) -> str:
        return self._wrap(_COLORS[severity], word)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def terminal_width(stream) -> int:
    """Width to fit source lines into.

    `COLUMNS` wins when set. Otherwise the terminal's width, found through any
    standard stream attached to it: a person piping the report through grep
    still reads it in that terminal. With no terminal at all, as in agent
    shells and CI, a fixed width keeps the output the same on every machine.
    """
    columns = os.environ.get("COLUMNS", "")
    if columns.isdigit() and int(columns) > 0:
        return int(columns)
    for candidate in (stream, sys.stderr, sys.stdin):
        try:
            if candidate.isatty():
                return os.get_terminal_size(candidate.fileno()).columns
        except (AttributeError, OSError, ValueError):
            continue
    return DEFAULT_WIDTH


def render(
    doc: Document,
    findings: list[Finding],
    stream=None,
    vocab: Vocabulary | None = None,
    width: int | None = None,
    seen_rules: set[str] | None = None,
) -> None:
    # The CLI shares this set across files so examples appear once per run.
    # Standalone renders start a fresh report unless the caller shares a set.
    if seen_rules is None:
        seen_rules = set()
    stream = stream or sys.stdout
    vocab = vocab or Vocabulary(formal_requested())
    pal = Palette(_use_color(stream))
    budget = max(MIN_WIDTH, (width or terminal_width(stream)) - len(_INDENT))
    ordered = sorted(findings, key=lambda f: (f.start, _ORDER[f.severity], f.rule.id))
    for f in ordered:
        line, col = doc.line_col(f.start)
        word = vocab.word(f.severity)
        header = (
            f"{doc.path}:{line}:{col}  {pal.severity(f.severity, word)}"
            f"{' ' * (vocab.pad - len(word))}  {pal.bold(f.rule.id)}"
        )
        stream.write(header + "\n")
        for source, marker in _source_lines(doc, f, budget):
            stream.write(f"{_INDENT}{source}\n")
            if marker:
                stream.write(f"{_INDENT}{pal.dim(marker)}\n")
        message = f.message
        if not f.detail:
            if f.rule.id in seen_rules and f.rule.repeat_message:
                message = f.rule.repeat_message
            seen_rules.add(f.rule.id)
        stream.write(f"{_INDENT}{message}\n\n")


def _source_lines(doc: Document, f: Finding, budget: int) -> list[tuple[str, str]]:
    """Every line the match touches, each paired with its caret underline.

    A parser-level match can run across a line break (a slide title without
    final punctuation followed by its body). Showing only the first line would
    hide part of what the rule matched, so each line the match touches is
    printed. Carets sit under the matched words only: a dependency match binds
    a few tokens that may sit apart, and underlining the stretch between them
    would present unrelated words as part of the finding.
    """
    pairs: list[tuple[str, str]] = []
    pos = f.start
    first = True
    while True:
        ls, le = doc.line_span(pos)
        source = doc.text[ls:le].rstrip("\n")
        marked = [False] * (len(source) + 1)
        for ms, me in f.marked_spans():
            lo, hi = max(ms, ls) - ls, min(me, le) - ls
            for i in range(lo, min(hi, len(source))):
                marked[i] = True
        if first and not any(marked):
            # An empty match still needs a visible anchor under its position.
            marked[pos - ls] = True
        pairs.append(_fit(_cells(source, marked), budget))
        first = False
        if f.end <= le or le >= len(doc.text):
            return pairs
        pos = le + 1


def _cells(source: str, marked: list[bool]) -> list[tuple[str, bool]]:
    """The source as printed cells, each with its marked flag. Tabs expand to
    four columns and East Asian wide characters take two, so the carets sit
    under the words a terminal shows rather than under character offsets."""
    cells: list[tuple[str, bool]] = []
    column = 0
    for i, ch in enumerate(source):
        if ch == "\t":
            text = " " * (4 - column % 4)
        else:
            text = ch
        cells.append((text, marked[i]))
        column += _width(text)
    if len(marked) > len(source) and marked[len(source)]:
        cells.append(("", True))
    return cells


def _width(text: str) -> int:
    if not text:
        return 1  # the end-of-line anchor
    if len(text) == 1 and unicodedata.east_asian_width(text) in ("W", "F"):
        return 2
    return len(text)


def _fit(cells: list[tuple[str, bool]], budget: int) -> tuple[str, str]:
    """Source line and caret line, cut to `budget` columns around the marks.

    A line longer than the terminal wraps, and the caret line wraps at a
    different place, so the carets land under unrelated words. Long lines are
    cut to a window around the marked words instead, with an ellipsis on each
    cut side.
    """
    widths = [_width(text) for text, _ in cells]
    total = sum(widths)
    if total <= budget:
        return _join(cells, widths, 0, total)
    starts = [0]
    for w in widths:
        starts.append(starts[-1] + w)
    marked = [starts[i] for i, (_, m) in enumerate(cells) if m]
    first = marked[0] if marked else 0
    last = max((starts[i + 1] for i, (_, m) in enumerate(cells) if m), default=first)
    # Center the marked stretch; when it is wider than the window, start at it.
    # Keep one column before it free for the ellipsis.
    lo = max(0, first - max(1, (budget - (last - first)) // 2))
    hi = min(total, lo + budget)
    lo = max(0, hi - budget) if hi - lo < budget else lo
    if lo > 0:
        lo = _snap(cells, starts, lo + 1, min(first, lo + 16), forward=True)
    if hi < total:
        hi = _snap(cells, starts, hi - 1, max(last, hi - 16), forward=False)
    source, carets = _join(cells, widths, lo, hi)
    if lo > 0:
        source = _ELLIPSIS + source
        carets = " " + carets if carets else ""
    if hi < total:
        source += _ELLIPSIS
    return source, carets


def _snap(cells: list[tuple[str, bool]], starts: list[int], cut: int, limit: int, forward: bool) -> int:
    """Move a cut column to the nearest word boundary between `cut` and
    `limit`, so the window does not open or close inside a word."""
    columns = range(cut, limit + 1) if forward else range(cut, limit - 1, -1)
    for column in columns:
        i = next((k for k, s in enumerate(starts) if s == column), None)
        if i is None or i >= len(cells):
            continue
        if forward and i > 0 and cells[i - 1][0].isspace() and not cells[i][0].isspace():
            return column
        if not forward and cells[i][0].isspace() and i > 0 and not cells[i - 1][0].isspace():
            return column
    return cut


def _join(cells: list[tuple[str, bool]], widths: list[int], lo: int, hi: int) -> tuple[str, str]:
    """Cells that lie fully inside columns [lo, hi), printed and underlined."""
    source: list[str] = []
    carets: list[str] = []
    column = 0
    for (text, mark), w in zip(cells, widths):
        if column >= lo and column + w <= hi:
            source.append(text)
            carets.append(("^" if mark else " ") * w)
        column += w
    return "".join(source), "".join(carets).rstrip()


def summary_line(findings: list[Finding], word_count: int, vocab: Vocabulary | None = None) -> str:
    vocab = vocab or Vocabulary(formal_requested())
    counts = Counter(f.severity for f in findings)
    density = (len(findings) / word_count * 100) if word_count else 0.0
    parts = ", ".join(vocab.count(counts[s], s) for s in SEVERITIES)
    return f"{parts} \u00b7 {density:.1f} findings per 100 words"


def footer(rule_files: list[str]) -> str:
    files = "\n".join(f"  {p}" for p in rule_files)
    return (
        "\nFix the text, then rerun. If a finding is wrong, preserve the legitimate wording. "
        "We encourage rule corrections: ask the operator whether to prepare and contribute "
        "a fix. After approval, reproduce it in a repository checkout, add a regression "
        "example, and run `./slophound test`. Leave installed packages and the uvx cache "
        "unchanged. Report unresolved findings separately. Rule files for inspection:\n"
        f"{files}\n"
    )
