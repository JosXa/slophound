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

A linter for prose written by language models. Feed it a document, a commit message, a PR description, a wiki page, anything with sentences in it. It returns the ones that make the text read like a machine wrote it, with line numbers and instructions for the fix. Markdown syntax is understood and masked; plain text works the same.

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

Deterministic. Same input, same output, no model in the loop. Rules are plain TOML that any agent can read, test, and repair when a finding is wrong.

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
| `--disable-category CAT[,CAT]` | Skip a whole rule file (`phrase`, `template`, `punct`, `verb`, `adj`, `doc`). |
| `--only ID[,ID]` | Run just these rules. |
| `--lang XX` | spaCy language code for the grammar layer. Non-English models download on demand. |
| `--skip-quotes` | Leave blockquotes unlinted. |
| `--no-footer` | Omit the false-positive instructions. |

Code blocks, inline code, URLs, link targets, tables, and HTML comments are never linted. Front matter is masked except for values the reader sees: a slide deck's `heading:`, `lede:` or `callout:`, a page's `title:` or `description:`, and list entries with `title:` and `detail:` are linted like paragraphs, while keys, one-word settings and `class:`/`style:`/`layout:` values stay hidden.

## How it works

Detection runs in three layers, ordered from cheapest to most expensive:

1. **Regex** for fixed phrases, sentence templates, and punctuation (`rules/phrase.toml`, `rules/template.toml`, `rules/punct.toml`). These bite.
2. **Dependency parsing** with spaCy for constructions that regex cannot tell apart from legitimate use: "the map holds three keys" passes, "that holds even under load" fires (`rules/verb.toml`, `rules/adj.toml`). These bark.
3. **Document statistics** for rhythm and repetition: uniform sentence length, repeated paragraph openers, triad density, bold-label bullet lists (`rules/doc.toml`). These sniff.

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
