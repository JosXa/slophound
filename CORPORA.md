# Corpora for rule development

Sources for finding prose patterns, reproducing findings, and measuring false positives. Prioritize complete technical documents: READMEs, design proposals, specifications, and explanatory pages under `docs/`. Blog posts provide a useful secondary register. Follow [Adding rules](docs/adding-rules.md) when turning an observation into a rule.

AI detection datasets are useful because they supply generated text alongside human writing, often with generator and domain labels. Their authorship labels do not establish whether a sentence needs editing. Slophound needs evidence that a construction is tiresome in context and that a proposed rule preserves legitimate uses.

## Choosing a source

- Start with RAID, M4, or MAGE for comparisons across generators and domains. HC3 offers human and generated answers to the same questions.
- Ghostbuster includes older Claude output and substantial prose. SWE-smith supplies attributed Claude 3.7 agent traces. Inspect its patches for documentation before treating it as a prose corpus.
- For technical Markdown, combine attributed assistant output with historical engineering documentation. An essay benchmark alone cannot establish a safe threshold for design docs.
- Use original generations to discover ordinary writing habits. Keep paraphrased, attacked, or partly generated documents in separate evaluation groups.

## AI detection datasets

### RAID

[Dataset and schema](https://huggingface.co/datasets/liamdugan/raid), [files](https://huggingface.co/datasets/liamdugan/raid/tree/main), and [paper](https://aclanthology.org/2024.acl-long.674/).

- Human source texts and model generations span explanatory writing, news, reviews, and other domains. Generator families include OpenAI, Llama, Mistral, MPT, and Cohere. The published model list does not include Claude.
- CSV fields include `generation`, `prompt`, `model`, `domain`, `source_id`, `adv_source_id`, `attack`, and decoding settings. Use the labeled splits for attribution. The benchmark test split withholds labels.
- Useful for measuring whether a phrase or grammatical construction persists across models, and whether it also occurs in human text from the same domain. Group related generations by source when dividing discovery and evaluation samples. Attack variants are dependent copies, not independent examples.
- The Hugging Face card declares MIT. Preserve source identifiers and check the underlying text terms before copying examples into the test corpus. The `code` domain does not establish coverage of prose documentation.

### M4 and its benchmark extensions

[Original dataset](https://github.com/mbzuai-nlp/M4), [data schema](https://github.com/mbzuai-nlp/M4/tree/main/data), and [paper](https://aclanthology.org/2024.eacl-long.83/). Related releases include [M4GT-Bench](https://github.com/mbzuai-nlp/M4GT-Bench) and [SemEval-2024 Task 8](https://github.com/mbzuai-nlp/SemEval2024-task8).

- Covers Wikipedia, Reddit, academic material, instructional writing, and multiple languages. Original generators include ChatGPT, Davinci, Cohere, Dolly, BLOOMZ, Flan-T5, and Llama. Treat each extension as a distinct release with its own model inventory.
- Original JSONL records expose `prompt`, `human_text`, `machine_text`, `model`, `source`, and `source_ID`. This supports comparisons that retain the source and generation context.
- Useful for checking whether a candidate is specific to generated prose or merely common in an academic or instructional register. Keep language, domain, and generator separate in results.
- Follow the release's access and source terms. Availability can differ between the original collection and extensions. The [SemEval mirror](https://huggingface.co/datasets/d0rj/SemEval2024-task8) identifies itself as unofficial. Its packaging and license declaration do not replace upstream documentation.

### MAGE

[Dataset](https://huggingface.co/datasets/yaful/MAGE), [collection and schema](https://github.com/yafuly/MAGE#-dataset), and [paper](https://aclanthology.org/2024.acl-long.3/).

- Human and generated news, stories, scientific writing, opinion pieces, and longer answers. Includes several generator families and separate GPT-4 evaluation material.
- CSV releases contain text, a binary label, and source information encoding domain, generation method, and model. Here `0` means machine and `1` means human. Confirm the columns in the chosen release before importing.
- Useful for testing a rule on domains and generators excluded during development. Keep paraphrased text separate from original generations. Continuations can retain a human prompt prefix.
- The Hugging Face card declares Apache-2.0, while the project README displays CC BY 4.0. Resolve the applicable terms for the selected distribution before redistributing excerpts.

### HC3: Human ChatGPT Comparison Corpus

[Dataset and source terms](https://huggingface.co/datasets/Hello-SimpleAI/HC3), [JSONL files](https://huggingface.co/datasets/Hello-SimpleAI/HC3/tree/main), and [paper](https://arxiv.org/abs/2301.07597).

- Human and early ChatGPT answers to common questions. The English files include Reddit ELI5 and `wiki_csai`, alongside other subject areas. A separate Chinese collection supports language-specific investigation.
- Useful for comparing explanation style while holding the question constant. Keep each answer separate because a list of human answers is not one document.
- Answer lengths vary, and question answering differs from a repository design document. This is an early ChatGPT baseline with no Claude attribution.
- The card declares CC BY-SA 4.0 and explicitly retains stricter terms from source datasets.

### Ghostbuster

[Project](https://github.com/vivek3141/ghostbuster), [text release](https://github.com/vivek3141/ghostbuster-data), and [paper with collection details](https://arxiv.org/html/2305.15047v3#S3).

- Human essays, Reuters articles, and creative writing, with GPT-3.5 Turbo generations and a separate Claude evaluation collection. The paper describes documents of several hundred words and attempts to match generation length to human sources.
- Useful for sentence rhythm, paragraph repetition, and comparing older Claude prose with human examples. The cited collection description names Claude without establishing a modern Claude model version.
- Use the document text. Files named for Ada and Davinci under `logprobs` hold scoring output. Those names do not identify the generator of the document.
- Prompts for some domains were reconstructed from human documents. This is not technical Markdown, and reconstructed prompts are a confound. Check the data release and original source terms because the paper's license alone does not license its source texts.

### MULTITuDE and MULTITuDEv2

[Original record](https://zenodo.org/records/10013755), [v2 record and schema](https://zenodo.org/records/13846588), and [collection scripts](https://github.com/kinit-sk/mgt-detection-benchmark).

- Human news articles and generations from their headlines, across multiple languages. The listed generators include GPT-3.5 Turbo, GPT-4, Davinci, and several open models. The listed releases do not include Claude.
- CSV fields include `text`, `label`, `multi_label`, `language`, `length`, `source`, and `split`. The v2 files add `generated` for obfuscated text. A transformed human sample can retain its original label, so that label cannot establish human authorship of the transformed text.
- Useful for checking language effects and measuring how editing changes rule findings. Select original English text for English cadence research.
- The Zenodo record declares CC BY 4.0 but also presents restricted file access with research and redistribution conditions. Read the access terms of the selected version before requesting or reusing it.

### AI Text Detection Pile

[Dataset and component inventory](https://huggingface.co/datasets/artem9k/ai-text-detection-pile).

- Aggregates longer human and generated text from sources including WritingPrompts, WebText, HC3, and instruction datasets. Generator families include GPT-2, GPT-3, GPT-J, and ChatGPT.
- Useful for broad example searches. The documented schema exposes text and a human/AI source label. It does not promise a generator identifier for every row. Use the original component dataset when attribution matters.
- Deduplicate against HC3 and other components before combining corpora. Scraped responses and incomplete component documentation weaken attribution. The card declares MIT, with source terms requiring separate review for redistribution.

## Conversation and instruction collections

These sources can supply generated documentation, but require filtering and inspection. User messages are prompts, and human preference votes are judgments. Neither is a matched human document.

### LMSYS-Chat-1M

[Dataset and access agreement](https://huggingface.co/datasets/lmsys/lmsys-chat-1m) and [collection paper](https://arxiv.org/abs/2309.11998).

- Model-labeled conversations from 2023, with `model`, `conversation_id`, `conversation`, and `language`. Messages retain role and content in Parquet files.
- Useful for finding long assistant responses to requests for documentation or technical explanations. Inspect the actual `model` values for Claude coverage. This collection predates Claude 3.
- Requires accepting the dataset agreement. Retain the prompt and conversation context, and separate quoted source material from newly generated text.

### Chatbot Arena Conversations

[Dataset](https://huggingface.co/datasets/lmsys/chatbot_arena_conversations) and [release description](https://lmsys.org/blog/2023-07-20-dataset/).

- Paired conversations with model names, prompts, and human preferences. The release explicitly includes Claude-v1 and GPT-4.
- Useful for comparing responses to the same initial prompt across models. Later turns can diverge, and a preference vote does not identify which stylistic construction a reader preferred.
- Parquet fields include `model_a`, `model_b`, `conversation_a`, and `conversation_b`. Access requires agreement to the dataset terms. The card's generic `cc` tag does not specify a complete Creative Commons license.

### WildChat

[WildChat-1M](https://huggingface.co/datasets/allenai/WildChat-1M), [collection paper](https://arxiv.org/abs/2405.01470), and [conversation search](https://wildvisualizer.com/).

- Real user conversations with GPT-3.5 and GPT-4, with model and message-role labels. WildChat-1M supplies a filtered collection. The full version has separate access requirements.
- Useful for finding complete technical explanations and requested Markdown artifacts. Filter assistant turns by language, prompt intent, and prose length. A long conversation can consist entirely of short replies or code.
- ODC-BY. Preserve the selected release and filters in an evaluation manifest. This collection provides no Claude baseline.

### UltraFeedback

[Original dataset and schema](https://huggingface.co/datasets/openbmb/UltraFeedback).

- Multiple model completions per instruction, with `model`, `response`, `principle`, and `custom_system_prompt` in each completion. The documented pool includes GPT, Bard, and several open model families, without Claude.
- Useful for investigating how instructions change wording across models. The supplied system prompts deliberately vary behavior, so compare them alongside the model labels.
- Ratings and written critiques come from GPT-4. They are not human style judgments. Check the selected release's license and the terms of its component prompt datasets.

## Coding-agent trajectories

These collections record work in software repositories. They can contain generated Markdown in tool calls or patches, but a trajectory is not itself a finished document. Confirm file types and prose lengths before claiming documentation coverage. Separate model messages from tool results that reproduce existing repository text.

### SWE-smith trajectories

[Dataset, schema, and access](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories).

- The publisher identifies Claude 3.7 Sonnet, including `claude-3-7-sonnet-20250219`. Records include `messages`, `model`, `instance_id`, and `patch`.
- A strong candidate for extracting attributed documentation edits. Inspect patches for Markdown paths and distinguish new text from unchanged human context. Reconstruct complete files from the base revision when studying document rhythm.
- The card declares MIT. Compare the `tool`, `xml`, and `ticks` representations before combining them, since alternate formats must not count as independent samples. Long Markdown coverage requires inspection.

### SWE-Gym OpenHands sampled trajectories

[Dataset](https://huggingface.co/datasets/SWE-Gym/OpenHands-Sampled-Trajectories) and [collection project](https://github.com/SWE-Gym/SWE-Gym).

- The authors describe sampling GPT-4o and Claude 3.5 Sonnet. The `train.raw` split retains `messages`, tool calls, `run_id`, and `test_result.git_patch`.
- Useful as another candidate for extracting documentation changes. Establish the generator for each selected run because a collection containing Claude does not make every row Claude output. The cited description does not establish an exact Claude snapshot.
- The dataset card does not declare a license. The code repository's Apache-2.0 license does not automatically license the trajectory collection. Markdown coverage requires inspection.

### CC-Bench trajectories

[Dataset and schema](https://huggingface.co/datasets/zai-org/CC-Bench-trajectories).

- Agent interactions across coding tasks, with `model_name`, `task_category`, and serialized `trajectory`. The card includes `Claude-Sonnet-4` among evaluated models and declares MIT.
- Useful for comparing agent explanations and plans across models. Human evaluators supplied follow-up prompts. Parse the trajectory roles before extracting prose.
- The model-family label does not establish an exact API snapshot. Complete Markdown artifacts and long documentation coverage require inspection.

### Nebius SWE-agent trajectories

[Dataset and source terms](https://huggingface.co/datasets/nebius/SWE-agent-trajectories).

The publisher identifies Qwen2.5 and Llama3 generation, with `model_name`, `trajectory`, and `generated_patch` fields. This supplies other model families for comparison with Claude agent traces. The card declares CC BY 4.0 and notes underlying repository licenses. As with SWE-smith, inspect patches before treating the collection as documentation prose.

### Derivative trajectory collections

[ThoughtWorks agentic coding trajectories](https://huggingface.co/datasets/thoughtworks/agentic-coding-trajectories) exposes `source_dataset`, `recorded_model`, and `messages_json`. Its Claude 3.7 material derives from SWE-smith, so it supplies another representation rather than independent evidence. Its `derivative-multi-source` terms require following the upstream licenses.

The [SWE-bench Pro trajectory export](https://huggingface.co/datasets/tarsur385/swebench-pro-top5-trajectories) reports Claude 4 and 4.5 Sonnet among its model labels. This is a third-party export with no declared card license, and its publisher says tool commands were not retained. It can support message searches, but cannot establish the complete Markdown files written by the agent.

## Human and reference technical documentation

### Generate README Eval

[Dataset and schema](https://huggingface.co/datasets/patched-codes/generate-readme-eval).

Repository records include `repo_content`, `repo_readme`, repository identity, and commit. This is useful for comparing a README with the code it explains and for preparing controlled generation tasks. The release contains reference READMEs rather than Claude completions. Published evaluation scores are not generated text. Verify each reference's authorship and date before labeling it human. The card declares Apache-2.0. Retain the source repository's terms when extracting its files.

### Rust RFCs

[Repository](https://github.com/rust-lang/rfcs), [Markdown proposals](https://github.com/rust-lang/rfcs/tree/master/text), and [license guidance](https://github.com/rust-lang/rfcs#license).

Substantial engineering proposals with motivations, alternatives, drawbacks, and technical examples. These are a close match for the prose in design docs. Use a historical snapshot predating widespread LLM assistance, record its commit, and retain the source path. A current file or a human Git author is insufficient evidence of unaided authorship. The repository documents its MIT/Apache-2.0 licensing transition. Inspect the selected material's terms.

### RFC Editor archive

[RFC index](https://www.rfc-editor.org/rfc-index.html) and [plain-text RFCs](https://www.rfc-editor.org/rfc/).

Protocol specifications and technical explanations provide examples of legitimate repetition, definitions, and parallel clauses. Select historical RFCs by subject and publication date, and retain their identifiers. Remove page furniture and boilerplate before measuring rhythm. These are mostly plain text rather than Markdown. Each RFC carries its applicable copyright notice.

## Using a corpus for a rule

1. Record the dataset revision, source URL, document identifier, model label, and extraction method in the evaluation's manifest. Keep experiment results beside that evaluation rather than in this index.
2. Select complete documents with enough prose for the metric. Count prose after code, tables, and quoted material are excluded. Keep the original Markdown for reproducing locations and masking failures.
3. Match human and generated samples by subject, document purpose, and length. Report rates by domain and model, with denominators in prose words or sentences as appropriate.
4. Deduplicate copied documents and group related prompts or source texts before creating a held-out evaluation set. Keep adversarial variants with their originals to avoid leakage.
5. Read the matches. Save both the generated construction and legitimate human uses with their sources. A higher frequency in generated text is a reason to investigate, not sufficient grounds for a bite.
6. Measure false positives on technical documentation before choosing a severity or threshold. Follow the repository's rule examples and human corpus checks before shipping a change.

Add sources here when their text, authorship evidence, and intended use can be described from primary documentation. Record uncertainty explicitly, and link to the release inventory for changing file lists or model coverage.
