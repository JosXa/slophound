# Unclear references

## Ask Jev about short paragraphs

```sh
./slophound --check-references draft.md
```

This optional check finds definite noun phrases and demonstratives with the parser:
"the queue", "the capacitor", "this", "those files", and any other noun.
There is no list of nouns that must or may appear. Jev judges whether each
reference is explained, rather than treating its presence as a writing problem.
The noun-list rules formerly in this PR have been removed.

Each ordinary prose paragraph must be **strictly shorter than 300 source Unicode
characters**. The paragraph is sent intact, with its heading and up to 2,000
characters of preceding reader-visible text. Jev considers explanations before
or after the reference, ordinary generic uses, and reasonable inferences.
A heading supplies evidence; it does not turn the check off.

For example:

```markdown
# Request latency metrics

A histogram records durations. The histogram sends counts to the monitoring system.
```

"The histogram" has an introduction. "The monitoring system" may need one.
Jev judges them separately; a paragraph need not receive one blanket verdict.
Model judgments can remain uncertain even when an editor sees a problem.

The three answers are `clear`, `unclear`, and `uncertain`. Only `unclear` with
confidence at least 0.8 produces a `noun.unclear-reference` warning. The returned
model must be `jev-1.13.0`, and the typed answer must be valid and consistent
with its choice probabilities. If earlier context was cut off, an unclear answer
cannot produce a warning: the missing text might introduce the reference.

Paragraphs of 300 characters or more are skipped, not split or declared clear.
The parser can misidentify a noun phrase; Jev must abstain when the selected span
is not actually a reference. Quotations, code, headings, lists, tables, and front
matter are not review targets. Reader-visible quotations, code, tables, and link
labels can still explain a following paragraph. Hidden comments, HTML attributes,
link destinations, and machine metadata are excluded from requests. Only the
known reader-facing front-matter fields `heading`, `title`, `lede`, and `callout`
are retained as context; unknown fields are not assumed visible. Unsupported
reader-facing YAML values and continuations are omitted and mark context
incomplete, so an unclear answer cannot produce a warning.

Configure a key with `./slophound auth set-key`. This opt-in mode sends paragraph
text and reader-visible context to TypeSafe, including visible code or quotations.
Keep that in mind for private documents. There are at most six references in each
request and 40 requests per document, with no retries for this check. Missing keys,
request failures, unexpected models, invalid answers, and exhausted request limits
produce no new reference warnings. The CLI prints a separate review summary so
an unavailable or uncertain result is not mistaken for a clear result.

For Python callers, `Engine(rules, check_references=True)` enables the check and
exposes `reference_outcomes`. Normal runs leave it off. Existing Jev veto checks
continue to work as before. To isolate this check from other rules:

```sh
./slophound --check-references --only noun.unclear-reference draft.md
```

## Remaining opening-only checks

Separate deterministic advisories still catch a few opening constructions:
"This is necessary", "This causes delays", "Unlike this", and "This enables
recovery". They do not name or resolve nouns. They stop after any preceding
reader-visible context, even a heading, so they miss later vague references.
They remain independent of the opt-in paragraph review.

Their `opening_reference = true` setting is metadata for regex/parser rules.
Detection still uses the masked prose view, while the opening-context test
preserves reader-visible headings, code, quotations, tables, and labels.

## Evidence limit

The examples and regression cases are constructed, not independently sourced
generated writing. This is an experimental check, not a calibrated detector of
machine-written prose. PR #4 remains draft while sourced positive calibration
is missing. Neither a clean deterministic report nor an uncertain Jev answer
establishes that a document's references are clear.
