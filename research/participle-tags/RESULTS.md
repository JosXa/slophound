# Comma and past participle endings

Research checked 5 October 2026. The proposed rule addresses the user's examples:

```text
The same submission, answered.
All the same process, verified.
```

The construction is a noun phrase followed by a comma and a detached past participle. It can occur with any determiner, possessive, or noun. The word `same` is incidental. A word list needs a structural condition because both the verbs and participial modifiers have legitimate uses.

## Closest reference

[unslop's catalog](https://github.com/theclaymethod/unslop/blob/17ed39c9d0b522f44190ff0c6233867eadee192a/references/taboo-phrases.md#L1131-L1135) explicitly describes `spec_fragment`: a count, a noun phrase, then a past participle. Its example is:

```text
Eight criteria, scored 1 to 5.
```

Its suggested regex accepts regular `-ed` endings and several irregular forms, including `built`, `written`, `made`, `done`, and `shown`. It only matches an entire line and requires a numeric opener. This is a close precedent, but it does not cover arbitrary noun phrases. The catalog treats it as soft severity. A repository search found the category in the reference and pack manifest, but no corresponding implementation in the Python scanner. Treat it as editorial guidance, not a validated detector.

[no-ai-slop](https://github.com/petergyang/no-ai-slop/blob/000650b156983f5159695b441477f4e63b25dc85/skills/no-ai-slop/SKILL.md#L74-L82) discusses dramatic fragmentation, repeated sentence forms, and questions followed by punchy answers. [skill-deslop](https://github.com/stephenturner/skill-deslop/blob/a906154bef375d9d49ed2ad7da13b2db16f0d3d2/references/structures.md#L36-L58) gives related examples. Both discuss trailing present participles separately. Neither inspected catalog names the exact one-word past-participle ending.

Our nearest rules are `template.verbless-pair`, `template.fragment-chain`, and `template.question-one-word-answer`. `template.participial-tail` concerns interpretive `-ing` clauses. None directly represents this request. The humanize reference likewise discusses compressed compounds and passive clauses, without this exact construction.

## Candidate endings and adjacent constructions

These are proposed examples for evaluation, not quotations from the datasets:

```text
Your workflow, simplified.
The whole pipeline, streamlined.
The problem, solved.
The architecture, demystified.
Your deployment, reimagined.
The experience, elevated.
The bottleneck, eliminated.
The process, perfected.
```

Start an evaluation dictionary with the supplied `answered` and `verified`, plus `simplified`, `streamlined`, `solved`, `demystified`, `reimagined`, `elevated`, `eliminated`, and `perfected`. Consider `unified`, `transformed`, `decoded`, `unlocked`, `redefined`, `reinvented`, and `tamed` after reviewing actual matches. These choices express an editorial preference. The searches below do not establish that models overuse them.

Search related variants before deciding whether they belong in the same rule:

```text
Your workflow. Simplified.
Your workflow: simplified.
Your workflow, made simple.
The same process, now verified.
```

The final two require more than a one-word ending. A closed word list would miss them. A broad punctuation rule would also catch labels and captions.

## Cases to preserve

The historical [Rust RFC on defaulted type parameters](https://github.com/rust-lang/rfcs/blob/16f3bc024bdef9db7502ffbefeb602c37cee20bf/text/0213-defaulted-type-params.md#L434) uses:

```text
No more defaults to apply, done.
```

It closes a worked inference procedure. The ending communicates termination. It is a real technical counterexample to a blanket ban on comma-plus-participle fragments.

An attributed GLM-4.5 [CC-Bench trace](https://huggingface.co/datasets/zai-org/CC-Bench-trajectories/tree/792c6d3221db4d9ed475702ed61a176dd8948152), train row 115, trajectory message 37, content block 0, gives an implementation detail:

```text
A container with 800px width, centered
```

The final word specifies alignment. This demonstrates that generated text can use the construction usefully. The probe also found ordinary ingredient instructions in Ghostbuster's GPT samples and complete narrative sentences in both human and generated writing.

Additional constructed controls should cover complete clauses, integrated modifiers, and conventional headings:

```text
The reviewer answered the submission.
The process was verified against the audit log.
The issue, resolved by the maintainer, stayed closed.
The reviewer replied, reassured.
Your questions, answered.
```

The FAQ heading in the last example is conventional human writing. Whether to reject it is a house-style choice. The comma alone cannot decide. A proposed production rule must resolve that choice before it can have an honest acceptable test.

## Corpus search

[probe.py](probe.py) uses slophound's masking and sentence boundaries, then asks lemminflect whether a final one-word comma suffix can be a past participle. It collects candidates without judging their quality. The retained [summary](evidence.json) records the group counts. Pinned corpus revisions and the selection method come from the [earlier cadence study](../parallel-cadence/RESULTS.md).

- Historical references: 9,133 texts, 5,063,283 prose words, and 291,982 sentence spans. The broad suffix probe returned 113 candidates. Reading them found no instance of the proposed dictionary in the requested construction. Most candidates were dialogue tags, descriptions of a character's state, or finite verbs following a parenthetical.
- Modern reference: all 260 CC-Bench rows returned with no truncated cells. Assistant text and Markdown/text writes were isolated from user turns and tool results. After whitespace deduplication within each model and artifact group, 5,434 excerpts supplied 97,726 prose words and 17,933 spans. The broad probe found the single useful alignment example above. The dictionary search found no matches.

The researcher also inspected the first 10 [Trace Commons sessions](https://huggingface.co/datasets/trace-commons/agent-traces/tree/112ebd4d03ce852b00e935d523107c3d0c9a65bf). They yielded 975 assistant-message records and 306 assistant `Write` payloads. Eight sessions label `claude-sonnet-4-6` and two label `claude-opus-4-8`. The targeted search found no motivating noun-phrase-plus-outcome construction or the proposed two-word variants. Row 7, `messages[241].content`, instead says "The feature is complete, tested, and documented." Row 5, `messages[56].content`, says "MiniMax M3 is now in all generated outputs. Done." Both have a complete finite clause. These are preliminary source examples. Their model labels come from session metadata, and the viewer does not certify a pinned revision.

These figures cover paragraphs and list items, including sentences without terminal punctuation. They exclude headings and quoted blocks. They are not a balanced sample of website slogans or current project descriptions. The probe can include headings with `--headings`; the reported counts do not use that option. Lemma morphology also accepts words that are finite past verbs in context, so every candidate needs review.

CC-Bench has a model-attribution trap: the wrapper's `message.model` says `claude-sonnet-4-20250514` for many GLM, Qwen, and Kimi runs. Use the dataset row's `model_name` for comparisons. Do not assign all these messages to Claude. The current dataset revision matched the earlier pinned revision, but the viewer responses do not themselves certify a revision. For a retained trigger example, retrieve its pinned source artifact too.

The small spaCy model tags `answered` as `VBD` in the user's first example and `verified` as `VBN` in the second. A `VBN`-only condition therefore misses a motivating case. It also misparsed a finite verb in one ordinary narrative candidate. A parser-based rule needs advisory severity and regression tests for those cases.

## Recommendation

Define the target as a short noun phrase followed by a detached outcome word, without an earlier finite predicate. Use a closed list of endings to limit the first evaluation. Do not require `same` or restrict the opener to a count. Include headings in that evaluation, because project descriptions and website copy often place this construction there.

The supplied examples can justify a style rule, but the examined datasets do not support a claim that this family is disproportionately generated. Start at `bark` while testing ambiguity. Reserve `bite` for narrower forms whose legitimate uses have been excluded. Repetition may justify a document-level advisory even when one instance works.

The [newer dataset note](datasets.md) identifies sources for the next evaluation. Trace Commons contains inspected June 2026 README, project-plan, HTML, and code-comment artifacts. Nebius OpenHands contributes attributed Qwen3-Coder patches and commentary. WildChat-4.8M extends conversation coverage through July 2025, but its first rows are still from 2023.

## Checks

The probe's synthetic controls check the two supplied examples, a heading without `same`, and the useful alignment fragment. Complete clauses and an integrated participial modifier do not match the suffix probe. This establishes candidate collection, not production-rule accuracy.

The report's lint run exposed an existing false positive: `phrase.signposted-conclusion` flags the literal discussion of a sentence's `final word` as an announced conclusion. Preserve the wording until that rule has an approved correction. No production rule was changed for this research.
