# Adding rules

Scope: adding, widening, or repairing a rule in `rules/*.toml`. Field syntax per layer is documented at the top of each rule file; this guide covers the judgement around a rule: whether it belongs, which tier it gets, how to write examples that prove it, how to measure the noise it adds, and the escaping traps that have already cost time.

Contract: a rule ships only when `./slophound test` is green, the repo's own documents still pass, and the rule has fired on at least one real generated sentence and stayed silent on at least one real human sentence that looks similar.

## Does it belong

A rule usually catches a construction a model produces where a person would have written something plainer. Use origin, source, or history instead of `provenance`, as appropriate. Existing code and quotation masking still applies.

- Bare words are blacklists. `robust`, `never`, `sits`, `actually`, `framework` appear in human technical prose at the same rate as in generated prose. Gate a word with the company it keeps: `the shape of the problem`, `sits at the intersection of`, `buys us`. If the only pattern you can write is one word, you have a vocabulary preference and not a rule.
- Register is not slop. Passive voice, formal vocabulary (`commence`, `sufficient`), and long sentences were measured on the human corpus and on generated text, and both fired at the same rate. Those rules were deleted. If a candidate would flag good human writing as often as generated writing, drop it.
- One occurrence has to be wrong on its own for a phrase or template rule. If a construction is fine once and tiresome at three, it is a document statistic (`doc.*`), and the rule is a threshold on a metric in `hound/layer_doc.py`.
- The example must come from somewhere. The best source is a sentence a model wrote, ideally one you or the user just caught. Upstream catalogs (unsloppify, unslop, antislop lists) are candidates to probe, never lists to paste: most of them are fiction register or bare words.

## Which tier

Severity is a claim about confidence, so pick it by how the match is found.

| Tier | Exit code | How the match is found | Typical categories |
| --- | --- | --- | --- |
| `bite` | fails | exact phrase, sentence template, glyph | `phrase`, `template`, `punct`, `noun.cluster-four` |
| `bark` | passes | parser-inferred, or a phrase family with real false-positive risk | `verb`, `adj`, `phrase.buzzword-vocabulary` |
| `sniff` | passes | document statistic crossing a threshold, or a hint too common in human text to advise on | `doc`, `noun.cluster-three` |

A phrase rule may be a bark when the family is broad and you cannot list every literal sense in `unless`. A verb rule is never a bite: `en_core_web_sm` mis-tags often enough (`lands` as a noun, `token` as a verb, `burns` as a noun) that a grammar finding must stay advisory. When two rules grade the same construction (`noun.cluster-four` and `noun.cluster-three`), the spaCy layer shadows the weaker finding within a category, so the stronger rule needs no exclusion for the weaker shape.

Promote or demote a tier only after measuring noise (below), never from taste.

## Which layer

Cheapest layer that can separate the slop from the literal use:

1. `phrase` when the words themselves are the signal.
2. `template` when the shape is the signal and the content varies ("It's not X. It's Y."). Keep every wildcard bounded (`[^.!?\n]{1,60}`) so a match cannot swallow a paragraph, and anchor to a sentence start with `sentence_start = true` or `(^|(?<=[.!?] ))` when the shape only counts at the start.
3. `punct` when the glyph is the signal. These run on the masked view where typographic characters are still original, so name them with `\u` escapes.
4. `verb`, `adj`, `noun` when the same words are fine in one grammatical role and slop in another. Before writing a DependencyMatcher pattern, look at the actual parse:

   ```sh
   tools/parse.py "That holds even under load." "The worker holds a mutex."
   ```

   It prints `i text lemma pos tag dep head` per token from the same model the linter uses. Write the pattern against what the parser produces for your examples, then check each `acceptable` sentence parses differently. If the parser gets your best example wrong, fall back to a `phrase` rule for that surface form instead of fighting the parser.
5. `doc` when only aggregate counts tell. Add the metric function to `hound/layer_doc.py` under the `@metric` decorator, document it in the `rules/doc.toml` header, then add the rule with `threshold` and `min_sentences` or `min_paragraphs` so short texts cannot trip it.

## Examples and acceptables

`./slophound test` runs every rule alone against its own `example` and `acceptable` lists, so a rule is exactly as good as those lists.

- Each `example` is one sentence the rule must fire on. Use the sentence that motivated the rule, verbatim. Add one per alternation branch you care about, because a branch without an example is a branch nobody has verified.
- Each `acceptable` is one sentence that shares surface material with the pattern and must stay silent: the literal sense (`The worker holds a mutex`), the same words in a different grammatical role (`The climbing holds are loose`), the honest rewrite the message recommends. The rewrite belongs in `acceptable` so a fix suggested by the message can never itself be flagged.
- A rule with an empty `acceptable` list is rejected by the loader on purpose.
- Prefer `unless` over a longer `pattern` for carving out literal senses. `unless` is tested against the whole containing sentence, so it can look at words far from the match. Check that `unless` does not suppress your own example: `phrase.cliche-metaphors` once listed `paint` in `unless` and silenced its own `fresh coat of paint` example.
- Messages state the problem, quote the shape in parentheses, and give the fix in the same voice the rule enforces. The report has no second lookup, so the message carries everything.

## Jev review

Use Jev for a judgment that a regex, a parse, or a count cannot settle. A rule of any severity can declare a `jev_veto` table to ask whether its finding should be removed. This runs automatically during linting when a key resolves. Two rules use it today: `noun.cluster-three` asks whether the stacked nouns are an established term, and `punct.semicolon-splice` asks whether the semicolon belongs between its two clauses. The second is a bark, so a run with a key and a run without one can exit differently under `--strict`; that is the intended trade.

```toml
[rule.jev_veto]
instructions = "Is the complete matched expression an established term in this sentence's field?"
threshold = 0.7
criteria.true = "The complete expression names a recognized concept in conventional usage."
criteria.false = "The expression is improvised or merely understandable from its parts."
```

The table belongs to the preceding `[[rule]]`; put it after that rule's other fields. All fields shown are required. The threshold is P(yes), must be greater than 0.5 and at most 1, and includes equality. Unknown fields are rejected.

Each question gets one finding's `sentence`, `matched_text`, and `tokens` from the masked prose. Small batches stay within a document block, with a question referring to its own item. Write criteria about the complete expression in that context. A yes removes the finding only at or above the threshold. Uncertain, missing, or invalid answers keep it. A request failure keeps the document's deterministic findings.

The rule's `example` and `acceptable` lists still test deterministic detection. `./slophound test` uses `Engine.lint_deterministic` so a configured key cannot hide a broken rule or change the corpus checks. Cover the veto separately in `tests/test_jev.py` with mock responses for both sides of the threshold and failures. Check the prompt against real terms and improvised phrases through the pinned Jev model before changing its criteria or threshold.

## Measure noise before locking the tier

Run the candidate on real text with `--only <id> --no-footer` and read every hit:

```sh
./slophound --only phrase.new-rule --no-footer README.md AGENTS.md docs/*.md
./slophound --only phrase.new-rule --no-footer tests/corpus/human/*.md
./slophound --only phrase.new-rule --no-footer tests/corpus/generated/*.md
printf 'One sentence to try.\n' | ./slophound --only phrase.new-rule --no-footer -
```

Also run it on whatever human-written documents are at hand outside the repo (wiki exports, slide decks with `--disable-category doc`, older READMEs). The human corpus in `tests/corpus/human/` must stay at zero bites and under one bark per hundred words. `./slophound test` enforces that ceiling. If the candidate fires on human text, each hit becomes either an `acceptable` (and a tighter pattern) or evidence that the rule is a register preference and should go.

The repo's own Markdown must pass with zero bites. When a new rule catches a sentence in `README.md` or `AGENTS.md`, fix the sentence, do not weaken the rule, unless the sentence is a false positive by the standard above.

## Escaping traps

- TOML basic strings (`"..."`) process backslashes: `\b` becomes a backspace. Either double every backslash (`"\\b"`) or use a literal string (`'\b'`). Literal strings cannot contain `'`; write `\x27` for an apostrophe inside one.
- A trailing `\b` after an alternation whose last branch ends in punctuation (`:`, `!`, `?`, `\.`, `,`) never matches. Close such groups with `(?!\w)` instead.
- Generating TOML through a shell heredoc or a Python string doubles backslashes silently. Read the file back after writing it.
- The prose view blanks Markdown syntax: `#`, `**`, `*`, `_`, list bullets, `>` are spaces. A phrase or template pattern must not expect them. Only `punct` rules see the original glyphs on the masked view. Headings run phrase rules only, so a template that needs a heading has to be a phrase rule with `headings = true`.
- Inline code, fenced code, URLs, link targets, tables, HTML comments, and text inside double quotes are masked. Quoting a bad phrase in backticks or quotes is how the repo's own documents talk about slop without tripping the linter, so use that in messages and docs.
- The engine drops a weaker finding fully contained in a stronger one. When two rules should both fire on overlapping text, verify each with `--only`, because the combined report may show only one.

## Ship it

1. `./slophound test` green (every rule solo, masking checks, corpus ceilings, own docs).
2. `./slophound README.md AGENTS.md docs/*.md` prints no findings.
3. Commit the rule with its motivating sentence in the message body. Commits in this repo are made with `git -c commit.gpgsign=false commit`.
4. If the rule corrects a false positive reported by a user, explain the change and offer to contribute it. Ask before submitting a PR.

## Repairing a false positive

A false positive is a rule bug. Preserve the legitimate wording and recommend a correction to the operator. After they approve preparing one, locate the rule by ID in a repository checkout. Reported paths are for inspection and may point into a package cache, which must remain unchanged.

Add the sentence to `acceptable` and confirm the test fails. Tighten `pattern`, add an `unless` for the legitimate sense, or adjust the severity according to the evidence. Delete a rule if it cannot distinguish the target from acceptable writing. Rerun `./slophound test` and check the original document with the corrected checkout. Follow the operator's authorization for contribution work.
