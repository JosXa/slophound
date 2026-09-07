"""Human-readable report in the eslint / rustc style.

Severity words come in two vocabularies. The default is the hound's: bite,
bark, sniff. `--formal` (or SLOPHOUND_FORMAL=1) swaps in error, warning,
suggestion for CI logs and reporters that parse linter output. Nothing else
about the report changes between the two.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

from .masking import Document
from .model import BARK, BITE, FORMAL_NAMES, SEVERITIES, SNIFF, Finding

_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
_COLORS = {BITE: "31", BARK: "33", SNIFF: "36"}


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


def render(doc: Document, findings: list[Finding], stream=None, vocab: Vocabulary | None = None) -> None:
    stream = stream or sys.stdout
    vocab = vocab or Vocabulary(formal_requested())
    pal = Palette(_use_color(stream))
    ordered = sorted(findings, key=lambda f: (f.start, _ORDER[f.severity], f.rule.id))
    for f in ordered:
        line, col = doc.line_col(f.start)
        ls, le = doc.line_span(f.start)
        source = doc.text[ls:le].rstrip("\n")
        # Underline only within this line; multi-line matches stop at its end.
        underline_start = f.start - ls
        underline_end = min(f.end, le) - ls
        underline_end = max(underline_end, underline_start + 1)
        marker = " " * underline_start + "^" * (underline_end - underline_start)
        word = vocab.word(f.severity)
        header = (
            f"{doc.path}:{line}:{col}  {pal.severity(f.severity, word)}"
            f"{' ' * (vocab.pad - len(word))}  {pal.bold(f.rule.id)}"
        )
        stream.write(header + "\n")
        stream.write(f"  {source.expandtabs(4)}\n")
        stream.write(f"  {pal.dim(marker)}\n")
        stream.write(f"  {f.message}\n\n")


def summary_line(findings: list[Finding], word_count: int, vocab: Vocabulary | None = None) -> str:
    vocab = vocab or Vocabulary(formal_requested())
    counts = Counter(f.severity for f in findings)
    density = (len(findings) / word_count * 100) if word_count else 0.0
    parts = ", ".join(vocab.count(counts[s], s) for s in SEVERITIES)
    return f"{parts} \u00b7 {density:.1f} findings per 100 words"


def footer(rule_files: list[str]) -> str:
    files = "\n".join(f"  {p}" for p in rule_files)
    return (
        "\nFix the text, then rerun. If a finding is wrong, do not work around it in the "
        "document: a false positive is a bug in the rule. Open the rule file, tighten the "
        "pattern or add the sentence to its `acceptable` list, run `./slophound test`, and "
        "offer the user to upstream the change.\n"
        f"{files}\n"
    )
