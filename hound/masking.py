"""Turn Markdown into views the detection layers can search without tripping over
markup, while keeping every character offset identical to the original text.

Three views, all exactly as long as the source text:

- `masked`: code fences, inline code, URLs, link targets, front matter, HTML
  comments, HTML tags and tables are replaced by spaces. Everything else,
  including emphasis markers and quote characters, is untouched. Punctuation
  rules run here because they care about the raw characters.
- `prose`: `masked` with typographic quotes normalised to ASCII and Markdown
  markup (heading hashes, list bullets, blockquote markers, emphasis) blanked.
  Phrase, template and grammar rules run here.

Blocks describe the structure: each heading, list item, paragraph or blockquote
paragraph becomes one block with its kind and span, so layers can skip headings
or quotes and the document layer can reason about paragraphs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Characters normalised in the prose view. Same length, so offsets survive.
_QUOTE_MAP = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})

_FENCE_RE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$", re.M | re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---[ \t]*\n", re.S)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^<>\n]*>")
_URL_RE = re.compile(r"(?:https?|ftp)://[^\s)>\]]+|www\.[^\s)>\]]+")
_LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
_TABLE_LINE_RE = re.compile(r"^[ \t]*\|.*$", re.M)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+")
_BULLET_RE = re.compile(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+")
_QUOTE_MARK_RE = re.compile(r"^([ \t]*>)+[ \t]?")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_)(?=\S)|(?<=\S)(\*\*|__|\*|_)")
_ATX_TRAILING_RE = re.compile(r"[ \t]+#+[ \t]*$")


@dataclass
class Block:
    kind: str  # heading | list | paragraph | quote
    start: int
    end: int  # exclusive


@dataclass
class Document:
    path: str
    text: str
    masked: str
    prose: str
    blocks: list[Block]
    line_starts: list[int]

    def line_col(self, offset: int) -> tuple[int, int]:
        """1-based line and column for an offset."""
        import bisect

        line = bisect.bisect_right(self.line_starts, offset) - 1
        return line + 1, offset - self.line_starts[line] + 1

    def line_span(self, offset: int) -> tuple[int, int]:
        """Start and end offsets of the line containing `offset`."""
        line, _ = self.line_col(offset)
        start = self.line_starts[line - 1]
        end = self.line_starts[line] - 1 if line < len(self.line_starts) else len(self.text)
        return start, end

    def blocks_of(self, *kinds: str) -> list[Block]:
        return [b for b in self.blocks if b.kind in kinds]

    def word_count(self) -> int:
        return len(re.findall(r"[A-Za-z0-9'\u00C0-\u024F]+", self.prose))


def _blank(text: str, start: int, end: int) -> str:
    """Replace text[start:end] with spaces, keeping newlines."""
    segment = "".join("\n" if ch == "\n" else " " for ch in text[start:end])
    return text[:start] + segment + text[end:]


def _blank_matches(text: str, regex: re.Pattern) -> str:
    out = text
    for m in regex.finditer(text):
        out = _blank(out, m.start(), m.end())
    return out


def build_document(path: str, text: str, skip_quotes: bool = False) -> Document:
    masked = text
    masked = _blank_matches(masked, _FRONT_MATTER_RE)
    masked = _blank_matches(masked, _FENCE_RE)
    masked = _blank_matches(masked, _INLINE_CODE_RE)
    masked = _blank_matches(masked, _HTML_COMMENT_RE)
    masked = _blank_matches(masked, _HTML_TAG_RE)
    masked = _blank_matches(masked, _LINK_TARGET_RE)
    masked = _blank_matches(masked, _URL_RE)
    masked = _blank_matches(masked, _TABLE_LINE_RE)

    line_starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    blocks: list[Block] = []
    prose_lines: list[str] = []
    masked_lines: list[str] = []

    pos = 0
    current: Block | None = None
    for raw_line in masked.split("\n"):
        line = raw_line
        line_start = pos
        pos += len(raw_line) + 1
        stripped = line.strip()

        kind: str | None
        if not stripped:
            kind = None
        elif _QUOTE_MARK_RE.match(line):
            kind = "quote"
            if skip_quotes:
                # --skip-quotes hides quoted text from every layer, punctuation included.
                line = " " * len(raw_line)
        elif _HEADING_RE.match(line):
            kind = "heading"
        elif _BULLET_RE.match(line):
            kind = "list"
        else:
            kind = "paragraph"

        prose_line = line.translate(_QUOTE_MAP)
        if kind == "quote":
            if skip_quotes:
                prose_line = " " * len(line)
            else:
                prose_line = _blank_prefix(prose_line, _QUOTE_MARK_RE)
                # A quoted list item or heading still has its own marker.
                prose_line = _blank_prefix(prose_line, _BULLET_RE)
                prose_line = _blank_prefix(prose_line, _HEADING_RE)
        elif kind == "heading":
            prose_line = _blank_prefix(prose_line, _HEADING_RE)
            prose_line = _blank_matches(prose_line, _ATX_TRAILING_RE)
        elif kind == "list":
            prose_line = _blank_prefix(prose_line, _BULLET_RE)
        prose_line = _blank_matches(prose_line, _EMPHASIS_RE)
        prose_lines.append(prose_line)
        masked_lines.append(line)

        line_end = line_start + len(raw_line)
        if kind is None:
            current = None
            continue
        # Headings and list items are one block per line. Paragraph and quote
        # lines continue the previous block of the same kind.
        if current is not None and current.kind == kind and kind in ("paragraph", "quote"):
            current.end = line_end
        else:
            current = Block(kind, line_start, line_end)
            blocks.append(current)

    prose = "\n".join(prose_lines)
    masked = "\n".join(masked_lines)
    assert len(prose) == len(text) == len(masked), "views must keep offsets"
    return Document(path, text, masked, prose, blocks, line_starts)


def _blank_prefix(line: str, regex: re.Pattern) -> str:
    m = regex.match(line)
    if not m:
        return line
    return " " * m.end() + line[m.end() :]
