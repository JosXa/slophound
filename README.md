<div align="center">
  <img src="assets/logo.png" alt="slophound: a bloodhound detective holding a red-marked page at arm's length" width="220">
  <h1>slophound</h1>
  <p><strong>Agents cannot see the slop they wrote. slophound can.</strong></p>
  <p>
    <img alt="Deterministic" src="https://img.shields.io/badge/deterministic-no%20LLM%20in%20the%20loop-2d2d2d">
    <img alt="Rules in TOML" src="https://img.shields.io/badge/rules-TOML-1f3a5f">
    <img alt="Runs with uv" src="https://img.shields.io/badge/runs%20with-uv-c8102e">
    <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-2d2d2d">
  </p>
</div>

A linter for prose written by language models. Feed it a document, a commit message, a PR description, a wiki page, anything with sentences in it. It returns the ones that make the text read like a machine wrote it, with line numbers and instructions for the fix. Markdown syntax is understood and masked, while plain text works the same.

```
docs/adr-014.md:12:1  bark   verb.buys-us
  That buys us a week of headroom before the migration.
  ^^^^^^^^^^^^
  "buys (us) X" is a Claude reflex for trading one thing for another. Name the trade: what was spent, what was gained, and for how long.

docs/adr-014.md:31:1  bite   template.not-x-but-y
  This isn't a cache problem. It's a consistency problem.
  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  Negation-then-reveal ("It's not X, it's Y"). Delete the negated half and state the positive claim.

1 bite, 1 bark, 0 sniffs · 1.4 findings per 100 words
```

## What it catches

A sample of the rule catalog. Each row pairs a real `example` sentence from a rule with a rewrite that passes.

| Found | Rule | Fix |
|---|---|---|
| This isn't a cache problem. It's a consistency problem. | `template.not-x-but-y` | The cache is consistent; the reads are stale. |
| Same benchmark, one year apart. | `template.verbless-pair` | We ran the same benchmark one year later. |
| Same object, new name, new roof. | `template.echo-triplet` | The object is unchanged; it has a new name and a new owner. |
| Three detection layers, cheapest first: | `template.count-opener` | Detection runs in three layers, ordered from cheapest to most expensive: |
| Tools, docs, and processes that actually work. | `template.triad-that-actually` | Tools and docs the team uses. |
| It's not about speed. It's about trust. Full stop. | `template.mic-drop` | Users need to trust the results more than they need speed. |
| That buys us a week of headroom. | `verb.buys-us` | The cache gives us a week before the migration. |
| That holds even under load. | `verb.holds` | The invariant survives 10k requests per second. |
| Two dropdowns carry the decision. | `verb.carries` | The two dropdowns record the decision, and the free-text field explains why. |
| The 2025 result is where most lean-file advice comes from. | `verb.copula-cleft` | Most lean-file advice traces back to the 2025 result. |
| Both sit at the top. | `verb.sits` | Both are frontier models. |
| The retry logic is load-bearing. | `phrase.load-bearing` | Every request depends on the retry logic. The word is banned outright, wall or no wall. |
| The unlock here is the shape of the problem. | `phrase.engineering-slang` | The problem is a scheduling problem, so the fix is a queue. |
| It's a surgical update, a minimal diff, and a clean fix. | `phrase.self-appraisal` | The change touches one function and adds no dependencies. |
| Each rule has to earn its keep. | `phrase.anthropomorphic-praise` | Each rule must fire on generated text and stay silent on human text. |
| Here's the thing: we never measured it. | `phrase.false-suspense` | We never measured it. |
| It's worth noting that the tests are slow. | `phrase.restatement` | The tests are slow. |
| Delve into the traces to leverage the insights. | `phrase.ai-vocabulary` | Read the traces. |
| In conclusion, the migration is done. | `phrase.signposted-conclusion` | The migration is done. |
| I hope this helps! Let me know if you'd like me to expand. | `phrase.assistant-pleasantry` | (delete) |
| The tenant database connection pool size is fixed. | `noun.cluster-four` | The connection pool for the tenant database has a fixed size. |
| A cache is fast — until it lies. | `punct.em-dash` | A cache is fast until it lies. |
| Five paragraphs in a row opening with "The linter" | `doc.repeated-paragraph-opener` | Vary the subject, or merge the paragraphs. |

Deterministic: the same input produces the same findings on every run, and no model sits in the loop. Rules are plain TOML that any agent can read, test, and repair when a finding is wrong.

## Usage

Requires only [`uv`](https://docs.astral.sh/uv/). The first run downloads spaCy and its English model (about 15 seconds); later runs start in under a second.

```sh
./slophound README.md docs/*.md     # lint files
cat draft.txt | ./slophound -       # lint stdin
./slophound test                    # run the rule and corpus tests
```

Findings come in three tiers. A **bite** is a fixed phrase or sentence template; the match is exact and must be fixed. The grammar layer produces **barks**, which are inferred and almost always right, and the document statistics produce **sniffs**, rhythm hints for the writer. Exit code 0 when there are no bites, 1 when at least one bite was found, 2 when the tool itself failed. Barks and sniffs never change the exit code unless `--strict` is set.

For CI logs and tools that parse linter output, `--formal` (or `SLOPHOUND_FORMAL=1`) prints the same report with `error`, `warning`, and `suggestion` instead.

| Flag | Effect |
|---|---|
| `--strict` | Barks count as bites for the exit code. |
| `--formal` | Print `error` / `warning` / `suggestion` instead of `bite` / `bark` / `sniff`. Same as `SLOPHOUND_FORMAL=1`. |
| `--disable ID[,ID]` | Skip specific rules for this run. |
| `--disable-category CAT[,CAT]` | Skip a whole rule file (`phrase`, `template`, `punct`, `verb`, `adj`, `noun`, `doc`). |
| `--only ID[,ID]` | Run just these rules. |
| `--no-emoji` | Also flag emoji in prose. Off by default: emoji are a taste, not a machine tell. |
| `--lang XX` | spaCy language code for the grammar layer. Non-English models download on demand. |
| `--skip-quotes` | Leave blockquotes unlinted. |
| `--no-footer` | Omit the false-positive instructions. |

Code blocks, inline code, URLs, link targets, tables, and HTML comments are never linted. Front matter is masked except for values the reader sees: a slide deck's `heading:`, `lede:` or `callout:`, a page's `title:` or `description:`, and list entries with `title:` and `detail:` are linted like paragraphs, while keys, one-word settings and `class:`/`style:`/`layout:` values stay hidden.

## How it works

Detection runs in three layers, ordered from cheapest to most expensive:

1. **Regex** for fixed phrases, sentence templates, and punctuation (`rules/phrase.toml`, `rules/template.toml`, `rules/punct.toml`). These bite.
2. **Dependency parsing** with spaCy for constructions that regex cannot tell apart from legitimate use: "the worker holds a mutex" passes, "that holds even under load" fires (`rules/verb.toml`, `rules/adj.toml`, `rules/noun.toml`). These bark, except for noun clusters: four or more nouns bite, three only sniff.
3. **Document statistics** for rhythm and repetition: uniform sentence length, repeated paragraph openers, triad density, bullet lists with bold labels (`rules/doc.toml`). These sniff.

Every rule has its own message, at least one `example` sentence it must fire on, and at least one `acceptable` sentence it must leave alone. `./slophound test` checks all of them, plus a small corpus of human and generated text under `tests/corpus/`, plus this repository's own Markdown.

## False positives

There is no ignore file and no inline suppression comment. When a finding is wrong, the rule is wrong: open the rule file the report points at, tighten the pattern or add the sentence to `acceptable`, run `./slophound test`, and send the change upstream. The footer of every report repeats these steps for the agent reading it.

## Contributing

Enable the pre-commit hook once per clone so your own Markdown gets linted:

```sh
git config core.hooksPath .githooks
```

See the Vision section in [AGENTS.md](./AGENTS.md) for what this project is and is not.

## License

MIT
