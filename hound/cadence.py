"""Recognize three parallel assertions for the document rhythm metric."""

from __future__ import annotations

import re

from .sentences import words


def clause_parts(text: str) -> tuple[str, str, str] | None:
    """Cheap shape filter before parsing; lists still need grammatical rejection."""
    parts = [part.strip() for part in re.split(r"[,;]", text)]
    if len(parts) != 3 or not re.match(r"and\s+", parts[2], re.I):
        return None
    parts[2] = re.sub(r"^and\s+", "", parts[2], flags=re.I)
    lengths = [len(words(part)) for part in parts]
    a, b, c = lengths
    if not (3 <= a <= 12 and 3 <= b <= 12 and 3 <= c <= 40):
        return None
    if max(a, b) > 2 * min(a, b):
        return None
    balanced = max(lengths) <= 2 * min(lengths)
    long_ending = max(a, b) <= 8 and c >= max(7, 1.5 * max(a, b))
    return tuple(parts) if balanced or long_ending else None


def _assertion(parsed):
    """Return the main predicate and subject, not verbs in embedded clauses."""
    tokens = [t for t in parsed if not t.is_space and not t.is_punct]
    if not tokens:
        return None
    # Standalone parsing can promote a conditional or relative clause to ROOT.
    if tokens[0].lower_ in {
        "if", "unless", "when", "whenever", "while", "although", "though",
        "because", "since", "where", "wherever", "which", "who", "whose",
        "whom", "that", "whether", "until", "before", "after", "once", "as",
    }:
        return None
    roots = [t for t in tokens if t.dep_ == "ROOT"]
    if len(roots) != 1:
        return None
    root = roots[0]
    if root.pos_ not in {"VERB", "AUX"}:
        return None
    if any(t.dep_ == "mark" for t in root.children):
        return None
    subjects = [t for t in root.children if t.dep_ in {"nsubj", "nsubjpass"} and t.i < root.i]
    if len(subjects) != 1:
        return None
    # A participle with a subject still needs a finite auxiliary to assert a fact.
    finite = {"VBD", "VBP", "VBZ", "MD"}
    if root.tag_ not in finite and not any(t.tag_ in finite for t in root.children):
        return None
    if not any(t.i > root.i for t in tokens):
        return None
    return root.lemma_.lower(), " ".join(t.lower_ for t in subjects[0].subtree)


def parallel_assertions(parts, parsed) -> bool:
    """Each comma-delimited piece must be an assertion with its own subject."""
    assertions = [_assertion(clause) for clause in parsed]
    # The small model reads "Red means fix it" as a noun phrase plus "fix".
    # Keep the observed status-label template as a bounded surface exception;
    # do not turn every repeated noun with a possible verb sense into a verb.
    status_labels = (
        re.fullmatch(r"([a-z][\w'-]*) means fix it", parts[0], re.I),
        re.fullmatch(r"([a-z][\w'-]*) means done", parts[1], re.I),
    )
    if all(status_labels):
        assertions[:2] = [("mean", match[1].lower()) for match in status_labels]
    if not all(assertions):
        return False
    first, second, third = assertions
    if first[0] != second[0] or first[1] == second[1]:
        return False
    lengths = [len(words(part)) for part in parts]
    # Equal beats need the repeated predicate in all three assertions. The
    # short-short-long variant allows a different predicate in its conclusion.
    return third[0] == first[0] or (
        max(lengths[:2]) <= 8 and lengths[2] >= max(7, 1.5 * max(lengths[:2]))
    )
