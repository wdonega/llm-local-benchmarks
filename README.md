# llm-local-benchmarks

This project runs **benchmarks of open-weight LLMs on my own local hardware**. I want
to know which model is worth serving on the machines I actually have. A model card or
a leaderboard run on an H100 does not answer that.

Every number here comes from my own boxes, running `llama.cpp`. Each model is tested at
the quantization that really fits. The workloads are the ones I care about: long
documents, code that has to pass hidden tests, multi-turn tool calling, reasoning and
English → Portuguese translation. Each test runs three times. Speed is recorded, but
**correctness comes first**: a fast model that gets the answer wrong is not useful.

The harness has nothing tied to one machine. Each piece of infrastructure gets its own
folder with its model list and results. So far there is one:

| Infrastructure | Folder | Setup guide |
|---|---|---|
| 2× AMD BC-250 (Vulkan, RPC layer split) | [`bc250/`](bc250/) | [wdonega/bc250-llm-setup](https://github.com/wdonega/bc250-llm-setup) |

---

## Contents

- [Best models on the BC-250](#best-models-on-the-bc-250)
- [Use cases: the LiteLLM routes (thinking off)](#use-cases-the-litellm-routes-thinking-off)
- [Round 1: screening 12 models](#round-1-screening-12-models)
- [BC-250 cluster](#bc-250-cluster)
- [The test process](#the-test-process)
- [How to reproduce](#how-to-reproduce)
- [Repository layout](#repository-layout)
- [Result files](#result-files)

---

## Best models on the BC-250

**Short answer: run a small-active MoE model.** Every config worth using is a
mixture-of-experts model with ~2.5–3B active parameters. These generate at 28–60 tok/s
on this board. Dense models from 9B up were too slow to finish hard tasks in time.

- **Everyday routes, thinking off (chat, voice, subtitles, prompts, Open WebUI tasks):**
  **Qwen3.6 35B-A3B UD-IQ2_XXS on one board**, 48/51 in the
  [use-case suite](#use-cases-the-litellm-routes-thinking-off), sub-second voice answers.
- **Hard tasks, thinking on, one board:** Ornith-1.5 35B-A3B IQ2_S (27/36 in round 1, 39 tok/s).
- **Hard tasks, thinking on, two boards:** flint 39.8B-A2.5B UD-Q3_K_XL (31/36 in round 1,
  the best score overall).

The finalists came out of round 1: configs with **more than 20 of 36 correct, at most 1
timeout and more than 20 tok/s**. That left 4 models, each tested with its one-board
and its two-board quant:

| Model | 1 board | Round 1 | Use cases | 2 boards | Round 1 | Use cases |
|---|---|---|---|---|---|---|
| Qwen3.6 35B-A3B | UD-IQ2_XXS | 25/36 | **48/51** | UD-Q4_K_M | 27/36 | 47/51 |
| flint 39.8B-A2.5B | UD-IQ2_XXS | 26/36 | 43/51 | UD-Q3_K_XL | **31/36** | 39/51 |
| Ornith-1.5 35B-A3B | IQ2_S | **27/36** | 35/51 | Q4_K_M | 28/36 | 42/51 |
| LFM2.5 24B-A2B | UD-Q3_K_XL | 21/36 | 21/51 | UD-Q5_K_XL | 24/36 | 27/51 |

Round 1 measures hard tasks with thinking on. The use-case suite measures the everyday
routes with thinking off. They rank the models differently, which is why both exist.

---

## Use cases: the LiteLLM routes (thinking off)

The BC-250 serves a set of [LiteLLM](https://github.com/BerriAI/litellm) routes, each one
a use case with its own temperature, output limit and timeout. This suite tests the
routes that run with thinking **off** (the thinking routes are served by another
machine): 17 tests × 3 runs = 51 calls per config.

| Route | temp | max_tokens | timeout | What is tested |
|---|---|---|---|---|
| `voice-chat` | 0.7 | 150 | **15 s** | 4 spoken questions (percentage, unit conversion, a fact, a tip). The answer must be right, at most 40 words, with no markdown or emoji, and must arrive in time. |
| `subtitles` | 0.2 | 2048 | 600 s | 2 SRT files, EN → PT-BR. Cue numbers, timestamps and `<i>` tags must not change; at most 2 lines per cue and 42 characters per line. Traps: *Break a leg*, *I'm on it*, *actually*, `12,500`, *6 p.m.* |
| `prompt-enhancer` | 0.7 | 800 | 600 s | 3 short requests turned into one detailed English image prompt (40–150 words) that keeps every requested element (watercolor, white background, "no people"), with no commentary. |
| `owui-tasks` | 0.3 | 512 | 600 s | Title, tags, follow-ups and search queries, using prompts modelled on Open WebUI's task templates. Valid JSON, the right schema and limits. A fenced JSON is accepted, because Open WebUI parses it. |
| `simple-chat` | 0.7 | 2048 | 300 s | Counting days, a formal e-mail with constraints, TCP vs UDP in at most 5 lines, a one-sentence summary. |

Server: 64k context and thinking off. Qwen3.6 and Ornith switch thinking off through
`enable_thinking: false`. flint and LFM2.5 have no switch, so the server forces it with
`--reasoning-budget 0`. top_p, top_k, min_p and penalties are each model card's
non-thinking recommendation. Temperature comes from the route:

| Model | top_p | top_k | min_p | other |
|---|---|---|---|---|
| Qwen3.6 35B-A3B | 0.8 | 20 | 0 | presence_penalty 1.5 |
| Ornith-1.5 35B-A3B | 0.95 | 20 | 0 | – |
| flint | 0.95 | 20 | 0 | – |
| LFM2.5 24B-A2B | 1.0 | 50 | 0 | repetition_penalty 1.05 |

| Config | voice-chat | subtitles | prompt-enhancer | owui-tasks | simple-chat | Total | Timeouts | Voice p95 latency | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 12/12 | 3/6 | 9/9 | 12/12 | 12/12 | **48/51** | 0 | 1.1s | 39.6 | complete |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 12/12 | 4/6 | 8/9 | 12/12 | 11/12 | **47/51** | 0 | 1.6s | 35.6 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 12/12 | 2/6 | 9/9 | 12/12 | 8/12 | **43/51** | 0 | 0.8s | 43.6 | complete |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 12/12 | 3/6 | 8/9 | 12/12 | 7/12 | **42/51** | 0 | 1.3s | 41.7 | complete |
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 12/12 | 1/6 | 7/9 | 9/12 | 10/12 | **39/51** | 0 | 1.1s | 36.7 | complete |
| Ornith-1.5-35B-A3B IQ2_S (single) | 10/12 | 0/6 | 8/9 | 11/12 | 6/12 | **35/51** | 0 | 0.6s | 48.6 | complete |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 10/12 | 0/6 | 5/9 | 3/12 | 9/12 | **27/51** | 0 | 1.1s | 50.0 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 9/12 | 0/6 | 3/9 | 0/12 | 9/12 | **21/51** | 0 | 0.9s | 60.6 | complete |

Median wall time per call, in seconds:

| Config | voice-chat | subtitles | prompt-enhancer | owui-tasks | simple-chat |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 0.6 | 5.5 | 3.6 | 2.1 | 2.6 |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 1.1 | 6.2 | 4.3 | 2.0 | 3.5 |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 0.6 | 3.5 | 2.1 | 1.7 | 3.0 |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 1.1 | 5.8 | 3.5 | 2.1 | 3.3 |
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 0.8 | 4.7 | 2.8 | 1.9 | 3.5 |
| Ornith-1.5-35B-A3B IQ2_S (single) | 0.4 | 4.4 | 1.9 | 2.0 | 2.2 |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 0.6 | 3.5 | 3.9 | 11.2 | 2.2 |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 0.4 | 2.6 | 4.3 | 9.3 | 2.3 |

Per-test breakdown: [`bc250/results/usecases/summary.md`](bc250/results/usecases/summary.md).

**What the use cases show**

- **Qwen3.6 is the model for everyday routes.** 48/51 on one board, perfect on voice,
  prompts, Open WebUI tasks and chat. The bigger two-board quant does not improve it (47/51).
- **Voice is fast for everyone.** p95 latency was 0.6–1.6 s, far inside the 15 s timeout.
  The differences are in correctness: LFM2.5 named "Camden" as the capital of Australia.
- **Subtitles are the hardest route.** Only Qwen3.6 (both quants) got the dialogue right.
  The others translated *Break a leg* as "Quebras uma perna" and *I'm on it* as "Estou em
  cima disso". The news file failed mostly on the 42-character line limit.
- **A model that always thinks cannot be switched off.** LFM2.5 is a pure reasoning
  model. With thinking forced off, it moved its reasoning into the answer ("We need to
  produce a concise title…") and ran out of the 512-token limit before writing the JSON:
  0/12 on Open WebUI tasks on one board. flint, which also has no switch, coped well.
- **Thinking on and thinking off rank models differently.** flint on two boards is the
  best model with thinking (31/36) but only 5th here (39/51), with no emoji in titles and
  overlong subtitles. Ornith's two-board quant gained 7 points over its 2-bit one-board
  quant here, much more than with thinking on.

### Round 2 (stopped)

A second round re-ran the finalists' hard tasks with production-like thinking settings:
64k context, 16k thinking budget, 15 min per call and each model card's sampling, plus
two EN → PT-BR translation tests. It was stopped after the first config, because the
thinking routes are served by another machine. The profile stays in the harness
(`--profile round2`), and the translation tests are described in
[The tasks](#the-tasks).

---

## Round 1: screening 12 models

Round 1 had one job: **sort out what works on this hardware** before spending time on
it. It ran 12 models (MoE and dense, 4B to 40B) under the same tight limits: 32k
context, 6144-token thinking budget and 5 minutes per call. Most of them did not make
the cut, mainly because dense models are too slow here. Their results stay below
because they explain *why* the finalists are what they are.

### What was tested in round 1

For every model, the best quant that fits one board was tested in **single** mode. Where
it makes sense, a bigger quant spread over both boards was tested in **dual** mode. The
quant rule was conservative. On one board it is the largest file that leaves room for a
32k context and the OS (about 11–12 GiB at most). Dense models are capped at Q6_K. The
reason is speed: the BC-250 makes ~7–8 tok/s on a 27B dense model, and a 9–12B model at
Q8_0 would spend the whole 5-minute timeout thinking.

| Model | HF repo | single | dual |
|---|---|---|---|
| flint 39.8B-A2.5B (MoE) | `unsloth/flint-GGUF` | UD-IQ2_XXS | UD-Q3_K_XL |
| LFM2.5 24B-A2B (MoE) | `unsloth/LFM2.5-24B-A2B-GGUF` | UD-Q3_K_XL | UD-Q5_K_XL |
| Ornith 1.5 35B-A3B (MoE) | `bartowski/…` (single), `ornith-ai/…` (dual) | IQ2_S | Q4_K_M |
| Qwen3.6 35B-A3B (MoE) | `unsloth/Qwen3.6-35B-A3B-GGUF` | UD-IQ2_XXS | UD-Q4_K_M |
| Qwen3-Coder 30B-A3B (MoE) | `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF` | UD-IQ2_M | Q4_K_M |
| Qwen3.8 27B (dense) | `unsloth/Qwen3.8-27B-GGUF` | UD-Q2_K_XL | UD-Q4_K_M |
| Qwen3.5 4B (dense) | `unsloth/Qwen3.5-4B-GGUF` | Q8_0 | – |
| Qwen3.5 9B (dense) | `unsloth/Qwen3.5-9B-GGUF` | Q6_K | – |
| Ornith 1.5 9B (dense) | `ornith-ai/Ornith-1.5-9B-GGUF` | Q6_K | – |
| Gemma 4 12B it (dense) | `unsloth/gemma-4-12b-it-GGUF` | Q6_K | – |
| Nemotron 3.5 Bolt E4B | `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF` | UD-Q6_K_XL | – |
| Qwen3.8 27B TURBO Fusion NEO-CODER (DavidAU) | `DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-…-GGUF` | IQ2_M | Q4_K_M |

The exact repos, quant tags and file sizes are in [`bc250/models.json`](bc250/models.json).

A few choices need explaining:

- **Nemotron from unsloth, not from NVIDIA.** NVIDIA ships one Q4_K_M, and its recipe
  targets CUDA with a BF16 speculative drafter. BF16 runs poorly on this GPU. The
  unsloth K-quant is a fast path on RADV and is higher quality than Q4.
- **DavidAU Fusion without MTP.** The non-MTP files were used for both quants.
- **dual-same.** As a last experiment, the config with the best single-board score is
  re-run on **both boards with the same quant**. This measures what RPC costs when you
  don't need the memory.
- **Timeout retries.** A config with 4 or more timeouts (over 10 % of its calls) is
  re-run at the end, one quant lower: the largest file in the same repo at most 90 % of
  the current size (e.g. Q8_0 → Q6_K, Q6_K → Q5_K_M). This shows whether a faster, smaller
  quant scores better within the time limit. Both rows stay in the table, and the retry is
  labelled `retry of <quant>`.

### Round 1 results

Completed on 2026-10-26: 25 configs, 36 graded calls each. Per-test breakdown:
[`bc250/results/main/summary.md`](bc250/results/main/summary.md). Two timeout retries
were cancelled because the trend was already clear: Qwen3.8-27B single UD-IQ2_S, which
was at 5/13 with 8 timeouts, and Fusion dual IQ3_M.

How to read the speed columns:

- **Ctx** is the context window allocated with `--ctx-size` (32k, or 24k if 32k did not
  fit). **KV cache** is the type passed to `--cache-type-k` and `--cache-type-v`. Both
  change speed and memory a lot, so compare rows only when these columns match.
- The **actual** prompt size depends on the test. The long-context tests send ~17k
  tokens. Everything else sends under 1k, plus the earlier turns in tool calls.
- **Prompt t/s** is the mean over calls with more than 200 prompt tokens, so the
  long-context calls dominate it. **Gen t/s** is the mean over every call. It is lower
  on long-context calls, where the KV cache is full.

<!-- RESULTS:BEGIN -->
_25 configs, final._

| Config | Ctx | KV cache | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 32k | q8_0 | 5/6 | 8/9 | 12/12 | 6/9 | **31/36** | 0 | 115 | 28.5 | complete |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 5/9 | 12/12 | 5/9 | **28/36** | 0 | 190 | 37.9 | complete |
| Ornith-1.5-35B-A3B IQ2_S (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 3/9 | **27/36** | 0 | 149 | 38.9 | complete |
| Qwen3.5-4B Q6_K (single, retry of Q8_0) | 32k | q8_0 | 5/6 | 5/9 | 12/12 | 5/9 | **27/36** | 5 | 207 | 34.2 | complete |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 32k | q8_0 | 6/6 | 4/9 | 11/12 | 6/9 | **27/36** | 0 | 195 | 37.0 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 2/9 | **26/36** | 0 | 110 | 31.7 | complete |
| Ornith-1.5-35B-A3B IQ2_S (dual-same) | 32k | q8_0 | 6/6 | 3/9 | 12/12 | 4/9 | **25/36** | 0 | 157 | 35.7 | complete |
| Qwen3.5-4B Q8_0 (single) | 32k | q8_0 | 5/6 | 5/9 | 12/12 | 3/9 | **25/36** | 6 | 204 | 29.0 | complete |
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 5/9 | 11/12 | 3/9 | **25/36** | 0 | 138 | 34.3 | complete |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 32k | q8_0 | 5/6 | 3/9 | 12/12 | 4/9 | **24/36** | 0 | 245 | 44.8 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 32k | q8_0 | 4/6 | 3/9 | 12/12 | 2/9 | **21/36** | 0 | 183 | 49.0 | complete |
| Nemotron-3.5-Bolt-E4B UD-Q6_K_XL (single) | 32k | q8_0 | 5/6 | 3/9 | 11/12 | 1/9 | **20/36** | 1 | 214 | 26.1 | complete |
| Ornith-1.5-9B Q5_K_M (single, retry of Q6_K) | 32k | q8_0 | 6/6 | 0/9 | 11/12 | 3/9 | **20/36** | 15 | 125 | 19.0 | complete |
| Qwen3.8-27B UD-IQ4_XS (dual, retry of UD-Q4_K_M) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 3/9 | **20/36** | 16 | 44 | 8.8 | complete |
| Ornith-1.5-9B Q6_K (single) | 32k | q8_0 | 6/6 | 1/9 | 12/12 | 0/9 | **19/36** | 14 | 103 | 18.5 | complete |
| Qwen3.8-27B UD-Q4_K_M (dual) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 2/9 | **19/36** | 17 | 36 | 7.5 | complete |
| Qwen3.8-27B UD-Q2_K_XL (single) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 2/9 | **19/36** | 17 | 45 | 7.7 | complete |
| Gemma-4-12B-it Q6_K (single) | 32k | q8_0 | 6/6 | 0/9 | 12/12 | 0/9 | **18/36** | 18 | 75 | 12.5 | complete |
| Qwen3.5-9B Q6_K (single) | 32k | q8_0 | 4/6 | 2/9 | 12/12 | 0/9 | **18/36** | 17 | 103 | 18.7 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-Q4_K_M (dual) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 1/9 | **18/36** | 16 | 31 | 7.0 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-IQ2_M (single) | 32k | q8_0 | 4/6 | 0/9 | 12/12 | 2/9 | **18/36** | 17 | 36 | 6.7 | complete |
| Gemma-4-12B-it UD-Q5_K_XL (single, retry of Q6_K) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 0/9 | **17/36** | 19 | 82 | 12.3 | complete |
| Qwen3.5-9B Q5_K_M (single, retry of Q6_K) | 32k | q8_0 | 3/6 | 2/9 | 11/12 | 1/9 | **17/36** | 17 | 155 | 20.3 | complete |
| Qwen3-Coder-30B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 3/9 | 6/12 | 0/9 | **15/36** | 0 | 202 | 39.1 | complete |
| Qwen3-Coder-30B-A3B UD-IQ2_M (single) | 32k | q8_0 | 5/6 | 2/9 | 6/12 | 0/9 | **13/36** | 1 | 128 | 35.1 | complete |
<!-- RESULTS:END -->

### Round 1 findings

**Round 1 ranking**

| | Config | Score | Gen t/s | Timeouts | Notes |
|---|---|---|---|---|---|
| 1 | flint 39.8B-A2.5B UD-Q3_K_XL, 2 boards | **31/36** | 28.5 | 0 | best overall. Only config with 3/3 on the expression evaluator; 8/9 coding, 6/9 reasoning |
| 2 | Ornith-1.5 35B-A3B Q4_K_M, 2 boards | 28/36 | 37.9 | 0 | best balance of score and speed |
| 3 | Qwen3.6 35B-A3B UD-Q4_K_M, 2 boards | 27/36 | 37.0 | 0 | best reasoner: the only one that solved the logic puzzle more than once (2/3) |
| 4 | Ornith-1.5 35B-A3B IQ2_S, 1 board | 27/36 | 38.9 | 0 | **best single-board config** |
| 5 | Qwen3.5 4B Q6_K, 1 board | 27/36 | 34.2 | 5 | ties #4 with a 3.5 GB file and room left over on the board |

**1. Small-active MoE is the right shape for this hardware.** All the configs that
matter are MoE models with ~2.5–3B active parameters, generating at 28–49 tok/s. They
had **zero timeouts**.

**2. Dense models from 9B up are not usable here.** Qwen3.5-9B, Ornith-1.5-9B,
Gemma-4-12B, Qwen3.8-27B and the DavidAU Fusion all land at 17–20/36, with 14–19 of
the 36 calls timing out. That happens even though the thinking budget (6144 tokens) is
1/8 of what a production config would allow. The arithmetic does not work: thinking
6144 tokens and then answering in 300 s needs more than ~21 tok/s. These models run at
7–20 tok/s, and a long-context call first spends 1.5–3 minutes reading the prompt.
When they *do* finish they are often right (11–12/12 on tool calls, which are short),
but coding is 0–2/9, almost all timeouts. Throughput was steady; there was no swapping.
Speed is the problem, not memory.

**3. A lower quant does not rescue a slow model.** Five configs with many timeouts were
re-run one quant lower. Generation speed changed by −2 % to +17 % and the score moved by
±1, which is noise. The exception is Qwen3.5-4B: Q8_0 → Q6_K gave +18 % speed, one fewer timeout and
**25 → 27**.

**4. A bigger quant on two boards is worth it.** The same model with a bigger quant
split over RPC scored better in every case: flint **26 → 31**, LFM 21 → 24, Qwen3.6
25 → 27, Qwen3-Coder 13 → 15 and Ornith 27 → 28. Generation speed changed by −10 % to
+11 %. When it got faster, the single-board config used an IQ quant (IQ quants are the
slow path on RADV). All numbers here were measured with both boards running 24 of
their 40 CUs, so they are a lower bound for unlocked boards.

**5. Splitting without needing the memory costs ~8 %.** The best single-board config
(Ornith IQ2_S) re-run on two boards with the same file went from 38.9 to 35.7 tok/s
(−8 %). The score went from 27 to 25, which is within run-to-run noise at temperature
0.6. Only split when you need the memory for a bigger quant.

**6. Tool calling is nearly solved. Reasoning is not.**
- 23 of 25 configs scored 11–12/12 on multi-turn tool calls.
- All 25 refused to send a PIX without a key and an amount. That test no longer
  discriminates.
- Qwen3-Coder is the exception: 6/12 at both quants. It booked the meeting twice, on
  the wrong day, and when a SKU was replaced it told the user to look it up instead of
  calling the tool again.
- On the 5-person logic puzzle only Qwen3.6 (dual, 2/3) and Ornith (dual, 1/3) ever got
  it right. Wrong answers were often stable: flint gave the same wrong solution in
  every run.

**7. Speed ≠ quality.** LFM2.5 is the fastest model on the board (49 tok/s) and scored
21/36. Nemotron-3.5-Bolt E4B scored 20/36 at 26 tok/s. It is beaten on both axes by
Qwen3.5-4B (27/36 at 34 tok/s).

---

## BC-250 cluster

### Hardware and software

Two ex-mining **AMD BC-250** boards. How they were built and tuned (BIOS, cooling,
drivers, GTT, 40-CU unlock, governor, RPC services) is in
[bc250-llm-setup](https://github.com/wdonega/bc250-llm-setup). In short:

| | Per board |
|---|---|
| APU | AMD BC-250 "Cyan Skillfish", RADV GFX1013, **24 of 40 CUs active on both boards** (the 40-CU unlock was not applied during these runs; a kernel upgrade had reverted it) |
| Memory | 16 GB GDDR6 shared by CPU and GPU, ~14 GiB usable as GTT (`ttm.pages_limit`) |
| OS | Ubuntu 26.04.1 LTS, kernel 7.0.0-38, Mesa 26.0.8 (RADV) |
| `llama.cpp` | build **b11869** (commit `d327bf1f0`, 2026-10-24), `-DGGML_VULKAN=ON -DGGML_RPC=ON` |
| Network | 2.5 GbE between the boards |

There are two layouts:

- **single**: one board (`llm3`) runs `llama-server` with the whole model.
- **dual**: `llm3` runs `llama-server` and offloads half of the layers to `llm4`, which
  runs `ggml-rpc-server` (`--rpc llm4.lab:50052 -ts 0.5,0.5`). A bigger quant fits this way.

Both boards must run the same `llama.cpp` build, because the RPC protocol version has to
match. The flint model needed this build: support for its architecture landed in
`llama.cpp` on 2026-10-21.

### BC-250 lessons learned

- **Unified memory means the OOM killer is part of the benchmark.** The GPU allocates
  from the same 14 GiB as everything else. A ~11 GiB model plus a 32k KV cache plus a
  ~1.4 GiB desktop/IDE process was enough to get `llama-server` OOM-killed mid-run.
  systemd then tore down the whole tmux scope with it. The fix was to run the queue as a
  `systemd --user` service with `Restart=on-failure`, make every call resumable, and
  keep other processes off the head board while benchmarking.
- **The RPC worker's tensor cache can go bad silently.** `ggml-rpc-server --cache` keeps
  received tensors on the worker's disk. At one point two dual configs (Ornith and
  Qwen3-Coder, both Q4_K_M) produced pure garbage ("2525255…", stray `\u` and tabs) for
  hours. Meanwhile other models split across the same two boards were fine, and the same
  files had worked the day before. The model file on the head was intact (its sha256
  matched Hugging Face). Deleting `~/.cache/llama.cpp/rpc` on the worker and restarting
  it fixed both. The runner now asks a trivial question ("capital of France?") right
  after loading and aborts the config if "Paris" is not in the answer.
- **Turn off `llama-server`'s host prompt cache.** Recent builds keep up to 8 GiB of
  saved prompt states in system RAM by default (`--cache-ram 8192`). On a 14 GiB
  unified-memory board with a ~10 GiB model, that cache grows call after call until the
  OOM killer fires. With a dense 27B model and 17k-token prompts it happened every
  10–20 minutes. `--cache-ram 0` stopped it. With one slot, the slot's own KV still
  reuses an identical prompt prefix between consecutive runs. Configs that finished
  before this flag was added ran with the default and survived through restarts.
- **Enable linger** (`loginctl enable-linger $USER`), or user services die when you log out.
- **IQ quants work on RADV, but K-quants are the fast path.** Prefer K-quants when the
  size is similar.
- **Prompt processing is the hidden cost of long context.** At ~100–180 tok/s of prompt
  eval, a 17k-token document takes 1.5–3 minutes before the first output token. The
  long-context document was sized to fit the 5-minute timeout. An earlier 25k-token
  version did not fit on the slower models.

---

## The test process

Each model/quant/mode combination is a **config**. For each config the runner:

1. Checks free disk space before downloading. If space is short, it deletes the HF cache
   of a model whose configs are **all finished**. It never deletes a repo still in the
   queue, or any repo listed in `BENCH_KEEP_CACHE`.
2. Starts `llama-server -hf <repo>:<quant>`, which downloads the model on first use. If
   a 32k context does not load, it retries at 24k.
3. Runs an output check: the model must answer "Paris" to "Qual é a capital da França?".
   If it does not (garbage output, broken split), the config is aborted with an error.
   Then it runs every test × 3, one request at a time.
4. Saves each call to the config's JSON as soon as it finishes, so a crash or reboot
   resumes at the next call.
5. Stops the server and rebuilds `summary.md` / `summary.csv`.

Every request has a **5-minute timeout**. A timeout is recorded separately from a wrong
answer, and the server is given time to recover before the next call.

All prompts are in **Brazilian Portuguese** on purpose: that is the language these models
are used in. The graders take this into account (decimal commas, `1.576` thousands
separators, Portuguese weekday names).

### The tasks

36 calls per config in round 1 (12 tests × 3 runs), 42 in round 2 (+2 translation
tests). A 1-run pilot ([`results/pilot`](bc250/results/pilot))
was used to make sure the tests are neither impossible nor trivial.

**Long context.** One ~17k-token synthetic document: ~400 filler records with planted
facts, corrections and look-alike names (Renata Aguiar / Renato Aguiar / Renata Agostini,
Otávio Brandt / Otávia Brandão / Otávio Brito).

| Test | Expected | Trap |
|---|---|---|
| `multi_hop_ramal` | 4471 | 3 hops: vault B key → Joinville coordinator → replaced on 2026-03-03 → new person's extension. The old coordinator's extension (3318) is the distractor. |
| `soma_com_correcoes` | 1576 | Sum three lots, applying a later correction (340 → 304) and a second shipment. |

**Coding.** Invented specs, so the model cannot recall a known solution. Hidden tests run
in `python:3.12-slim` with no network, 256 MB RAM, 1 CPU and a read-only mount.

| Test | Hidden tests | What makes it hard |
|---|---|---|
| `avaliador_expressoes` | 36 | Expression evaluator without `eval`: right-associative `^`, unary minus below `^`, division truncating toward zero, exact errors for every invalid input |
| `calculo_frete` | 30 | 8 shipping rules applied in order: per-kg-*or-fraction* pricing, regional multipliers, free shipping overrides an invalid coupon, minimum fee, `ROUND_HALF_UP` (cases like 29.30 / 11.63 / 42.53 fail with float `round()`) |
| `corrigir_sessoes` | 8 | Fix a buggy function to match its docstring: `<=` limit, dedup, must not mutate the input |

**Tool calling.** Multi-turn, with tools simulated by the harness. Each tool result is fed
back until the model gives a final answer.

| Test | Pass condition |
|---|---|
| `multi_etapas_reembolso` | Look up the customer, list cancelled orders, call `calcular_reembolso` for **each** of the 3, and answer **432.36**. Summing the paid amounts (480.40) fails. |
| `args_estritos_agenda` | Exactly one booking: `2026-10-27T14:30` ("next Tuesday" from Friday 2026-10-23), `90` min, the two right e-mails from the directory, room `"Verde"` (enum, case-sensitive) |
| `recuperacao_erro_estoque` | The first SKU returns an error pointing to a replacement. The model must query the new SKU and answer 37 (warehouse), not 42 (warehouse + store). |
| `abster_sem_dados_pix` | "Send a PIX to João" with no key or amount. Passes only if `transferir_pix` is **not** called. |

A tool call written as JSON in the text, instead of a native `tool_calls` entry, counts
as a failure.

**Reasoning.**

| Test | Expected |
|---|---|
| `logica_5_pessoas` | 5 people × floor × city × drink, 15 clues, unique solution (checked by brute force): `Carla; Natal; 2` |
| `aritmetica_datas` | 1000-day contract starting Sunday 2026-10-25 (day 1): `2029-07-20; sexta; 1` (date, weekday and the number of Feb 29s, all three required) |
| `instrucoes_multiplas` | One paragraph: exactly 4 sentences, initials M-A-P-E, no letter z, "backup" exactly twice, no commas, ends with "fim." |

**Translation (round 2).** Two English texts to translate into Brazilian Portuguese
"with the naturalness of a professional translator", keeping placeholders, code, URLs,
product names and Markdown untouched. Each one hides traps that a competent translator
handles and a literal one does not. Grading is a checklist on the final answer: every
item must pass.

| Test | What is checked |
|---|---|
| `traducao_suporte_tecnico` | Support e-mail. False friends *actually* (≠ atualmente) and *eventually* (≠ eventualmente). Idioms *ballpark figure* (→ valor aproximado / estimativa) and *the ball is in your court* (no literal "quadra"). `$1,250.75` → `1.250,75`. *March 3, 2027* → *3 de março de 2027*. `{customer_name}`, `` `npm install …` ``, the URL, "CloudSync Pro" and the `**bold**` must survive exactly. |
| `traducao_falsos_cognatos` | A short personal paragraph packed with false friends: *parents* → pais (≠ parentes), *library* → biblioteca (≠ livraria), *pretends* → finge (≠ pretende), *attends* → participa/frequenta (≠ atende), *sensible* → sensata (≠ sensível), *piece of cake* → moleza/fácil (≠ pedaço de bolo). |

Both tests also fail if more than one common English word is left over, or if the output
is under 0.8× or over 1.6× the source length, which catches summaries and added
commentary. Several valid wordings are accepted for each trap. chrF (character n-gram
F-score) against a reference translation is recorded in each call's `detail` for
reference, but it does not affect the verdict.

### Grading rules

- **Only the final answer counts.** The reasoning trace (`reasoning_content`) is never
  graded. A model that works out the right answer while thinking but never writes it
  in its reply fails.
- Answers are read from the last `RESPOSTA:` line, with some tolerance for format
  (bold markers, the answer on the next line).
- Thinking is capped with `--reasoning-budget 6144`, and the budget message tells the
  model to stop and answer. Without the cap, some models think until they time out.

### Server and sampling settings

```
llama-server -hf <repo>:<quant> --no-mmproj -ngl 999 -fa on --ctx-size <ctx> --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 -b 2048 -ub 512 --jinja \
  --reasoning-budget <budget> --reasoning-budget-message " Preciso parar de pensar agora e dar a resposta final." \
  --cache-ram 0
# dual / dual-same add:  --rpc llm4.lab:50052 -ts 0.5,0.5
```

The two profiles (`--profile round1|round2`, defined in `PROFILES` in `run_bench.py`):

| | round1 | round2 |
|---|---|---|
| context | 32k (24k fallback) | 64k (no fallback) |
| thinking budget | 6144 | 16384 |
| timeout per call | 300 s | 900 s |
| sampling | 0.6 / 0.95 / 20 / 0 (temp / top_p / top_k / min_p) for every model | per model, from `sampling` in the models file |
| seed | 9000 + run | 9000 + run |
| max tokens | 8k long context, 12k coding/reasoning, 4k per tool turn | 20k long context and per tool turn, 24k coding/reasoning/translation |
| tasks | 12 tests (36 calls) | the same + 2 translation tests (42 calls) |

### Validating the suite

A wrong answer key would make every model look bad. `validate.py` checks the suite
itself, without any model:

- the reference solutions pass 100 % of the hidden tests;
- 11 coding negative controls and 16 translation negative controls fail. These are typical wrong implementations, such as `//` for
  division, float `round()`, left-associative `^`, or fixing only `<` → `<=`;
- the long-context document contains each planted fact the expected number of times, in
  the right order;
- every grader accepts valid answer formats and rejects distractors.

It must print `ALL OK`. Several answer-key mistakes were caught this way before the real
run.

---

## How to reproduce

### Requirements

- A `llama.cpp` build with the backend for your GPU and `-DGGML_RPC=ON` if you want dual
  mode. Any recent build should work. The BC-250 numbers above used b11869.
- For dual mode, a second machine running `ggml-rpc-server` from the **same** build.
- Python 3.10+ (standard library only), `curl`, and Docker with `python:3.12-slim`
  pulled. Docker is used to run model-written code in a sandbox.
- Disk space for the models. The runner downloads through `llama-server -hf` into the
  normal Hugging Face cache.

### Configure

All settings are environment variables with defaults:

| Variable | Default | Meaning |
|---|---|---|
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | server binary |
| `BENCH_RPC` | `llm4.lab:50052` | RPC worker for dual mode |
| `BENCH_PORT` | `8081` | local port for the test server |
| `BENCH_OUT` | `./bc250` | infrastructure folder: `models.json`, `results/`, logs |
| `BENCH_MODELS` | `$BENCH_OUT/models.json` | model list |
| `BENCH_KEEP_CACHE` | *(empty)* | comma-separated HF repos the disk cleanup must never delete |
| `HF_HUB_CACHE` | `~/.cache/huggingface/hub` | where models are cached |

To benchmark a different machine, create a folder (e.g. `mybox/`) with a `models.json`
and point `BENCH_OUT` at it.

`models.json` is a list of models, each with one or more configs:

```json
{
  "key": "qwen36-35b",
  "label": "Qwen3.6-35B-A3B",
  "run_last": false,
  "configs": [
    {"mode": "single", "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "quant": "UD-IQ2_XXS", "size_gib": 10.02},
    {"mode": "dual",   "repo": "unsloth/Qwen3.6-35B-A3B-GGUF", "quant": "UD-Q4_K_M",  "size_gib": 20.61}
  ]
}
```

`quant` is the tag passed to `-hf repo:quant`. `size_gib` is used for the disk-space
check. `run_last` pushes slow models to the end of the queue.

### Run

Stop anything else that uses the GPU first, so the test server gets all the memory.

```bash
cd harness

# 1. check the suite itself (no model needed, uses Docker)
python3 validate.py                          # must print ALL OK

# 2. optional: check the RPC worker before any dual config
python3 rpc_smoke.py                         # or: python3 rpc_smoke.py <repo>:<quant>

# 3. one config, one run, to try it out
python3 run_bench.py --only qwen36-35b:single --runs 1 --tag try

# 4. everything (singles -> duals -> run_last models)
python3 run_bench.py --all --runs 3

# 5. re-run the best single config on two boards with the same quant
python3 run_bench.py --best-single-dual

# 6. re-run configs with 4+ timeouts one quant lower
python3 run_bench.py --retry-timeouts

# round 2: the finalists with 64k context, 16k thinking budget, per-model sampling,
# 15 min per call and the translation tests (results in results/round2/)
python3 run_bench.py --profile round2 --models ../bc250/models-round2.json --all --runs 3

# use cases: the LiteLLM routes with thinking off (results in results/usecases/)
python3 validate_usecases.py                 # must print ALL OK
python3 run_usecases.py --models ../bc250/models-usecases.json --all --runs 3

# rebuild summaries from the JSON files at any time
python3 run_bench.py --summary
```

The full queue takes many hours (about 1 hour per MoE config, 3–5 hours per 27B
dense config on a BC-250). To run it unattended, survive logouts and restart after an
OOM kill:

```bash
loginctl enable-linger "$USER"
systemd-run --user --unit=llm-bench -p Restart=on-failure -p RestartSec=60 \
  -p StartLimitIntervalSec=4h -p StartLimitBurst=6 \
  --setenv=BENCH_KEEP_CACHE=ornith-ai/Ornith-1.5-9B-GGUF \
  "$PWD/run_queue.sh"

journalctl --user -u llm-bench -f              # or: tail -f ../bc250/bench.log
```

`--setenv` protects the model your production server uses from the disk cleanup. Use
your own repo there, or drop the flag.

---

## Repository layout

```
harness/
  run_bench.py        benchmark runner (resumable, single/dual/dual-same modes)
  tasks.py            tasks, simulated tools and graders
  validate.py         checks the answer keys, graders and negative controls of the suite
  common.py           shared helpers: server lifecycle, disk management, Docker sandbox
  usecases.py         use-case suite: one group of tests per LiteLLM route
  run_usecases.py     use-case runner (thinking off, per-route settings, latency)
  validate_usecases.py  checks the use-case graders against good and bad answers
  rpc_smoke.py        loads a small model across two boards to check the RPC worker
  run_queue.sh        full queue, meant to run unattended as a systemd user service
bc250/
  models.json         round 1: every model and quant tested on the BC-250 cluster
  models-round2.json  round 2: the finalists, with each model card's recommended sampling
  models-usecases.json  use cases: the finalists, with each card's non-thinking sampling
  results/usecases/   use-case results
  results/round2/     round 2 results (updated as each config finishes)
  results/main/       round 1 results
  results/pilot/      pilot run (1 run per test, used to calibrate difficulty)
```

---

## Result files

| File | Content |
|---|---|
| `results/<tag>/<key>__<mode>__<quant>.json` (default tag: `main`) | one config: settings, load time, and every call with the verdict, timeout flag, token counts, prompt/gen speed, the final answer and grader details (failed hidden tests, parsed answer line, tool calls made) |
| `results/<tag>/summary.md` | scoreboard and per-test matrix |
| `results/<tag>/summary.csv` | one row per call, for your own analysis |

The JSON files keep the model's final answer, so any verdict can be audited. Results
recorded before the harness was translated to English have some Portuguese keys in
`detail` (`falhas`, `motivo`, `chamadas`). The meaning is the same.

## License

AGPL-3.0, same as [bc250-llm-setup](https://github.com/wdonega/bc250-llm-setup).
