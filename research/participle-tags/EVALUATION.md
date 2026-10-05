# Detached outcome endings: proposal evaluation

Evaluated 5 October 2026. The proposal finds **one observed target construction**, with **no observed false positives in the corpus run**. It also flags **two legitimate constructed controls**. This evidence supports an advisory rule because legitimate fragments can match.

## Proposal

Match a short noun phrase followed by a comma and one outcome word. There is no restriction on the opener: the user's `the same submission, answered` and `all the same process, verified` both match, as do constructed examples with `your`, `the`, and other openers.

- Core endings: `answered`, `verified`, `simplified`, `streamlined`, `solved`, `demystified`, `reimagined`, `elevated`, `perfected`.
- Additional endings evaluated separately: `eliminated`, `unified`, `transformed`, `decoded`, `unlocked`, `redefined`, `reinvented`, `tamed`.
- Search paragraphs, list items, headings, and reader-visible frontmatter fields after the existing prose masking.
- Limit the noun phrase to 12 words. Parse that phrase, requiring a nominal root and no finite verb or modal. Do not require the outcome word to parse as a participle: spaCy tags the motivating `answered` as past tense.
- Allow an introductory label before a colon or spaced dash. Apply the grammar condition to the following noun phrase.

This is a separate construction from count-led specification fragments. `Eight criteria, scored 1 to 5.` does not match. A colon replacing the outcome comma was measured as an extension and produced no corpus findings. Period-separated fragments, `made simple`, and `now verified` remain outside this proposal.

## Corpus coverage

The run used the earlier study's frozen reference selection and all available rows in the two agent datasets. There was no search for candidate words to select the modern rows.

| Source | Evaluated material | Findings |
| --- | --- | ---: |
| Ghostbuster, generated groups | 5,871 complete texts | 0 |
| Ghostbuster, human-labeled groups | 2,787 complete texts | 0 |
| Historical Rust RFCs | 475 proposals at the pinned revision | 0 |
| CC-Bench | Prose from all 260 trajectories | 0 |
| Trace Commons | Prose from all 30 viewer sessions | 1 |

After masking, empty-text removal, and deduplication within model and extraction kind, the modern sources contributed 14,532 excerpts: 7,922 assistant messages, 108 Markdown/text artifacts or edits, 98 visible HTML extracts, and 6,404 comment or docstring extracts. The combined run contains **23,665 text units**, **5,334,396 prose words**, and **337,793 sentence or heading spans**. An individual comment is one unit, so this is not a count of distinct projects or files.

[Evaluation data](evaluation.json) records the revisions, counts, proposal, and complete finding review. [The collection note](additional-samples.md) records the Trace Commons response coverage and attribution limits. The existing [dataset survey](datasets.md) gives the source and license details. WildChat's search endpoint returned HTTP 500, so this run includes no WildChat conversations.

## Observed finding

**Trace Commons row 25, `messages[812].content`, 16 June 2026.** The session metadata labels the model `claude-opus-4-8`. The [source row](https://datasets-server.huggingface.co/rows?dataset=trace-commons%2Fagent-traces&config=default&split=train&offset=25&length=1) contains this heading:

```text
What this MR carries — the whole arc, verified
```

The matched construction is `the whole arc, verified`. I classify it as the requested style problem: a vague noun phrase receives a detached one-word assurance. The bullets below it describe source builds, a local build, reproducibility checks, and a release. Those details can supply the evidence without the heading's assurance. A suitable replacement heading is `Changes and checks in this MR`.

The first proposal rejected this example because it parsed the whole heading prefix and found the finite verb `carries`. Restricting the parse to the noun phrase after the introductory dash fixes that observed miss. With the same corpus and vocabulary, findings changed from zero to one. Both runs remain in the saved artifacts.

No additional endings produced a finding. There were no other lexical candidates rejected by the final grammar condition, and no observed corpus false positives to list.

## False positives and controls

These two examples are **constructed controls, not dataset quotations**:

| Legitimate context | Text | Proposal behavior |
| --- | --- | --- |
| FAQ heading | `Your questions, answered` | Flags it |
| Order verification status | `Order 123, verified.` | Flags it |

Both have the same syntax and an included outcome word. The grammar condition cannot distinguish their useful functions from a slogan. A word blacklist would have more false positives because it would also reject complete statements using these verbs.

The proposal preserves the attested Rust example `No more defaults to apply, done.` and the CC-Bench alignment description `A container with 800px width, centered`. Their endings are outside the word list. It also preserves constructed finite clauses, integrated modifiers, concrete qualifying tails, inline code, and fenced code.

All **36 controls** satisfy the expected detector behavior. That includes the two known false positives, whose expected behavior is explicitly set to detection. Passing these checks does not mean the proposal correctly judges every legitimate sentence.

## Recommendation and limits

Keep this at `bark` for review. The two legitimate controls block promotion to `bite` without a narrower context condition or an explicit preference to reject those uses. Keep the nine core words for now: the additional eight have no observed benefit in this sample.

One observed match is too little to estimate precision or claim that models disproportionately use this construction. The modern sources contain mostly programming assistance, and the website sample is small. Visible HTML extraction excludes scripts and styles. It does not extract strings or visible copy inside JSX/TSX components. Comment extraction covers Python and selected C-family languages. It is not a complete parser for every language. Writes can copy existing repository prose, so attributing a payload to an assistant does not establish that every word was newly generated.

The evaluation is implemented in [evaluate.py](evaluate.py), with [controls.json](controls.json) and [extract.py](extract.py). It uses spaCy 3.8.16 and `en_core_web_sm` 3.8.0. Full inputs, manifests, candidates, and both runs are retained under `/tmp/opencode/slophound-participle-tags/`. No production rule was enabled or changed.

## Report checks

Report lint retains one `noun.cluster-three` suggestion. In `The two legitimate controls block promotion`, spaCy tags `block` as a noun although it is the sentence's verb. This is a parser false positive, so the legitimate wording is preserved. The collection note retains a suggestion for `assistant text blocks`, which is readable and identifies the message role and content type. [Full lint diagnostics](evaluation-lint.txt) records both suggestions after the editorial changes.
