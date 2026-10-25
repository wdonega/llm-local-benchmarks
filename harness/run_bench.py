#!/usr/bin/env python3
"""Benchmark runner.

Usage:
  python3 run_bench.py --all                # singles -> duals -> models flagged run_last
  python3 run_bench.py --only qwen3-coder-30b:single --runs 1 --tag pilot
  python3 run_bench.py --best-single-dual   # best single config re-run on 2 boards, same quant
  python3 run_bench.py --retry-timeouts     # configs with many timeouts re-run one quant lower
  python3 run_bench.py --summary

Every call is saved as soon as it finishes, so an interrupted run resumes where it stopped.
Results go to $BENCH_OUT/results/<tag>/.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import common as rb  # noqa: E402
import tasks as T  # noqa: E402

CTX = 32768
CTX_FALLBACK = 24576
REASONING_BUDGET = 6144
BUDGET_MESSAGE = " Preciso parar de pensar agora e dar a resposta final."
SAMPLING = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0}
OUTPUT_CHECK_PROMPT = "Qual é a capital da França? Responda em uma frase."
KV_CACHE = "q8_0"  # --cache-type-k / --cache-type-v
# HF repos the disk cleanup must never delete (e.g. the model your production server uses)
KEEP_CACHE = {r.strip() for r in os.environ.get("BENCH_KEEP_CACHE", "").split(",") if r.strip()}


def log(msg):
    rb.log(msg)


def is_cached(cfg):
    snap = os.path.join(rb.cache_dir(cfg["repo"]), "snapshots")
    q = cfg["quant"].lower()
    for path in glob.glob(os.path.join(snap, "*", "*.gguf")):
        name = os.path.basename(path).lower()
        if (f"-{q}." in name or f"-{q}-" in name) and os.path.exists(path):
            return True
    return False


def start_server(cfg, alias, log_name, ctx):
    os.makedirs(rb.LOGS, exist_ok=True)
    log_path = os.path.join(rb.LOGS, log_name + ".log")
    cmd = [
        rb.SERVER, "-hf", f"{cfg['repo']}:{cfg['quant']}", "--no-mmproj",
        "-ngl", "999", "-fa", "on", "--ctx-size", str(ctx), "--parallel", "1",
        "--cache-type-k", KV_CACHE, "--cache-type-v", KV_CACHE, "-b", "2048", "-ub", "512",
        "--jinja", "--reasoning-budget", str(REASONING_BUDGET),
        "--reasoning-budget-message", BUDGET_MESSAGE,
        "--host", "127.0.0.1", "--port", str(rb.PORT), "--alias", alias,
    ]
    if cfg["mode"].startswith("dual"):  # dual and dual-same
        cmd += ["--rpc", rb.RPC, "-ts", "0.5,0.5"]
    log(f"starting (ctx={ctx}): {' '.join(cmd)}")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    rb.CURRENT_PROC, rb.CURRENT_LOG = proc, logf
    return proc, logf, log_path


def timings_of(resp):
    t = (resp or {}).get("timings") or {}
    return {
        "prompt_n": t.get("prompt_n") or 0,
        "prompt_ms": t.get("prompt_ms") or 0.0,
        "pred_n": t.get("predicted_n") or 0,
        "pred_ms": t.get("predicted_ms") or 0.0,
        "cache_n": t.get("cache_n") or 0,
    }


def add_timings(acc, t):
    for k, v in t.items():
        acc[k] = acc.get(k, 0) + v


def is_timeout(err):
    return bool(err) and (err == "timeout" or "rc=28" in err)


def payload(alias, messages, run, max_tokens, tools=None):
    p = {"model": alias, "messages": messages, "seed": 9000 + run, "max_tokens": max_tokens,
         "stream": False, **SAMPLING}
    if tools:
        p["tools"] = tools
        p["tool_choice"] = "auto"
    return p


def settle_after_timeout():
    for _ in range(30):
        if rb.health():
            break
        time.sleep(2)
    time.sleep(3)


def run_single_turn(alias, messages, run, max_tokens):
    resp, err, wall = rb.chat(payload(alias, messages, run, max_tokens))
    msg = {}
    finish = None
    if resp is not None:
        try:
            msg = resp["choices"][0]["message"]
            finish = resp["choices"][0].get("finish_reason")
        except Exception:
            msg = {}
    return msg, finish, timings_of(resp), err, wall


def run_tool_task(alias, task, run):
    messages = T.tool_messages(task)
    state = {}
    acc = {}
    steps_log = []
    final = ""
    err = None
    wall_total = 0.0
    finish = None
    reasoning_chars = 0
    for step in range(task["max_steps"]):
        resp, err, wall = rb.chat(payload(alias, messages, run, 4096, tools=task["tools"]))
        wall_total += wall
        if err:
            break
        add_timings(acc, timings_of(resp))
        try:
            msg = resp["choices"][0]["message"]
            finish = resp["choices"][0].get("finish_reason")
        except Exception:
            msg = {}
        reasoning_chars += len(msg.get("reasoning_content") or "")
        tcs = msg.get("tool_calls") or []
        if not tcs:
            text_call = T.content_tool_call(msg)
            if text_call:
                state["text_tool_call"] = text_call
            final = T.final_text(msg)
            break
        for i, tc in enumerate(tcs):
            if not tc.get("id"):
                tc["id"] = f"call_{step}_{i}"
        assistant = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs}
        if msg.get("reasoning_content"):
            assistant["reasoning_content"] = msg["reasoning_content"]
        messages.append(assistant)
        for tc in tcs:
            fn = tc.get("function") or {}
            name = fn.get("name")
            args = T.parse_args(fn.get("arguments"))
            result = task["simulate"](name, args, state)
            steps_log.append({"name": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result, ensure_ascii=False)})
    else:
        state["max_steps"] = True
    if err:
        ok, detail = False, {}
    else:
        ok, detail = task["check"](final, state)
        if state.get("text_tool_call"):
            ok = False
            detail["tool_call_as_text"] = state["text_tool_call"]
    return ok, detail, {"final": final[:3000], "steps": steps_log, "finish": finish,
                        "reasoning_chars": reasoning_chars}, acc, err, wall_total


def specs(runs):
    out = []
    for t in T.LONG_TASKS:
        out += [("long_context", t["id"], r, t) for r in range(1, runs + 1)]
    for t in T.CODING_TASKS:
        out += [("coding", t["id"], r, t) for r in range(1, runs + 1)]
    for t in T.TOOL_TASKS:
        out += [("tool_call", t["id"], r, t) for r in range(1, runs + 1)]
    for t in T.REASONING_TASKS:
        out += [("reasoning", t["id"], r, t) for r in range(1, runs + 1)]
    return out


def execute(alias, cat, task, run):
    """Return (correct, detail, extra, timings, err, wall)."""
    if cat == "tool_call":
        return run_tool_task(alias, task, run)
    if cat == "long_context":
        msg, finish, t, err, wall = run_single_turn(alias, T.long_messages(task), run, 8192)
        ok, detail = (False, {}) if err else T.score_long(task, msg)
    elif cat == "coding":
        msg, finish, t, err, wall = run_single_turn(alias, T.coding_messages(task), run, 12288)
        ok, detail = False, {}
        if not err:
            code = T.extract_code(T.final_text(msg), task["func"])
            wd = tempfile.mkdtemp(dir=rb.WORK)
            try:
                ok, detail = rb.run_docker_tests(code, T.coding_test_source(task), wd)
            finally:
                shutil.rmtree(wd, ignore_errors=True)
            detail = {"passed": detail.get("passed"), "total": detail.get("total"),
                      "failures": [r for r in detail.get("results", []) if not r["ok"]][:6],
                      "error": detail.get("error"), "code": code[:3000]}
    else:
        msg, finish, t, err, wall = run_single_turn(
            alias, [{"role": "user", "content": task["prompt"]}], run, 12288)
        ok, detail = (False, {}) if err else T.score_reasoning(task["id"], msg)
    extra = {"final": T.final_text(msg)[:3000], "finish": finish,
             "reasoning_chars": len(msg.get("reasoning_content") or "")}
    return ok, detail, extra, t, err, wall


def run_config(model, cfg, runs, results_dir, force=False, protected=()):
    alias = f"{model['key']}-{cfg['mode']}"
    stem = f"{model['key']}__{cfg['mode']}__{cfg['quant']}"
    path = os.path.join(results_dir, stem + ".json")
    if force and os.path.exists(path):
        os.remove(path)
    data = rb.load_json(path, None) or {
        "model": model["label"], "key": model["key"], "mode": cfg["mode"], "repo": cfg["repo"],
        "quant": cfg["quant"], "runs": runs, "calls": [], "status": "running",
        "settings": {"ctx": CTX, "kv_cache": KV_CACHE, "reasoning_budget": REASONING_BUDGET, **SAMPLING},
        "retry_of": cfg.get("retry_of"),
    }
    if data.get("status") == "complete":
        log(f"skipping {stem}: already complete")
        return data
    data["status"] = "running"
    seen = {(c["category"], c["test"], c["run"]) for c in data["calls"]}
    todo = [s for s in specs(runs) if (s[0], s[1], s[2]) not in seen]
    if not todo:
        data["status"] = "complete"
        rb.save_json(path, data)
        return data

    if not is_cached(cfg):
        need = int(cfg["size_gib"] * 1.15 * rb.GIB) + 5 * rb.GIB
        rb.track_repo(cfg["repo"])
        if not rb.ensure_space(need, {rb.cache_dir(cfg["repo"])} | set(protected)):
            data["status"] = "error"
            data["error"] = "not enough disk space"
            rb.save_json(path, data)
            return data

    proc = logf = None
    try:
        ctx_used = None
        for ctx in (CTX, CTX_FALLBACK):
            start = time.time()
            proc, logf, log_path = start_server(cfg, alias, stem, ctx)
            if rb.wait_ready(proc):
                ctx_used = ctx
                data["load_s"] = round(time.time() - start, 1)
                break
            log(f"{stem}: failed with ctx={ctx}")
            rb.stop_server(proc, logf)
            proc = logf = None
        if ctx_used is None:
            data["status"] = "error"
            data["error"] = "server did not load (see log)"
            rb.save_json(path, data)
            return data
        data["settings"]["ctx"] = ctx_used
        data["log"] = log_path
        log(f"{stem}: loaded in {data['load_s']}s (ctx={ctx_used})")
        # output check: a corrupted RPC tensor cache on the worker once produced pure garbage
        # for hours; a trivial question catches that before 36 wasted calls
        resp, err, _ = rb.chat(payload(alias, [{"role": "user", "content": OUTPUT_CHECK_PROMPT}], 0, 2048))
        msg = ((resp or {}).get("choices") or [{}])[0].get("message") or {}
        seen = T.normalize((msg.get("content") or "") + " " + (msg.get("reasoning_content") or ""))
        if err or "paris" not in seen:
            data["status"] = "error"
            data["error"] = ("output check failed (garbage output? on dual, clear the RPC worker "
                             f"cache): {err or (msg.get('content') or '')[:200]!r}")
            rb.save_json(path, data)
            log(f"{stem}: {data['error']}")
            return data

        total = len(specs(runs))
        for cat, tid, run, task in todo:
            ok, detail, extra, t, err, wall = execute(alias, cat, task, run)
            call = {
                "category": cat, "test": tid, "run": run, "correct": bool(ok),
                "timeout": is_timeout(err), "error": err, "wall_s": round(wall, 1),
                "prompt_tokens": t.get("prompt_n"), "completion_tokens": t.get("pred_n"),
                "cache_tokens": t.get("cache_n"),
                "prompt_tps": round(t["prompt_n"] / t["prompt_ms"] * 1000, 2) if t.get("prompt_ms") else None,
                "gen_tps": round(t["pred_n"] / t["pred_ms"] * 1000, 2) if t.get("pred_ms") else None,
                "detail": detail, **extra,
            }
            data["calls"].append(call)
            rb.save_json(path, data)
            status = "OK" if ok else ("TIMEOUT" if call["timeout"] else ("ERROR" if err else "FAIL"))
            log(f"{stem}: {len(data['calls'])}/{total} {cat}/{tid} run {run} -> {status} "
                f"({call['gen_tps'] or '?'} t/s, {call['wall_s']}s)")
            if err:
                log(f"  error: {err[:200]}")
                if call["timeout"]:
                    settle_after_timeout()
                elif not rb.health():
                    log(f"{stem}: server died; aborting config")
                    data["status"] = "error"
                    data["error"] = "server died during the tests"
                    rb.save_json(path, data)
                    return data
        data["status"] = "complete"
        rb.save_json(path, data)
        log(f"{stem}: complete")
        return data
    finally:
        rb.stop_server(proc, logf)


def config_done(model, cfg, results_dir):
    path = os.path.join(results_dir, f"{model['key']}__{cfg['mode']}__{cfg['quant']}.json")
    return (rb.load_json(path, None) or {}).get("status") == "complete"


def ordered_configs(models, only=None):
    singles, duals, last = [], [], []
    for m in models:
        for cfg in m["configs"]:
            key = f"{m['key']}:{cfg['mode']}"
            if only and key not in only:
                continue
            if m.get("run_last"):  # dense/slow models go last
                last.append((m, cfg))
            elif cfg["mode"] == "single":
                singles.append((m, cfg))
            else:
                duals.append((m, cfg))
    return singles + duals + last


CAT_ORDER = ["long_context", "coding", "tool_call", "reasoning"]


def summarize(results_dir):
    rows, configs = [], []
    for f in sorted(glob.glob(os.path.join(results_dir, "*__*.json"))):
        d = rb.load_json(f, {})
        if not isinstance(d, dict) or "calls" not in d:
            continue
        configs.append(d)
        for c in d["calls"]:
            rows.append({k: c.get(k) for k in ("category", "test", "run", "correct", "timeout", "error",
                                               "wall_s", "prompt_tokens", "completion_tokens",
                                               "prompt_tps", "gen_tps", "reasoning_chars", "finish")}
                        | {"model": d["model"], "mode": d["mode"], "quant": d["quant"]})
    if not configs:
        return
    import csv
    with open(os.path.join(results_dir, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def label(d):
        retry = f", retry of {d['retry_of']}" if d.get("retry_of") else ""
        return f"{d['model']} {d['quant']} ({d['mode']}{retry})"

    md = ["# Benchmark results", "",
          f"Settings: ctx {CTX} ({CTX_FALLBACK} fallback; see the Ctx column), KV cache {KV_CACHE}, reasoning budget {REASONING_BUDGET} tokens, "
          f"temperature {SAMPLING['temperature']}, timeout {rb.CALL_TIMEOUT}s per call.", "",
          "## Scoreboard", "",
          "| Config | Ctx | KV cache | Long context | Coding | Tool call | Reasoning | Total | Timeouts | Prompt t/s | Gen t/s | Status |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    ranked = []
    for d in configs:
        cats = defaultdict(lambda: [0, 0])
        tos = 0
        ptps, gtps = [], []
        for c in d["calls"]:
            cats[c["category"]][1] += 1
            cats[c["category"]][0] += int(bool(c["correct"]))
            tos += int(bool(c.get("timeout")))
            if c.get("prompt_tps") and (c.get("prompt_tokens") or 0) > 200:
                ptps.append(c["prompt_tps"])
            if c.get("gen_tps"):
                gtps.append(c["gen_tps"])
        tot = sum(v[0] for v in cats.values())
        n = sum(v[1] for v in cats.values())
        ranked.append((tot, n, d, cats, tos, ptps, gtps))
    ranked.sort(key=lambda x: (-x[0], x[2]["model"]))
    for tot, n, d, cats, tos, ptps, gtps in ranked:
        cells = [f"{cats[c][0]}/{cats[c][1]}" for c in CAT_ORDER]
        p = f"{sum(ptps)/len(ptps):.0f}" if ptps else "-"
        g = f"{sum(gtps)/len(gtps):.1f}" if gtps else "-"
        st = d.get("settings") or {}
        ctx = f"{st['ctx'] // 1024}k" if st.get("ctx") else "-"
        kv = st.get("kv_cache", "q8_0")  # every run so far used q8_0
        md.append(f"| {label(d)} | {ctx} | {kv} | " + " | ".join(cells) + f" | **{tot}/{n}** | {tos} | {p} | {g} | {d['status']} |")

    tests = []
    for cat, group in (("long_context", T.LONG_TASKS), ("coding", T.CODING_TASKS),
                       ("tool_call", T.TOOL_TASKS), ("reasoning", T.REASONING_TASKS)):
        tests += [(cat, t["id"]) for t in group]
    md += ["", "## Correct per test (out of 3 runs; T = timeouts)", "",
           "| Test | " + " | ".join(f"{d['model']} {d['quant']} ({d['mode']})" for _, _, d, *_ in ranked) + " |",
           "|---|" + "---|" * len(ranked)]
    for cat, tid in tests:
        cells = []
        for _, _, d, *_ in ranked:
            cs = [c for c in d["calls"] if c["test"] == tid]
            if not cs:
                cells.append("-")
                continue
            ok = sum(bool(c["correct"]) for c in cs)
            to = sum(bool(c.get("timeout")) for c in cs)
            cells.append(f"{ok}/{len(cs)}" + (f" T{to}" if to else ""))
        md.append(f"| {cat}/{tid} | " + " | ".join(cells) + " |")
    with open(os.path.join(results_dir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    log(f"summary: {os.path.join(results_dir, 'summary.md')}")


def run_best_single_dual(results_dir, runs):
    """Re-run the best complete single config (score, then gen t/s) over RPC with the same quant."""
    best = None
    for f in glob.glob(os.path.join(results_dir, "*__single__*.json")):
        d = rb.load_json(f, {})
        if not isinstance(d, dict) or d.get("status") != "complete":
            continue
        tot = sum(int(bool(c["correct"])) for c in d["calls"])
        g = [c["gen_tps"] for c in d["calls"] if c.get("gen_tps")]
        score = (tot, sum(g) / len(g) if g else 0)
        if best is None or score > best[0]:
            best = (score, d)
    if best is None:
        log("no complete single config")
        return 1
    d = best[1]
    models = {m["key"]: m for m in rb.load_json(rb.MODELS_PATH, [])}
    model = models[d["key"]]
    cfg = next(c for c in model["configs"] if c["mode"] == "single")
    cfg = dict(cfg, mode="dual-same")
    log(f"best single: {d['model']} {d['quant']} ({best[0][0]} correct); running dual-same")
    run_config(model, cfg, runs, results_dir,
               protected={rb.cache_dir(r) for r in KEEP_CACHE})
    summarize(results_dir)
    return 0


RETRY_TIMEOUTS = 4  # configs with this many timeouts (of 36 calls) get re-run one quant lower
RETRY_SIZE_RATIO = 0.9  # "one quant lower" = largest file at most 90% of the current size


def hf_gguf_files(repo):
    """{filename: size_bytes} for the top-level .gguf files of a HF repo."""
    r = subprocess.run(["curl", "-sf", "--max-time", "30",
                        f"https://huggingface.co/api/models/{repo}/tree/main"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    try:
        return {f["path"]: f.get("size", 0) for f in json.loads(r.stdout)
                if f.get("type") == "file" and f["path"].endswith(".gguf") and "/" not in f["path"]}
    except Exception:
        return {}


def lower_quant(repo, quant):
    """Next smaller quant tag in the same repo, or None. Skips MTP (unless current is MTP), BF16/F16/F32, mmproj."""
    files = hf_gguf_files(repo)
    cur = next((n for n in files if n.lower().endswith(f"-{quant.lower()}.gguf")), None)
    if not cur:
        return None
    base = cur[: -len(f"-{quant}.gguf")]
    cur_size = files[cur]
    best = None
    for name, size in files.items():
        if not name.startswith(base + "-") or "mmproj" in name.lower():
            continue
        tag = name[len(base) + 1 : -len(".gguf")]
        up = tag.upper()
        if re.search(r"(^|-)(BF16|F16|F32)$", up) or re.search(r"\d{5}-OF-\d{5}", up):
            continue
        if ("MTP" in up) != ("MTP" in quant.upper()):
            continue
        if 0 < size <= cur_size * RETRY_SIZE_RATIO and (best is None or size > best[1]):
            best = (tag, size)
    return best


def run_timeout_retries(results_dir, runs):
    """Re-run every complete config with many timeouts one quant lower (once; retries are not retried)."""
    models = {m["key"]: m for m in rb.load_json(rb.MODELS_PATH, [])}
    done = []
    for f in sorted(glob.glob(os.path.join(results_dir, "*__*.json"))):
        d = rb.load_json(f, {})
        if not isinstance(d, dict) or d.get("status") != "complete" or d.get("retry_of"):
            continue
        tos = sum(bool(c.get("timeout")) for c in d.get("calls", []))
        if tos < RETRY_TIMEOUTS or d["key"] not in models:
            continue
        low = lower_quant(d["repo"], d["quant"])
        if not low:
            log(f"{d['key']} {d['quant']}: {tos} timeouts, but no lower quant found")
            continue
        tag, size = low
        cfg = {"mode": d["mode"], "repo": d["repo"], "quant": tag, "size_gib": round(size / rb.GIB, 2),
               "retry_of": d["quant"]}
        log(f"{d['key']} {d['mode']} {d['quant']}: {tos} timeouts -> retrying with {tag} ({cfg['size_gib']} GiB)")
        run_config(models[d["key"]], cfg, runs, results_dir,
                   protected={rb.cache_dir(r) for r in KEEP_CACHE})
        summarize(results_dir)
        done.append(tag)
    log(f"timeout retries: {len(done)} config(s)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", help="comma-separated key:mode list")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--best-single-dual", action="store_true",
                    help="re-run the best single config with the SAME quant on 2 boards (dual-same)")
    ap.add_argument("--retry-timeouts", action="store_true",
                    help=f"re-run configs with >= {RETRY_TIMEOUTS} timeouts one quant lower")
    args = ap.parse_args()

    results_dir = os.path.join(rb.OUT, "results", args.tag)
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(rb.WORK, exist_ok=True)
    if args.summary:
        summarize(results_dir)
        return 0
    if args.best_single_dual:
        return run_best_single_dual(results_dir, args.runs)
    if args.retry_timeouts:
        return run_timeout_retries(results_dir, args.runs)
    if not args.all and not args.only:
        ap.print_help()
        return 1
    models = rb.load_json(rb.MODELS_PATH, [])
    only = set(args.only.split(",")) if args.only else None
    queue = ordered_configs(models, only)
    for i, (m, cfg) in enumerate(queue):
        # only delete caches of repos that are done: protect everything still to run
        protected = {rb.cache_dir(c["repo"]) for mm, c in queue[i:]
                     if not config_done(mm, c, results_dir)}
        protected |= {rb.cache_dir(r) for r in KEEP_CACHE}
        run_config(m, cfg, args.runs, results_dir, force=args.force, protected=protected)
        summarize(results_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
