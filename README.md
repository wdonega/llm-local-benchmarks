# llm-local-benchmarks

This project runs **benchmarks of open-weight LLMs on my own local hardware**. I want
to know which model is worth serving on the machines I actually have. A model card or
a leaderboard run on an H100 does not answer that.

Every number here comes from my own boxes, running `llama.cpp`. Each model is tested at
the quantization that really fits. The workloads are the ones I care about: long
documents, code that has to pass hidden tests, multi-turn tool calling and reasoning.
Each test runs three times. Speed is recorded, but **correctness comes first**: a fast
model that gets the answer wrong is not useful.

The harness has nothing tied to one machine. Each piece of infrastructure gets its own
folder with its model list and results. So far there is one:

| Infrastructure | Folder | Setup guide |
|---|---|---|
| 2× AMD BC-250 (Vulkan, RPC layer split) | [`bc250/`](bc250/) | [wdonega/bc250-llm-setup](https://github.com/wdonega/bc250-llm-setup) |

---

## Contents

- [Repository layout](#repository-layout)
- [BC-250 cluster](#bc-250-cluster)
  - [Hardware and software](#hardware-and-software)
  - [What was tested](#what-was-tested)
  - [Results](#results)
  - [Findings so far](#findings-so-far)
  - [BC-250 lessons learned](#bc-250-lessons-learned)
- [The test process](#the-test-process)
  - [The tasks](#the-tasks)
  - [Grading rules](#grading-rules)
  - [Server and sampling settings](#server-and-sampling-settings)
  - [Validating the suite](#validating-the-suite)
- [How to reproduce](#how-to-reproduce)
- [Result files](#result-files)

---

## Repository layout

```
harness/
  run_bench.py        benchmark runner (resumable, single/dual/dual-same modes)
  tasks.py            tasks, simulated tools and graders
  validate.py         checks the answer keys, graders and negative controls of the suite
  common.py           shared helpers: server lifecycle, disk management, Docker sandbox
  rpc_smoke.py        loads a small model across two boards to check the RPC worker
  run_queue.sh        full queue, meant to run unattended as a systemd user service
bc250/
  models.json         models and quants tested on the BC-250 cluster
  results/main/       results (updated as each config finishes)
  results/pilot/      pilot run (1 run per test, used to calibrate difficulty)
```

---

## BC-250 cluster

### Hardware and software

Two ex-mining **AMD BC-250** boards. How they were built and tuned (BIOS, cooling,
drivers, GTT, 40-CU unlock, governor, RPC services) is in
[bc250-llm-setup](https://github.com/wdonega/bc250-llm-setup). In short:

| | Per board |
|---|---|
| APU | AMD BC-250 "Cyan Skillfish", RADV GFX1013, 40 CUs unlocked |
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

### What was tested

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

### Results

The run is still in progress. The table below is refreshed automatically each time a
config finishes. Per-test breakdown:
[`bc250/results/main/summary.md`](bc250/results/main/summary.md).

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
_22 configs complete so far._

| Config | Ctx | KV cache | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| flint-39.8B-A2.5B UD-Q3_K_XL (dual) | 32k | q8_0 | 5/6 | 8/9 | 12/12 | 6/9 | **31/36** | 0 | 115 | 28.5 | complete |
| Ornith-1.5-35B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 5/9 | 12/12 | 5/9 | **28/36** | 0 | 190 | 37.9 | complete |
| Ornith-1.5-35B-A3B IQ2_S (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 3/9 | **27/36** | 0 | 149 | 38.9 | complete |
| Qwen3.6-35B-A3B UD-Q4_K_M (dual) | 32k | q8_0 | 6/6 | 4/9 | 11/12 | 6/9 | **27/36** | 0 | 195 | 37.0 | complete |
| flint-39.8B-A2.5B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 6/9 | 12/12 | 2/9 | **26/36** | 0 | 110 | 31.7 | complete |
| Ornith-1.5-35B-A3B IQ2_S (dual-same) | 32k | q8_0 | 6/6 | 3/9 | 12/12 | 4/9 | **25/36** | 0 | 157 | 35.7 | complete |
| Qwen3.5-4B Q8_0 (single) | 32k | q8_0 | 5/6 | 5/9 | 12/12 | 3/9 | **25/36** | 6 | 204 | 29.0 | complete |
| Qwen3.6-35B-A3B UD-IQ2_XXS (single) | 32k | q8_0 | 6/6 | 5/9 | 11/12 | 3/9 | **25/36** | 0 | 138 | 34.3 | complete |
| LFM2.5-24B-A2B UD-Q5_K_XL (dual) | 32k | q8_0 | 5/6 | 3/9 | 12/12 | 4/9 | **24/36** | 0 | 245 | 44.8 | complete |
| LFM2.5-24B-A2B UD-Q3_K_XL (single) | 32k | q8_0 | 4/6 | 3/9 | 12/12 | 2/9 | **21/36** | 0 | 183 | 49.0 | complete |
| Nemotron-3.5-Bolt-E4B UD-Q6_K_XL (single) | 32k | q8_0 | 5/6 | 3/9 | 11/12 | 1/9 | **20/36** | 1 | 214 | 26.1 | complete |
| Ornith-1.5-9B Q5_K_M (single, retry of Q6_K) | 32k | q8_0 | 6/6 | 0/9 | 11/12 | 3/9 | **20/36** | 15 | 125 | 19.0 | complete |
| Ornith-1.5-9B Q6_K (single) | 32k | q8_0 | 6/6 | 1/9 | 12/12 | 0/9 | **19/36** | 14 | 103 | 18.5 | complete |
| Qwen3.8-27B UD-Q4_K_M (dual) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 2/9 | **19/36** | 17 | 36 | 7.5 | complete |
| Qwen3.8-27B UD-Q2_K_XL (single) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 2/9 | **19/36** | 17 | 45 | 7.7 | complete |
| Gemma-4-12B-it Q6_K (single) | 32k | q8_0 | 6/6 | 0/9 | 12/12 | 0/9 | **18/36** | 18 | 75 | 12.5 | complete |
| Qwen3.5-9B Q6_K (single) | 32k | q8_0 | 4/6 | 2/9 | 12/12 | 0/9 | **18/36** | 17 | 103 | 18.7 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-Q4_K_M (dual) | 32k | q8_0 | 4/6 | 1/9 | 12/12 | 1/9 | **18/36** | 16 | 31 | 7.0 | complete |
| Qwen3.8-27B-Fusion-NEO-CODER (DavidAU) NEO-CODER-MAX-IQ2_M (single) | 32k | q8_0 | 4/6 | 0/9 | 12/12 | 2/9 | **18/36** | 17 | 36 | 6.7 | complete |
| Gemma-4-12B-it UD-Q5_K_XL (single, retry of Q6_K) | 32k | q8_0 | 5/6 | 0/9 | 12/12 | 0/9 | **17/36** | 19 | 82 | 12.3 | complete |
| Qwen3-Coder-30B-A3B Q4_K_M (dual) | 32k | q8_0 | 6/6 | 3/9 | 6/12 | 0/9 | **15/36** | 0 | 202 | 39.1 | complete |
| Qwen3-Coder-30B-A3B UD-IQ2_M (single) | 32k | q8_0 | 5/6 | 2/9 | 6/12 | 0/9 | **13/36** | 1 | 128 | 35.1 | complete |
<!-- RESULTS:END -->

### Findings so far

- **The suite separates the models.** Configs in the same speed class are already 6
  points apart. An earlier, easier sanity suite had every model at 100 %, which is why
  every task here is built to make models fail.
- **MoE models with ~3B active parameters are the sweet spot on this board.** They
  generate at 30–55 tok/s even at 2–3 bit. A 27B dense model makes 7–8 tok/s at any
  quant, because the BC-250 is memory-bound on dense weights.
- **Basic tool calling is solved.** Every model tested so far scores 12/12 on
  multi-step calls, strict arguments, error recovery and refusing to act without data.
- **Reasoning is where they break.** No model has solved the 5-person logic puzzle yet.
  flint gives the same wrong answer every time. LFM gives a different one every run.
  flint gets the date arithmetic right but calls 2029-07-20 a Sunday (it is a Friday).
- **Speed ≠ quality.** LFM2.5 is the fastest model (49 tok/s) and the lowest scorer so far.
- **dual mode:** see the table as the dual configs finish. The open question is whether
  the bigger quant buys enough correctness to pay for the RPC speed cost.

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

36 calls per config (12 tests × 3 runs). A 1-run pilot ([`results/pilot`](bc250/results/pilot))
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
llama-server -hf <repo>:<quant> --no-mmproj -ngl 999 -fa on --ctx-size 32768 --parallel 1 \
  --cache-type-k q8_0 --cache-type-v q8_0 -b 2048 -ub 512 --jinja \
  --reasoning-budget 6144 --reasoning-budget-message " Preciso parar de pensar agora e dar a resposta final." \
  --cache-ram 0
# dual / dual-same add:  --rpc llm4.lab:50052 -ts 0.5,0.5
```

| | |
|---|---|
| context | 32k (24k fallback) |
| temperature / top_p / top_k / min_p | 0.6 / 0.95 / 20 / 0 |
| seed | 9000 + run |
| max tokens | 8k (long context), 12k (coding, reasoning), 4k per tool turn |

### Validating the suite

A wrong answer key would make every model look bad. `validate.py` checks the suite
itself, without any model:

- the reference solutions pass 100 % of the hidden tests;
- 11 negative controls fail. These are typical wrong implementations, such as `//` for
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
