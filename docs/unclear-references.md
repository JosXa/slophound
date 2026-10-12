# Unclear opening references

Six advisory families check context-free opening claims. Five phrase rules cover a bare demonstrative verdict, a demonstrative consequence, a demonstrative abstraction, a definite abstraction, and an unnamed comparison. The existing `verb.demonstrative-enables` rule owns benefit claims and now includes `allow`.

The checks ask the writer to identify a referent, not to delete demonstratives or definite articles. Ordinary nouns, explicit modifiers, definitions, and literal instructions remain valid. The rules do not attempt to prove that an antecedent is absent by searching for an exact noun. A synonym, an earlier event, or a part of a previously introduced object can establish a reference without repeating its name.

## Eligibility

`opening_reference = true` is an optional boolean for regex and parser rules. It requires a candidate to begin a paragraph with no preceding visible context anywhere in the document. Leading whitespace and emphasis markers do not count as context. Any preceding heading, paragraph, list, rendered metadata, or quotation suppresses a candidate. The rules do not inspect headings, list items, block quotations, or rendered metadata as opening assertions.

Code, tables, link labels, and bare URLs can establish reader-visible context even when the prose view masks them as lint targets. The eligibility gate preserves references after those constructs without interpreting their content. HTML comments and machine-only front matter do not establish context. Rendered front-matter values still do. Ordinary double quotations are not masked by the prose view. An opening quotation mark supplies visible context, so quoted candidates remain silent, including curly quotation marks and soft-wrapped multi-sentence quotations. No shared masking behavior has changed.

Phrase patterns require adjacent bounded words, not arbitrary text between the article and its noun. A modifier between the abstraction and its verb takes the claim outside the candidate shape. A copular definition does not match an abstraction rule. Verdicts with an infinitival explanation also remain silent. A colon or an explanatory connective in the containing sentence suppresses the claim-oriented rules. That sentence-wide exemption is deliberately generous and can hide a separate unclear clause.

## Ownership

`phrase.vague-back-reference` still owns unnamed textual pointers such as references to an earlier discussion. `phrase.cataphoric-count` still owns list-count announcements. Neither inventory is duplicated here. The five new phrase patterns and the pattern for benefit claims have distinct opening shapes. Tests assert one finding per eligible synthetic probe both individually and together.

## Evidence and limits

[Plain Writing rule 24](https://github.com/docwriter-org/plain-writing-skill/blob/f0d3630983ac7a82aa580f1c1509d72df739ee12/skills/plain-writing/SKILL.md) motivated the subject of this work. Its repository license is MIT, copyright 2026 Shreya Shankar. The implementation, messages, and new fixtures are independently written. The source recommends a general demonstrative ban, but these checks preserve established references.

New fixtures are synthetic calibration probes, not independently collected generated or human passages. Baseline and post-change reports on the repository human and generated corpora are identical. Those reports establish no added corpus noise, but they provide no new positive evidence for these opening families. The authoring guide's requirement for a real generated positive remains unfulfilled for the five new families. Broader deployment needs sourced examples and evaluation because the synthetic tests do not establish precision or recall.

The conservative gate misses references after any visible introduction, even an unrelated heading. It does not reset at paragraph or section boundaries. Shared knowledge, external screenshots, earlier messages, and established technical abstractions can justify an opening reference despite a finding. Every family remains advisory because external context can justify the reference.

The small English parser reads `Those enable recovery.` and `Those empower developers to ship.` incorrectly and the benefit family misses them. No lexical fallback was added to reinterpret those parses. Unlisted abstractions, modified constructions, most adverbial variants, and indirect references also remain unchecked. Resolving arbitrary references is an editorial task, not a deterministic coreference claim.
