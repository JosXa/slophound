<div align="center">
  <img src="assets/logo.png" alt="slophound: a bloodhound detective holding a red-marked page at arm's length" width="220">
  <h1>slophound</h1>
  <p><strong>Agents cannot see the slop they wrote. slophound can.</strong></p>
  <p>A deterministic core with Jev to resolve ambiguous findings.</p>
  <p>
    <img alt="Deterministic core" src="https://img.shields.io/badge/core-deterministic-2d2d2d">
    <a href="https://typesafe.ai/blog/introducing-system-one-models-and-jev"><img alt="Jev for judgment" src="https://img.shields.io/badge/Jev-judgment-1f3a5f"></a>
    <img alt="Rules in TOML" src="https://img.shields.io/badge/rules-TOML-1f3a5f">
    <img alt="Runs with uv" src="https://img.shields.io/badge/runs%20with-uv-c8102e">
    <img alt="License MIT" src="https://img.shields.io/badge/license-MIT-2d2d2d">
  </p>
</div>

A linter for prose written by language models. Feed it a document, a commit message, a PR description, a wiki page, anything with sentences in it. It returns the ones that make the text read like a machine wrote it, with line numbers and instructions for the fix. Markdown syntax is understood and masked, while plain text works the same.

Regex, grammar, and document statistics find the patterns. [Jev](#jev-for-contextual-judgment) checks ambiguous findings in context: when three nouns form an established term such as "database connection pool", it can remove the finding so you can keep the term.

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

A sample of the rule catalog, with examples and suggested revisions.

| Found | Rule | Fix |
|---|---|---|
| This isn't a cache problem. It's a consistency problem. | `template.not-x-but-y` | The cache returns stale data. |
| Same benchmark, one year apart. | `template.verbless-pair` | We ran the same benchmark one year later. |
| Same object, new name, new roof. | `template.echo-triplet` | The object is unchanged; it has a new name and a new owner. |
| Three detection layers, cheapest first: | `template.count-opener` | Detection runs in three layers, ordered from cheapest to most expensive: |
| Tools, docs, and processes that actually work. | `template.triad-that-actually` | The team uses these tools, documents, and processes daily. |
| It's not about speed. It's about trust. Full stop. | `template.mic-drop` | Users need to trust the results more than they need speed. |
| That buys us a week of headroom. | `verb.buys-us` | With the cache enabled, we can delay migration by a week. |
| That holds even under load. | `verb.holds` | This remains true under load. |
| Two dropdowns carry the decision. | `verb.carries` | Select the decision using the two dropdowns, then explain your choice in the text field. |
| The 2025 result is where most lean-file advice comes from. | `verb.copula-cleft` | Most lean-file advice is based on the 2025 result. |
| Both sit at the top. | `verb.sits` | Both are frontier models. |
| The retry logic is load-bearing. | `phrase.load-bearing` | Every request depends on the retry logic. |
| The unlock here is the shape of the problem. | `phrase.engineering-slang` | Requests need scheduling, so we use a queue. |
| It's a surgical update, a minimal diff, and a clean fix. | `phrase.self-appraisal` | The update changes one function and adds no dependencies. |
| Each rule has to earn its keep. | `phrase.anthropomorphic-praise` | Each rule must detect its target pattern and avoid false positives. |
| Here's the thing: we never measured it. | `phrase.false-suspense` | We never measured it. |
| It's worth noting that the tests are slow. | `phrase.restatement` | The tests are slow. |
| Delve into the traces to leverage the insights. | `phrase.ai-vocabulary` | Read the traces. |
| In conclusion, the migration is done. | `phrase.signposted-conclusion` | The migration is done. |
| I hope this helps! Let me know if you'd like me to expand. | `phrase.assistant-pleasantry` | (delete) |
| The tenant database connection pool size is fixed. | `noun.cluster-four` | The connection pool for the tenant database has a fixed size. |
| A cache is fast — until it lies. | `punct.em-dash` | A cache can return results quickly even when they are incorrect. |
| Five paragraphs in a row opening with "The linter" | `doc.repeated-paragraph-opener` | Combine repeated points and remove unnecessary repetition. |

The deterministic core produces the same findings for the same input with the same rules and parser. Jev can remove findings after detection for the rules that ask it to, so the report and the exit code may differ between a run with a key and a run without one. Rules and Jev criteria are plain TOML that any agent can read, test, and repair when a finding is wrong.

## Usage

Install [`uv`](https://docs.astral.sh/uv/), then run the tool directly from Git. This requires Git and SSH access to the repository. The first run downloads Python dependencies and the English spaCy model, which `uv` caches for later runs.

```sh
uvx --python 3.13 --from 'git+ssh://git@github.com/JosXa/slophound.git' slophound draft.md
```

In a source checkout, the existing script works too:

```sh
./slophound README.md docs/*.md     # lint files
cat draft.txt | ./slophound -       # lint stdin
./slophound test                    # run the rule and corpus tests
```

Findings come in three tiers. A **bite** requires a correction. A **bark** is advisory, and a **sniff** suggests something to review. Exit code 0 means there are no bites, 1 means at least one bite was found, and 2 means the tool itself failed. `--strict` also makes barks fail the command. Sniffs never change the exit code.

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

## Jev for contextual judgment

[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) supplies judgment where grammar alone is insufficient. It answers typed questions and generates no prose. Slophound asks it whether a flagged noun cluster is an established term in the sentence's field, so familiar terminology can pass without adding every term to a regex exception, and whether a semicolon between two clauses belongs there or stands in for the word that would have said how the clauses relate.

Once a key is configured, normal linting runs Jev automatically. The `noun.cluster-three` rule removes a sniff when Jev assigns at least 0.70 probability to the complete expression being conventional in its field. This includes established terms with ordinary literal modifiers. Lower probabilities keep the finding for review. The prompt distinguishes familiar usage from a phrase whose meaning a reader could merely guess.

The `punct.semicolon-splice` bark fires on every semicolon that joins two clauses without a connective, since a model that may not use em dashes reaches for the semicolon next. Jev reads the sentence and clears the bark when the halves are parallel statements a careful writer would hold side by side. When the second half explains, causes, or contrasts with the first, the bark stays and the message asks for the connective. When the second half only adds a fact, the message asks for a rewrite instead of an 'and'.

Store your [TypeSafe API key](https://docs.typesafe.ai/) once, from a terminal:

```sh
uvx --python 3.13 --from 'git+ssh://git@github.com/JosXa/slophound.git' slophound auth set-key
```

The prompt hides your input. Piped stdin also works, so a secret manager can supply the key. Keep the value out of command arguments and chat messages. In a checkout, use `./slophound auth set-key`.

All harnesses use the same credential lookup:

1. Check `TYPESAFE_API_KEY` in the environment first. An empty value counts as unset.
2. Otherwise, read `api_key` from the `[jev]` table in the user config file.

On macOS and Linux, the file is `$XDG_CONFIG_HOME/slophound/config.toml`, defaulting to `~/.config/slophound/config.toml`. On Windows, it is `%APPDATA%\slophound\config.toml`. The command stores the key as plaintext and creates the file with owner-only permissions on POSIX. It preserves other settings when replacing a key. Remove `jev.api_key` and unset `TYPESAFE_API_KEY` to disable access.

With no key, Slophound runs the deterministic core with no Jev requests, results, warnings, or errors. This also applies when the stored key is blank. Credentials come from the environment and user config. A repository `.env` must be loaded by the caller.

For each eligible finding, Slophound sends the matched text, the selected words, and the sentence or sentences containing them to TypeSafe. Requests contain at most six findings from the same paragraph or list item. Masked code and URLs stay masked, and context longer than 2,000 characters keeps its finding without a request. If credentials or a request fail, the document keeps its deterministic findings. Jev only removes findings, at whatever severity the rule carries. A bark it clears no longer fails `--strict`.

### Python interface

Python callers can reuse a connection across batches:

```python
from hound.jev import JevClient
from typesafe_sdk import Noul

with JevClient() as jev:
    result = jev.evaluate(
        state="Check the database connection pool.",
        questions={
            "known_term": Noul(
                instructions="Is 'database connection pool' an established term in this sentence's field?",
                criteria={
                    "true": "The complete expression names a recognized concept in conventional usage.",
                    "false": "The expression is improvised or merely understandable from its parts.",
                },
            )
        },
    )
    if result is not None:
        print(result.nouls["known_term"].noul)
```

Each call sends the supplied state and questions to TypeSafe. The response includes the model, token usage, and typed answers. `noul` is a probability from 0 to 1. The [question types](https://docs.typesafe.ai/sdk/python/api/types/questions) also include `Choice` for labels and `Score` for ordered criteria. The default model is pinned to `jev-1.13.0`; select another with `JevClient(model="...")`.

The client returns `None` when no key or questions are supplied. It retries transient failures up to twice, with a ten-second budget for retries. Each network operation can wait up to five seconds. Direct Python calls raise `JevError` from `hound.jev` for request failures and `ConfigError` from `hound.config` for credential failures; the linter catches these and keeps the deterministic report.

## Agent skill

The [slophound skill](skills/slophound/SKILL.md) runs the standalone linter through `uvx`, then guides an editorial review based on the humanize skill.

```sh
npx skills add git@github.com:JosXa/slophound.git --skill slophound
```

The agent fixes bites first and may address useful barks and sniffs. It then loads a separate reference for reviewing meaning, terminology, audience assumptions, and support for claims. Phrase lists remain in the linter. The agent chooses tone for the intended audience and reruns the linter after editing.

The final report counts resolved findings and lists remaining barks and sniffs for review. If a finding is wrong, the agent recommends contributing a correction and asks before starting repository work. The skill works with whichever agent or subagent your harness assigns to it.

## How it works

The deterministic core runs three detection layers, ordered from cheapest to most expensive:

1. **Regex** for fixed phrases, sentence templates, and punctuation (`rules/phrase.toml`, `rules/template.toml`, `rules/punct.toml`). These bite.
2. **Dependency parsing** with spaCy for constructions that regex cannot tell apart from legitimate use: "the worker holds a mutex" passes, "that holds even under load" fires (`rules/verb.toml`, `rules/adj.toml`, `rules/noun.toml`). These bark, except for noun clusters: four or more nouns bite, three only sniff.
3. **Document statistics** for rhythm and repetition: uniform sentence length, repeated paragraph openers, triad density, bullet lists with bold labels (`rules/doc.toml`). These sniff.

Jev reviews eligible findings after these layers and deduplication. Its instructions, yes/no criteria, and probability threshold live with the rule in a `jev_veto` table. See [Adding rules](docs/adding-rules.md#jev-review) for the contract.

Every rule has its own message, at least one `example` sentence it must fire on, and at least one `acceptable` sentence it must leave alone. `./slophound test` checks all of them against the deterministic core, plus a small corpus of human and generated text under `tests/corpus/`, plus this repository's own Markdown. These checks make no Jev calls, even when a key is configured. `uv run python -m unittest discover tests` also checks Jev integration with mock responses.

## False positives

There is no ignore file and no inline suppression comment. Keep legitimate wording when a finding is wrong. We encourage corrections: reproduce the finding in a repository checkout, add a regression example, and test the fix. Agents should ask their operators whether to prepare and contribute the correction. Leave installed packages and caches unchanged.

## Contributing

Changes and ideas are welcome. See [Contributing](CONTRIBUTING.md) for the review process and [Corpora](CORPORA.md) for datasets to investigate rules and measure false positives.

Enable the pre-commit hook once per clone so your own Markdown gets linted:

```sh
git config core.hooksPath .githooks
```

See the Vision section in [AGENTS.md](./AGENTS.md) for what this project is and is not.

## License

MIT
