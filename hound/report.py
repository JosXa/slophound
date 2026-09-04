"""Human-readable report in the eslint / rustc style."""

from __future__ import annotations

import sys
from collections import Counter

from .masking import Document
from .model import Finding

_ORDER = {"error": 0, "warning": 1, "suggestion": 2}
_PAD = max(len(s) for s in _ORDER)


def _use_color(stream) -> bool:
    import os

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

    def severity(self, sev: str) -> str:
        return self._wrap({"error": "31", "warning": "33", "suggestion": "36"}[sev], sev)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def render(doc: Document, findings: list[Finding], stream=None) -> None:
    stream = stream or sys.stdout
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
        header = f"{doc.path}:{line}:{col}  {pal.severity(f.severity)}{' ' * (_PAD - len(f.severity))}  {pal.bold(f.rule.id)}"
        stream.write(header + "\n")
        stream.write(f"  {source.expandtabs(4)}\n")
        stream.write(f"  {pal.dim(marker)}\n")
        stream.write(f"  {f.message}\n\n")


def summary_line(findings: list[Finding], word_count: int) -> str:
    counts = Counter(f.severity for f in findings)
    density = (len(findings) / word_count * 100) if word_count else 0.0

    def plural(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'}"

    return (
        f"{plural(counts['error'], 'error')}, {plural(counts['warning'], 'warning')}, "
        f"{plural(counts['suggestion'], 'suggestion')} \u00b7 {density:.1f} findings per 100 words"
    )


def footer(rule_files: list[str]) -> str:
    files = "\n".join(f"  {p}" for p in rule_files)
    return (
        "\nFix the text, then rerun. If a finding is wrong, do not work around it in the "
        "document: a false positive is a bug in the rule. Open the rule file, tighten the "
        "pattern or add the sentence to its `acceptable` list, run `./slophound test`, and "
        "offer the user to upstream the change.\n"
        f"{files}\n"
    )
