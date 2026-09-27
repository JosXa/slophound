# Repeated predicates and clause cadence

Exploratory study, 27 September 2026. This records an investigation, including its limits. Dataset selection guidance lives in [CORPORA.md](../../CORPORA.md).

## Recommendation

Keep investigating the combination of balanced clauses, a repeated predicate, and a longer concluding clause. Repeating a verb alone is too broad for a rule. The probe described below found more repeated predicates per word in human prose than in Claude prose within each Ghostbuster domain.

The most promising eventual severity is `sniff`, based on repeated use within a document. The evidence does not yet justify a threshold or a production rule for technical documentation. A single occurrence can explain a comparison well.

## Material inspected

The analysis retained 9,238 texts containing 5,088,408 prose words. These include separate assistant messages, so they are not all independent documents. Selection retained 200 to 5,000 words after slophound masking, counted in paragraph and list blocks. Headings and code do not contribute to that count.

The [Ghostbuster data](https://github.com/vivek3141/ghostbuster-data/tree/86ebd72590556a81622986fab736ab9227a948af) supplied essays, news, and creative writing labelled human, Claude, or GPT. Its [paper](https://arxiv.org/html/2305.15047v3) identifies the GPT generations as ChatGPT and provides a separate Claude evaluation collection. The exact Claude snapshot is unspecified. Only original generations were selected. Prompt variants and paraphrases were excluded. Equal filenames in different authorship groups do not establish matched prompts.

The technical control consists of [Rust RFCs at the end of 2021](https://github.com/rust-lang/rfcs/tree/16f3bc024bdef9db7502ffbefeb602c37cee20bf). Of 512 Markdown proposals, 475 met the length limits. This supplies historical technical writing, with a different domain from the Ghostbuster material.

Modern Claude required a separate search through agent traces:

- The first 1,000 rows of the [SWE-smith tool split](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories/tree/08e109b4a59eaeebf80e4675cd125d42e7ac99a4) contained 991 Claude 3.7 Sonnet runs and nine Claude 3.5 Sonnet runs. Extraction found no Markdown paths in generated patches or recognized file creation calls. It retained 116 assistant messages before applying slophound's stricter word count, which retained 99.
- All 260 rows of [CC-Bench](https://huggingface.co/datasets/zai-org/CC-Bench-trajectories/tree/792c6d3221db4d9ed475702ed61a176dd8948152) included 52 Claude Sonnet 4 runs. Those contained eight Markdown file writes. One README and five assistant messages met the length limit.
- The README is a complete `Write` call for a Python cron library, attributed to `claude-sonnet-4-20250514`. It contains 385 prose words under slophound masking. Locate it in train row 96, task 20, trajectory message 62, content block 0. Its file path in the task is `/app/projects/python-cron/README.md`.

One README is insufficient to estimate how often modern Claude uses this construction in documentation. Coding-agent explanations also differ from finished design documents. The first 1,000 SWE-smith rows are a deterministic convenience sample.

The Hugging Face viewer serves live `main`. A separate fetch verified the README row's revision and confirmed that no cells were truncated. The initial bulk extraction did not retain those response fields. A later audit encountered HTTP 429 before verifying every selected row. Treat the other modern-Claude excerpts as provisional. This limitation does not affect the Ghostbuster or Rust results, which came from immutable Git revisions.

## Probe and measurements

[The probe](../../tools/cadence_probe.py) searches comma- or semicolon-separated pieces of a sentence. Its broad surface test looks for the same word near the beginning of adjacent pieces with different prefixes. A parser then checks whether that word is a verb with an explicit subject in each piece. This still admits subordinate clauses and parser errors. The counts measure candidates, not confirmed writing defects.

The more specific surface test requires exactly three pieces. The first two each have three to eight words, repeat a word in a comparable position, and the final piece starts with "and". That final piece has at least eight words and is at least 1.5 times as long as the longer opening piece. These bounds were chosen for exploration. They have not been calibrated.

| Corpus | Texts | Prose words | Parsed echo candidates | Candidates per 10,000 words |
| --- | ---: | ---: | ---: | ---: |
| Claude essays | 1,000 | 457,062 | 43 | 0.94 |
| ChatGPT essays | 1,000 | 570,496 | 25 | 0.44 |
| Human essays | 962 | 624,134 | 87 | 1.39 |
| Claude news | 1,000 | 395,543 | 14 | 0.35 |
| ChatGPT news | 986 | 507,275 | 31 | 0.61 |
| Human news | 980 | 502,685 | 37 | 0.74 |
| Claude creative writing | 981 | 388,195 | 60 | 1.55 |
| ChatGPT creative writing | 904 | 487,939 | 81 | 1.66 |
| Human creative writing | 845 | 509,471 | 117 | 2.30 |
| Historical Rust RFCs | 475 | 620,483 | 107 | 1.72 |

The specific surface test returned 28 sentences: three from Claude, 20 from ChatGPT, four from human creative writing, and one from Rust. All 28 were inspected. They include repeated nouns, passive auxiliaries, subordinate clauses, and lists without separate subjects. Thus even this narrower surface shape needs grammatical review. The accompanying [review records](review.json) classify those candidates by construction, without assigning a quality verdict.

The 105 retained modern-Claude texts produced 20 broad surface candidates, all in Claude 3.7 assistant messages. None passed the parsed echo test or the specific surface test. This result does not establish absence: code masking can remove a clause's subject, and the sample contains very little finished documentation.

## Observed constructions

### Two short clauses followed by a longer clause

Claude, [creative sample 240](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/claude/240.txt):

> The kids were in bed, the dishes were done, and I had a few hours of peace before having to do it all over again tomorrow.

This has the requested cadence, with "were" repeated before a longer final clause. The parser treats the second "were" as a passive auxiliary. Whether "done" describes a state or a completed action affects the parse without changing the audible repetition.

ChatGPT, [creative sample 715](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/gpt/715.txt):

> Days turn into nights, nights turn into days, and you lose track of your own existence.

This repeats a lexical verb and ends in a longer clause that describes the experience. It is a close structural match to the motivating sentence.

The same construction occurs in [human creative sample 624](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/human/624.txt):

> His carpet was wet, his blanket was wet, and he was pretty certain mold was going to grow underneath his carpets if he didn't do something about it right now.

Authorship therefore cannot decide whether this construction needs revision.

### Three clauses with the same predicate

Claude, [creative sample 477](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/claude/477.txt):

> Conversations felt forced, laughter felt less frequent, and intimacy felt routine.

This repeats the predicate across all three clauses, without a longer ending. It is distinct from a list of three nouns. The current `doc.triad-density` regex counts short lists of words and does not represent this grammatical construction.

Claude also uses the form to explain a taxonomy in [essay 772](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/essay/claude/772.txt):

> The rational part loves truth and knowledge, the spirited part loves honor and victory, and the appetitive part loves bodily pleasures and material goods.

The comparable structure helps a reader compare three categories. Repeated use, purpose, and surrounding prose matter more than the presence of three clauses alone.

### Two clauses with a figurative ending

Claude, [creative sample 149](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/claude/149.txt):

> Her daughter needed medicine, and Jill needed a miracle.

The second complement shifts from a concrete need to a figurative one. The balance makes that shift emphatic. A grammatical test could find the repetition, but deciding whether the ending overstates the point requires meaning and context.

### Reversed participants

Claude, [creative sample 293](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/claude/293.txt):

> She gave me a window into the world, and I gave her a conscience.

The participants exchange grammatical roles while the verb repeats. This is another form of deliberate balance, with a different mechanism from clause length.

### Chained progression with an omitted verb

ChatGPT, [creative sample 297](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/gpt/297.txt):

> Days turned into weeks, weeks into months, and yet the memory of that fleeting connection remained etched in their hearts.

The second clause omits "turned". A rule requiring a repeated verb would miss the cadence. The same progression occurs in [human creative sample 876](https://github.com/vivek3141/ghostbuster-data/blob/86ebd72590556a81622986fab736ab9227a948af/wp/human/876.txt), with dreams, eons, and eternities.

## Technical comparisons that must remain acceptable

[RFC 2437](https://github.com/rust-lang/rfcs/blob/16f3bc024bdef9db7502ffbefeb602c37cee20bf/text/2437-rustfmt-stability.md#L180) uses matching grammar to distinguish two versioning rules:

> Major formatting changes cause a major version increment, minor formatting changes cause a minor version increment

[RFC 1444](https://github.com/rust-lang/rfcs/blob/16f3bc024bdef9db7502ffbefeb602c37cee20bf/text/1444-union.md#L368) similarly contrasts unions and structs with "unions represent a sum type, while structs represent a product type." [RFC 0141](https://github.com/rust-lang/rfcs/blob/16f3bc024bdef9db7502ffbefeb602c37cee20bf/text/0141-lifetime-elision.md#L97) repeats "refers to" when defining input and output types.

Such comparisons are common in documentation. Rewriting them merely to vary the verb can make the distinction harder to follow.

## Implications for a rule

1. Preserve separate features for two repeated predicates, three repeated predicates, a longer final clause, reversed participants, and an omitted repeated verb. They are related constructions with different failure cases.
2. Use grammatical subjects and clause relationships to reject noun lists. Do not equate every comma with a clause boundary. Handle auxiliaries separately from lexical predicates.
3. Preserve technical comparisons, definitions, protocols, and mappings as regression examples. Also preserve valid generated prose. Human authorship is not the definition of acceptable writing.
4. Test repetition across a document before selecting a severity. An isolated balanced sentence provides insufficient evidence of tiresome rhythm. No document-level threshold was measured here.
5. Collect complete modern-Claude design documents before drawing conclusions about that model or register. Label construction and editorial usefulness separately, then evaluate on documents withheld from rule development.

The existing `template.stacked-anaphora` rule concerns repeated sentence openings. It does not cover changed subjects with a repeated predicate inside one sentence. A new rhythm metric could address that gap if further evaluation supports it.

## Parser limitation

The motivating sentence is an essential regression case:

> Red means fix it, green means done, and the same text produces the same findings on every run.

With `en_core_web_sm` 3.8.0, both occurrences of "means" are tagged as nouns. A rule requiring a parsed verb misses the sentence that motivated the investigation. The surface probe retains it for review, but that is not sufficient validation for a production detector.

## Reproduction and limits

Run `tools/cadence_probe.py --help` through `uv run --script`. Supply local Ghostbuster and Rust RFC checkouts with `--ghostbuster` and `--rust`, plus an output directory. The script reads the immutable revisions named above with `git archive`. Fetch those revisions first if a checkout lacks them. It leaves the checkout branch unchanged.

The script uses spaCy 3.8.16, `en_core_web_sm` 3.8.0, and the repository's Markdown masking and sentence segmentation. It records selected source IDs, hashes, word counts, and every candidate with its original text and location. Extra JSONL inputs use `id`, `source_url`, `model`, `text`, and optionally `genre` and `dataset_revision`. Modern-Claude extraction also needs the row and message locators described above.

Exact duplicate text is removed within each group. Documents are ordered by content hash, with a maximum of 1,000 per group. This does not remove near-duplicates, repeated prompts, or related messages from one trajectory. The analysis does not estimate detector precision, recall, or statistical significance. These exploratory counts preceded the production rules. See [the subsequent rule evaluation](rule-evaluation.json) for their scope and results.
