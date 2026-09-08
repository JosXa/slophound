# Adding rules

Scope: adding, widening, or repairing a rule in `rules/*.toml`. Field syntax per layer is documented at the top of each rule file; this guide covers the judgement around a rule: whether it belongs, which tier it gets, how to write examples that prove it, how to measure the noise it adds, and the escaping traps that have already cost time.

Contract: a rule ships only when `./slophound test` is green, the repo's own documents still pass, and the rule has fired on at least one real generated sentence and stayed silent on at least one real human sentence that looks similar.

## Does it belong

A rule catches a construction a model produces where a person would have written something plainer. It never catches a topic, a register, or a single word.

- Bare words are blacklists. `robust`, `never`, `sits`, `actually`, `framework` appear in human technical prose at the same rate as in generated prose. Gate a word with the company it keeps: `the shape of the problem`, `sits at the intersection of`, `buys us`. If the only pattern you can write is one word, you have a vocabulary preference and not a rule.
- Register is not slop. Passive voice, formal vocabulary (`commence`, `sufficient`), and long sentences were measured on the human corpus and on generated text; both fired at the same rate. Those rules were deleted. If a candidate would flag good human writing as often as generated writing, drop it.
- One occurrence has to be wrong on its own for a phrase or template rule. If a construction is fine once and tiresome at three, it is a document statistic (`doc.*`), and the rule is a threshold on a metric in `hound/layer_doc.py`.
- The example must come from somewhere. The best source is a sentence a model wrote, ideally one you or the user just caught. Upstream catalogs (unsloppify, unslop, antislop lists) are candidates to probe, never lists to paste: most of them are fiction register or bare words.

## Which tier

Severity is a claim about confidence, so pick it by how the match is found.

| Tier | Exit code | How the match is found | Typical categories |
| --- | --- | --- | --- |
| `bite` | fails | exact phrase, sentence template, glyph | `phrase`, `template`, `punct`, `noun.cluster-four` |
| `bark` | passes | parser-inferred, or a phrase family with real false-positive risk | `verb`, `adj`, `noun.cluster-three`, `phrase.buzzword-vocabulary` |
| `sniff` | passes | document statistic crossing a threshold | `doc` |

A phrase rule may be a bark when the family is broad and you cannot list every literal sense in `unless`. A verb rule is never a bite: `en_core_web_sm` mis-tags often enough (`lands` as a noun, `token` as a verb, `burns` as a noun) that a grammar finding must stay advisory. When two rules grade the same construction (`noun.cluster-four` and `noun.cluster-three`), the spaCy layer shadows the weaker finding within a category, so the stronger rule needs no exclusion for the weaker shape.

Promote or demote a tier only after measuring noise (below), never from taste.

## Which layer

Cheapest layer that can separate the slop from the literal use:

1. `phrase` when the words themselves are the signal.
2. `template` when the shape is the signal and the content varies ("It's not X. It's Y."). Keep every wildcard bounded (`[^.!?\n]{1,60}`) so a match cannot swallow a paragraph, and anchor to a sentence start with `sentence_start = true` or `(^|(?<=[.!?] ))` when the shape only counts at the start.
3. `punct` when the glyph is the signal. These run on the masked view where typographic characters are still original; name them with `\u` escapes.
4. `verb`, `adj`, `noun` when the same words are fine in one grammatical role and slop in another. Before writing a DependencyMatcher pattern, look at the actual parse:

   ```sh
   tools/parse.py "That holds even under load." "The map holds three keys."
   ```

   It prints `i text lemma pos tag dep head` per token from the same model the linter uses. Write the pattern against what the parser produces for your examples, then check each `acceptable` sentence parses differently. If the parser gets your best example wrong, fall back to a `phrase` rule for that surface form instead of fighting the parser.
5. `doc` when only aggregate counts tell. Add the metric function to `hound/layer_doc.py` under the `@metric` decorator, document it in the `rules/doc.toml` header, then add the rule with `threshold` and `min_sentences` or `min_paragraphs` so short texts cannot trip it.

## Examples and acceptables

`./slophound test` runs every rule alone against its own `example` and `acceptable` lists, so a rule is exactly as good as those lists.

- Each `example` is one sentence the rule must fire on. Use the sentence that motivated the rule, verbatim. Add one per alternation branch you care about; a branch without an example is a branch nobody has verified.
- Each `acceptable` is one sentence that shares surface material with the pattern and must stay silent: the literal sense (`The contractor confirmed the wall is load-bearing`), the same words in a different grammatical role (`The map holds three keys`), the honest rewrite the message recommends. The rewrite belongs in `acceptable` so a fix suggested by the message can never itself be flagged.
- A rule with an empty `acceptable` list is rejected by the loader on purpose.
- Prefer `unless` over a longer `pattern` for carving out literal senses. `unless` is tested against the whole containing sentence, so it can look at words far from the match. Check that `unless` does not suppress your own example: `phrase.cliche-metaphors` once listed `paint` in `unless` and silenced its own `fresh coat of paint` example.
- Messages state the problem, quote the shape in parentheses, and give the fix in the same voice the rule enforces. The report has no second lookup, so the message carries everything.

## Measure noise before locking the tier

Run the candidate on real text with `--only <id> --no-footer` and read every hit:

```sh
./slophound --only phrase.new-rule --no-footer README.md AGENTS.md docs/*.md
./slophound --only phrase.new-rule --no-footer tests/corpus/human/*.md
./slophound --only phrase.new-rule --no-footer tests/corpus/generated/*.md
printf 'One sentence to try.\n' | ./slophound --only phrase.new-rule --no-footer -
```

Also run it on whatever human-written documents are at hand outside the repo (wiki exports, slide decks with `--disable-category doc`, older READMEs). The human corpus in `tests/corpus/human/` must stay at zero bites and under one bark per hundred words; `./slophound test` enforces that ceiling. If the candidate fires on human text, each hit becomes either an `acceptable` (and a tighter pattern) or evidence that the rule is a register preference and should go.

The repo's own Markdown must pass with zero bites. When a new rule catches a sentence in `README.md` or `AGENTS.md`, fix the sentence, do not weaken the rule, unless the sentence is a false positive by the standard above.

## Escaping traps

- TOML basic strings (`"..."`) process backslashes: `\b` becomes a backspace. Either double every backslash (`"\\b"`) or use a literal string (`'\b'`). Literal strings cannot contain `'`; write `\x27` for an apostrophe inside one.
- A trailing `\b` after an alternation whose last branch ends in punctuation (`:`, `!`, `?`, `\.`, `,`) never matches. Close such groups with `(?!\w)` instead.
- Generating TOML through a shell heredoc or a Python string doubles backslashes silently. Read the file back after writing it.
- The prose view blanks Markdown syntax: `#`, `**`, `*`, `_`, list bullets, `>` are spaces. A phrase or template pattern must not expect them; only `punct` rules see the original glyphs on the masked view. Headings run phrase rules only, so a template that needs a heading has to be a phrase rule with `headings = true`.
- Inline code, fenced code, URLs, link targets, tables, HTML comments, and text inside double quotes are masked. Quoting a bad phrase in backticks or quotes is how the repo's own documents talk about slop without tripping the linter; use that in messages and docs.
- The engine drops a weaker finding fully contained in a stronger one. When two rules should both fire on overlapping text, verify each with `--only`, because the combined report may show only one.

## Ship it

1. `./slophound test` green (every rule solo, masking checks, corpus ceilings, own docs).
2. `./slophound README.md AGENTS.md docs/*.md` prints no findings.
3. Commit the rule with its motivating sentence in the message body. Commits in this repo are made with `git -c commit.gpgsign=false commit`.
4. If the rule was added to fix a false positive reported by a user, tell them which rule changed and offer the fix upstream; the report footer asks agents to do the same.

## Repairing a false positive

A false positive is a rule bug. Never edit the document to route around it, and never add suppression comments; there are none. Open the rule file the footer points at, then in order of preference: add the sentence to `acceptable` and tighten `pattern`; add an `unless` for the literal sense; demote the tier if the family is inherently ambiguous; delete the rule if human text fires it as often as generated text. Rerun `./slophound test`.
