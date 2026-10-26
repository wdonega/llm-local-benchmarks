#!/usr/bin/env python3
"""Use-case runner: the LiteLLM routes served by the BC-250, with thinking off.

Usage:
  python3 run_usecases.py --models ../bc250/models-usecases.json --all --runs 3
  python3 run_usecases.py --models ../bc250/models-usecases.json --only ornith35:single --runs 1 --tag try
  python3 run_usecases.py --summary

Server: 64k context (enough for the input and output of every route), thinking off
(--reasoning-budget 0 on the server and enable_thinking=false per request, so models whose
template has no switch are also forced to answer directly). Per call: the route's temperature,
max_tokens and timeout (usecases.ROUTES) plus the model's "sampling_nothink" (top_p, top_k,
min_p, penalties). Results go to $BENCH_OUT/results/<tag>/, resumable call by call.
"""

import argparse
import glob
import os
import subprocess
import sys
import time
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import common as rb  # noqa: E402
import run_bench as RB  # noqa: E402
import usecases as U  # noqa: E402

CTX = 65536
KV_CACHE = "q8_0"


def log(msg):
    rb.log(msg)


def start_server(cfg, alias, log_name):
    os.makedirs(rb.LOGS, exist_ok=True)
    log_path = os.path.join(rb.LOGS, log_name + ".log")
    cmd = [
        rb.SERVER, "-hf", f"{cfg['repo']}:{cfg['quant']}", "--no-mmproj",
        "-ngl", "999", "-fa", "on", "--ctx-size", str(CTX), "--parallel", "1",
        "--cache-type-k", KV_CACHE, "--cache-type-v", KV_CACHE, "-b", "2048", "-ub", "512",
        "--jinja", "--reasoning-budget", "0", "--cache-ram", "0",
        "--host", "127.0.0.1", "--port", str(rb.PORT), "--alias", alias,
    ]
    if cfg["mode"] == "dual":
        cmd += ["--rpc", rb.RPC, "-ts", "0.5,0.5"]
    log(f"starting: {' '.join(cmd)}")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    rb.CURRENT_PROC, rb.CURRENT_LOG = proc, logf
    return proc, logf, log_path


def payload(alias, route, messages, run, sampling):
    r = U.ROUTES[route]
    return {"model": alias, "messages": messages, "seed": 9000 + run, "stream": False,
            "max_tokens": r["max_tokens"], **sampling, "temperature": r["temperature"],
            "chat_template_kwargs": {"enable_thinking": False}}


def specs(runs):
    return [(route, t["id"], r, t) for route, group in U.SUITE for t in group for r in range(1, runs + 1)]


def run_config(model, cfg, runs, results_dir, protected=()):
    alias = f"{model['key']}-{cfg['mode']}"
    stem = f"{model['key']}__{cfg['mode']}__{cfg['quant']}"
    path = os.path.join(results_dir, stem + ".json")
    sampling = dict(model["sampling_nothink"])
    data = rb.load_json(path, None) or {
        "model": model["label"], "key": model["key"], "mode": cfg["mode"], "repo": cfg["repo"],
        "quant": cfg["quant"], "runs": runs, "calls": [], "status": "running",
        "settings": {"ctx": CTX, "kv_cache": KV_CACHE, "thinking": "off", "sampling": sampling,
                     "routes": U.ROUTES},
    }
    if data.get("status") == "complete":
        log(f"skipping {stem}: already complete")
        return data
    data["status"] = "running"
    seen = {(c["route"], c["test"], c["run"]) for c in data["calls"]}
    todo = [s for s in specs(runs) if (s[0], s[1], s[2]) not in seen]

    if not RB.is_cached(cfg):
        need = int(cfg["size_gib"] * 1.15 * rb.GIB) + 5 * rb.GIB
        rb.track_repo(cfg["repo"])
        if not rb.ensure_space(need, {rb.cache_dir(cfg["repo"])} | set(protected)):
            data["status"], data["error"] = "error", "not enough disk space"
            rb.save_json(path, data)
            return data

    proc = logf = None
    try:
        start = time.time()
        proc, logf, log_path = start_server(cfg, alias, "usecases__" + stem)
        if not rb.wait_ready(proc):
            data["status"], data["error"] = "error", "server did not load (see log)"
            rb.save_json(path, data)
            return data
        data["load_s"], data["log"] = round(time.time() - start, 1), log_path
        log(f"{stem}: loaded in {data['load_s']}s")
        resp, err, _ = rb.chat(payload(alias, "simple-chat", [{"role": "user", "content": RB.OUTPUT_CHECK_PROMPT}],
                                       0, sampling), timeout=120)
        msg = ((resp or {}).get("choices") or [{}])[0].get("message") or {}
        if err or "paris" not in U.plain(msg.get("content") or ""):
            data["status"] = "error"
            data["error"] = f"output check failed: {err or (msg.get('content') or '')[:200]!r}"
            rb.save_json(path, data)
            log(f"{stem}: {data['error']}")
            return data

        total = len(specs(runs))
        for route, tid, run, task in todo:
            route_cfg = U.ROUTES[route]
            resp, err, wall = rb.chat(payload(alias, route, U.messages_for(route, task), run, sampling),
                                      timeout=route_cfg["timeout"])
            msg, finish, t = {}, None, {}
            if resp is not None:
                try:
                    msg = resp["choices"][0]["message"]
                    finish = resp["choices"][0].get("finish_reason")
                except Exception:
                    msg = {}
                t = resp.get("timings") or {}
            text = (msg.get("content") or "").strip()
            timeout = RB.is_timeout(err)
            ok, detail = (False, {}) if err else task["score"](text, wall)
            call = {
                "route": route, "test": tid, "run": run, "correct": bool(ok), "timeout": timeout,
                "error": err, "wall_s": round(wall, 2), "finish": finish,
                "prompt_tokens": t.get("prompt_n"), "completion_tokens": t.get("predicted_n"),
                "gen_tps": round(t["predicted_per_second"], 2) if t.get("predicted_per_second") else None,
                "reasoning_chars": len(msg.get("reasoning_content") or ""),
                "final": text[:3000], "detail": detail,
            }
            data["calls"].append(call)
            rb.save_json(path, data)
            status = "OK" if ok else ("TIMEOUT" if timeout else ("ERROR" if err else "FAIL"))
            log(f"{stem}: {len(data['calls'])}/{total} {route}/{tid} run {run} -> {status} ({call['wall_s']}s)"
                + (f" {detail.get('failed')}" if not ok and detail.get("failed") else ""))
            if err:
                if timeout:
                    RB.settle_after_timeout()
                elif not rb.health():
                    data["status"], data["error"] = "error", "server died during the tests"
                    rb.save_json(path, data)
                    return data
        data["status"] = "complete"
        rb.save_json(path, data)
        log(f"{stem}: complete")
        return data
    finally:
        rb.stop_server(proc, logf)


def pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else None


def summarize(results_dir):
    configs = []
    for f in sorted(glob.glob(os.path.join(results_dir, "*__*.json"))):
        d = rb.load_json(f, {})
        if isinstance(d, dict) and "calls" in d:
            configs.append(d)
    if not configs:
        return
    routes = [r for r, _ in U.SUITE]
    rows = []
    for d in configs:
        per = defaultdict(lambda: [0, 0])
        walls = defaultdict(list)
        for c in d["calls"]:
            per[c["route"]][0] += int(bool(c["correct"]))
            per[c["route"]][1] += 1
            walls[c["route"]].append(c["wall_s"])
        tot = sum(v[0] for v in per.values())
        n = sum(v[1] for v in per.values())
        tos = sum(bool(c.get("timeout")) for c in d["calls"])
        g = [c["gen_tps"] for c in d["calls"] if c.get("gen_tps")]
        rows.append((tot, n, d, per, walls, tos, g))
    rows.sort(key=lambda x: (-x[0], x[2]["model"]))
    md = ["# Use-case results (LiteLLM routes, thinking off)", "",
          f"Settings: ctx {CTX}, KV cache {KV_CACHE}, thinking off; per route temperature / max_tokens / timeout: "
          + ", ".join(f"{r} {v['temperature']}/{v['max_tokens']}/{v['timeout']}s" for r, v in U.ROUTES.items())
          + "; top_p/top_k/min_p/penalties from each model card.", "",
          "## Scoreboard", "",
          "| Config | " + " | ".join(routes) + " | Total | Timeouts | Voice p95 latency | Gen t/s | Status |",
          "|---|" + "---|" * len(routes) + "---|---|---|---|---|"]
    for tot, n, d, per, walls, tos, g in rows:
        cells = [f"{per[r][0]}/{per[r][1]}" for r in routes]
        p95 = pct(walls["voice-chat"], 0.95)
        md.append(f"| {d['model']} {d['quant']} ({d['mode']}) | " + " | ".join(cells)
                  + f" | **{tot}/{n}** | {tos} | {f'{p95:.1f}s' if p95 is not None else '-'} | "
                  + (f"{sum(g)/len(g):.1f}" if g else "-") + f" | {d['status']} |")
    md += ["", "## Latency per route (median wall time per call, seconds)", "",
           "| Config | " + " | ".join(routes) + " |", "|---|" + "---|" * len(routes)]
    for _, _, d, _, walls, _, _ in rows:
        md.append(f"| {d['model']} {d['quant']} ({d['mode']}) | "
                  + " | ".join(f"{pct(walls[r], 0.5):.1f}" if walls[r] else "-" for r in routes) + " |")
    md += ["", "## Correct per test (out of 3 runs; T = timeouts)", "",
           "| Test | " + " | ".join(f"{d['model']} {d['quant']} ({d['mode']})" for _, _, d, *_ in rows) + " |",
           "|---|" + "---|" * len(rows)]
    for route, group in U.SUITE:
        for t in group:
            cells = []
            for _, _, d, *_ in rows:
                cs = [c for c in d["calls"] if c["test"] == t["id"]]
                if not cs:
                    cells.append("-")
                    continue
                ok = sum(bool(c["correct"]) for c in cs)
                to = sum(bool(c.get("timeout")) for c in cs)
                cells.append(f"{ok}/{len(cs)}" + (f" T{to}" if to else ""))
            md.append(f"| {route}/{t['id']} | " + " | ".join(cells) + " |")
    with open(os.path.join(results_dir, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    log(f"summary: {os.path.join(results_dir, 'summary.md')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="models file with a 'sampling_nothink' entry per model")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", help="comma-separated key:mode list")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--tag", default="usecases")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.models:
        rb.MODELS_PATH = os.path.abspath(args.models)
    results_dir = os.path.join(rb.OUT, "results", args.tag)
    os.makedirs(results_dir, exist_ok=True)
    if args.summary:
        summarize(results_dir)
        return 0
    if not args.all and not args.only:
        ap.print_help()
        return 1
    models = rb.load_json(rb.MODELS_PATH, [])
    only = set(args.only.split(",")) if args.only else None
    queue = RB.ordered_configs(models, only)
    keep = {rb.cache_dir(r) for r in RB.KEEP_CACHE}
    for i, (m, cfg) in enumerate(queue):
        protected = {rb.cache_dir(c["repo"]) for _, c in queue[i:]} | keep
        run_config(m, cfg, args.runs, results_dir, protected=protected)
        summarize(results_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
