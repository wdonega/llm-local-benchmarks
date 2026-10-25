#!/usr/bin/env python3
"""Suite v1 runner (sanity + speed) and the helpers shared with the v2 runner.

Usage:
  python3 run_bench.py --smoke             # quick load test of the model that has a "smoke" entry
  python3 run_bench.py --all
  python3 run_bench.py --model flint
  python3 run_bench.py --model flint --mode single --force

Configuration comes from environment variables (see README):
  LLAMA_SERVER, BENCH_RPC, BENCH_PORT, BENCH_MODELS, BENCH_OUT
"""

import argparse
import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(BASE)
sys.path.insert(0, BASE)
import tasks  # noqa: E402

SERVER = os.environ.get("LLAMA_SERVER", os.path.expanduser("~/llama.cpp/build/bin/llama-server"))
HF_CACHE = os.path.expanduser(os.environ.get("HF_HUB_CACHE", "~/.cache/huggingface/hub"))
PORT = int(os.environ.get("BENCH_PORT", "8081"))
RPC = os.environ.get("BENCH_RPC", "llm4.lab:50052")
OUT = os.path.abspath(os.environ.get("BENCH_OUT", os.path.join(REPO, "bc250")))
MODELS_PATH = os.path.abspath(os.environ.get("BENCH_MODELS", os.path.join(OUT, "models.json")))
CTX = 16384
CALL_TIMEOUT = 300
LOAD_TIMEOUT = 3600
RESULTS = os.path.join(OUT, "results", "v1")
LOGS = os.path.join(OUT, "logs")
WORK = os.path.join(OUT, "work")
STATE_PATH = os.path.join(OUT, "state.json")
GIB = 2**30

CURRENT_PROC = None
CURRENT_LOG = None


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"downloaded": []}


STATE = load_state()


def save_state():
    os.makedirs(OUT, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False, indent=2)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cache_dir(repo):
    return os.path.join(HF_CACHE, "models--" + repo.replace("/", "--"))


def track_repo(repo):
    d = cache_dir(repo)
    if d not in STATE["downloaded"]:
        STATE["downloaded"].append(d)
        save_state()


def ensure_space(need_bytes, protected):
    """Free disk space by deleting HF caches downloaded by earlier runs, oldest first.

    Only repos this harness downloaded (state.json) are candidates, and anything in
    `protected` is never touched.
    """
    while True:
        free = shutil.disk_usage(HF_CACHE if os.path.isdir(HF_CACHE) else OUT).free
        if free >= need_bytes:
            return True
        victim = None
        for d in STATE["downloaded"]:
            if d in protected:
                continue
            if os.path.isdir(d):
                victim = d
                break
        if victim is None:
            return free >= need_bytes
        log(f"disk: {free / GIB:.1f} GiB free; deleting old cache {victim}")
        shutil.rmtree(victim, ignore_errors=True)
        STATE["downloaded"].remove(victim)
        save_state()


def call_url(path):
    return f"http://127.0.0.1:{PORT}{path}"


def health():
    r = subprocess.run(
        ["curl", "-sf", "--max-time", "5", call_url("/health")],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def chat(payload, timeout=CALL_TIMEOUT):
    """POST /v1/chat/completions and return (json, error, wall_s)."""
    data = json.dumps(payload, ensure_ascii=False)
    start = time.time()
    try:
        r = subprocess.run(
            [
                "curl",
                "-sS",
                "--max-time",
                str(timeout),
                "-H",
                "Content-Type: application/json",
                "--data-binary",
                "@-",
                call_url("/v1/chat/completions"),
            ],
            input=data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout + 15,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout", time.time() - start
    except Exception as e:
        return None, f"exception: {e!r}", time.time() - start
    wall = time.time() - start
    if r.returncode != 0:
        return None, f"curl rc={r.returncode}: {r.stderr.strip()[:500]}", wall
    try:
        return json.loads(r.stdout), None, wall
    except Exception:
        return None, f"invalid JSON: {r.stdout.strip()[:500]}", wall


def start_server(cfg, alias, log_name):
    global CURRENT_PROC, CURRENT_LOG
    os.makedirs(LOGS, exist_ok=True)
    log_path = os.path.join(LOGS, log_name + ".log")
    cmd = [
        SERVER,
        "-hf",
        f"{cfg['repo']}:{cfg['quant']}",
        "--no-mmproj",
        "-ngl",
        "999",
        "-fa",
        "on",
        "--ctx-size",
        str(CTX),
        "--parallel",
        "1",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "-b",
        "2048",
        "-ub",
        "512",
        "--jinja",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--alias",
        alias,
    ]
    if cfg["mode"] == "dual":
        cmd += ["--rpc", RPC, "-ts", "0.5,0.5"]
    log(f"starting: {' '.join(cmd)}")
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    CURRENT_PROC, CURRENT_LOG = proc, logf
    return proc, logf, log_path


def stop_server(proc, logf):
    global CURRENT_PROC, CURRENT_LOG
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    if logf is not None:
        logf.close()
    CURRENT_PROC, CURRENT_LOG = None, None


def stop_at_exit():
    if CURRENT_PROC is not None:
        stop_server(CURRENT_PROC, CURRENT_LOG)


atexit.register(stop_at_exit)


def _handle_signal(signum, frame):
    stop_at_exit()
    sys.exit(128 + signum)


for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    try:
        signal.signal(_sig, _handle_signal)
    except Exception:
        pass


def wait_ready(proc, timeout=LOAD_TIMEOUT):
    start = time.time()
    last_report = 0
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return False
        if health():
            return True
        elapsed = time.time() - start
        if elapsed - last_report >= 30:
            free = shutil.disk_usage(OUT).free / GIB
            log(f"waiting for server... {elapsed:.0f}s (free disk {free:.1f} GiB)")
            last_report = elapsed
        time.sleep(5)
    return False


def warmup(alias):
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": "Responda apenas: ok"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    _, err, wall = chat(payload)
    return err, wall


def run_docker_tests(code, tests_source, workdir):
    """Run model-written code against hidden tests in a locked-down container."""
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "solution.py"), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(workdir, "test_solution.py"), "w", encoding="utf-8") as f:
        f.write(tests_source)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-v",
        f"{workdir}:/w:ro",
        "-w",
        "/w",
        "python:3.12-slim",
        "python",
        "test_solution.py",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except subprocess.TimeoutExpired:
        return False, {"error": "timeout"}
    for line in reversed(r.stdout.strip().splitlines()):
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict) and "ok" in data:
            return bool(data["ok"]), data
    return False, {
        "error": (r.stderr.strip() or r.stdout.strip())[:500],
        "rc": r.returncode,
    }


def task_specs():
    specs = []
    for run_index in range(3):
        messages, meta = tasks.needle_messages(run_index)
        specs.append(
            {
                "category": "needle",
                "test": "needle",
                "run": run_index + 1,
                "messages": messages,
                "meta": meta,
                "max_tokens": 2048,
            }
        )
    for problem in tasks.CODING_TASKS:
        for run_index in range(3):
            specs.append(
                {
                    "category": "coding",
                    "test": problem["id"],
                    "run": run_index + 1,
                    "messages": tasks.coding_messages(problem),
                    "problem": problem,
                    "max_tokens": 3072,
                }
            )
    for tool_task in tasks.TOOL_TASKS:
        for run_index in range(3):
            specs.append(
                {
                    "category": "tool_call",
                    "test": tool_task["id"],
                    "run": run_index + 1,
                    "messages": tasks.tool_messages(tool_task),
                    "tool_task": tool_task,
                    "max_tokens": 2048,
                }
            )
    return specs


def run_config(model, cfg, force=False):
    alias = f"{model['key']}-{cfg['mode']}"
    stem = f"{model['key']}__{cfg['mode']}__{cfg['quant']}"
    result_path = os.path.join(RESULTS, stem + ".json")
    if force and os.path.exists(result_path):
        os.remove(result_path)

    data = {
        "model": model["label"],
        "key": model["key"],
        "mode": cfg["mode"],
        "repo": cfg["repo"],
        "quant": cfg["quant"],
        "alias": alias,
        "started": now(),
        "status": "running",
        "load_s": None,
        "warmup_error": None,
        "calls": [],
    }
    if os.path.exists(result_path):
        old = load_json(result_path, {})
        if old.get("status") == "complete":
            log(f"skipping {stem}: already complete")
            return old
        data = old
        data["status"] = "running"
    seen = {(c["category"], c["test"], c["run"]) for c in data.get("calls", [])}

    protected = {cache_dir(cfg["repo"])}
    need = int(cfg["size_gib"] * 1.15 * GIB) + 10 * GIB
    track_repo(cfg["repo"])
    if not ensure_space(need, protected):
        data["status"] = "error"
        data["error"] = "not enough disk space"
        save_json(result_path, data)
        log(f"ERROR {stem}: not enough disk space")
        return data

    start = time.time()
    proc = logf = None
    try:
        proc, logf, log_path = start_server(cfg, alias, stem)
        data["log"] = log_path
        if not wait_ready(proc):
            data["status"] = "error"
            data["error"] = "server never became ready (see log)"
            save_json(result_path, data)
            log(f"ERROR {stem}: server never became ready")
            return data
        data["load_s"] = round(time.time() - start, 1)
        log(f"{stem}: loaded in {data['load_s']}s")
        data["warmup_error"], _ = warmup(alias)
        if data["warmup_error"]:
            log(f"WARNING {stem}: warmup failed: {data['warmup_error']}")

        total = len(task_specs())
        done = 0
        for spec in task_specs():
            key = (spec["category"], spec["test"], spec["run"])
            if key in seen:
                done += 1
                continue
            payload = {
                "model": alias,
                "messages": spec["messages"],
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 20,
                "min_p": 0.0,
                "seed": 7000 + spec["run"],
                "max_tokens": spec["max_tokens"],
                "stream": False,
            }
            if spec["category"] == "tool_call":
                payload["tools"] = tasks.TOOLS
                payload["tool_choice"] = "auto"

            resp, err, wall = chat(payload)
            call = {
                "category": spec["category"],
                "test": spec["test"],
                "run": spec["run"],
                "correct": False,
                "error": err,
                "wall_s": round(wall, 3),
                "meta": spec.get("meta"),
            }
            if resp is not None:
                try:
                    message = resp["choices"][0]["message"]
                except Exception:
                    message = {}
                content = message.get("content") or ""
                reasoning = message.get("reasoning_content") or ""
                call["answer"] = content[:4000]
                call["reasoning"] = reasoning[:2000]
                call["finish_reason"] = resp.get("choices", [{}])[0].get("finish_reason")
                call["tool_calls"] = message.get("tool_calls")
                timings = resp.get("timings") or {}
                call["prompt_tokens"] = timings.get("prompt_n")
                call["completion_tokens"] = timings.get("predicted_n")
                call["prompt_ms"] = timings.get("prompt_ms")
                call["gen_ms"] = timings.get("predicted_ms")
                call["prompt_tps"] = timings.get("prompt_per_second")
                call["gen_tps"] = timings.get("predicted_per_second")
                call["cache_tokens"] = timings.get("cache_n")

                if spec["category"] == "needle":
                    call["correct"] = tasks.score_needle(message, spec["meta"]["code"])
                elif spec["category"] == "coding":
                    code = tasks.extract_code(content or reasoning)
                    call["code"] = code[:4000]
                    wd = tempfile.mkdtemp(dir=WORK)
                    try:
                        ok, detail = run_docker_tests(code, spec["problem"]["tests"], wd)
                    finally:
                        shutil.rmtree(wd, ignore_errors=True)
                    call["correct"] = ok
                    call["test_detail"] = detail
                elif spec["category"] == "tool_call":
                    ok, detail = tasks.score_tool(spec["tool_task"], message)
                    call["correct"] = ok
                    call["tool_detail"] = detail
                    call["tool_native"] = detail.get("native")

            data["calls"].append(call)
            save_json(result_path, data)
            done += 1
            speed = call.get("gen_tps")
            speed_s = f"{speed:.1f} t/s" if isinstance(speed, (int, float)) else "?"
            log(
                f"{stem}: {done}/{total} {spec['category']}/{spec['test']} "
                f"run {spec['run']} -> {'OK' if call['correct'] else 'FAIL'} ({speed_s})"
            )
            if err:
                log(f"  error: {err}")

        data["status"] = "complete"
        data["finished"] = now()
        save_json(result_path, data)
        log(f"{stem}: complete")
        return data
    finally:
        stop_server(proc, logf)


def run_smoke(model, force=False):
    """Load the model's "smoke" quant and ask two trivial questions (checks a new build works)."""
    cfg = dict(model["smoke"])
    cfg["mode"] = "single"
    alias = f"{model['key']}-smoke"
    name = f"{model['key']}-smoke"
    result_path = os.path.join(RESULTS, name + ".json")
    if force and os.path.exists(result_path):
        os.remove(result_path)
    data = {
        "model": model["label"],
        "repo": cfg["repo"],
        "quant": cfg["quant"],
        "alias": alias,
        "started": now(),
        "status": "running",
        "calls": [],
    }

    protected = {cache_dir(cfg["repo"])}
    need = int(cfg["size_gib"] * 1.15 * GIB) + 10 * GIB
    track_repo(cfg["repo"])
    if not ensure_space(need, protected):
        data["status"] = "error"
        data["error"] = "not enough disk space"
        save_json(result_path, data)
        return data

    start = time.time()
    proc = logf = None
    try:
        proc, logf, log_path = start_server(cfg, alias, name)
        data["log"] = log_path
        if not wait_ready(proc):
            data["status"] = "error"
            data["error"] = "server never became ready (see log)"
            save_json(result_path, data)
            log(f"ERROR {name}: server never became ready")
            return data
        data["load_s"] = round(time.time() - start, 1)
        log(f"{name}: loaded in {data['load_s']}s")

        prompts = [
            ("ok", "Responda apenas: ok", 32),
            (
                "codigo",
                "Escreva uma função Python chamada dobro(x) que retorna x*2. "
                "Responda apenas com o código.",
                256,
            ),
        ]
        for pname, prompt, max_tokens in prompts:
            payload = {
                "model": alias,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 20,
                "seed": 42,
                "max_tokens": max_tokens,
                "stream": False,
            }
            resp, err, wall = chat(payload)
            call = {"name": pname, "error": err, "wall_s": round(wall, 3)}
            if resp is not None:
                message = resp["choices"][0]["message"]
                call["content"] = (message.get("content") or "")[:2000]
                call["reasoning"] = (message.get("reasoning_content") or "")[:1000]
                timings = resp.get("timings") or {}
                call["prompt_tps"] = timings.get("prompt_per_second")
                call["gen_tps"] = timings.get("predicted_per_second")
                call["prompt_tokens"] = timings.get("prompt_n")
                call["completion_tokens"] = timings.get("predicted_n")
            data["calls"].append(call)
            save_json(result_path, data)
            log(f"{name}: {pname} -> {'error: ' + err if err else 'ok'}")

        data["status"] = "complete"
        data["finished"] = now()
        save_json(result_path, data)
        return data
    finally:
        stop_server(proc, logf)


def summarize():
    files = sorted(
        f
        for f in os.listdir(RESULTS)
        if f.endswith(".json") and "__" in f
    )
    rows = []
    configs = []
    for fname in files:
        data = load_json(os.path.join(RESULTS, fname), {})
        if not isinstance(data, dict):
            continue
        calls = data.get("calls", [])
        agg = {
            "model": data.get("model"),
            "key": data.get("key"),
            "mode": data.get("mode"),
            "quant": data.get("quant"),
            "status": data.get("status"),
            "load_s": data.get("load_s"),
            "error": data.get("error"),
            "categories": defaultdict(lambda: {"correct": 0, "total": 0}),
            "prompt_tps": [],
            "gen_tps": [],
            "errors": 0,
        }
        for call in calls:
            cat = call["category"]
            agg["categories"][cat]["total"] += 1
            if call.get("correct"):
                agg["categories"][cat]["correct"] += 1
            if call.get("prompt_tps"):
                agg["prompt_tps"].append(call["prompt_tps"])
            if call.get("gen_tps"):
                agg["gen_tps"].append(call["gen_tps"])
            if call.get("error"):
                agg["errors"] += 1
            rows.append(
                {
                    "model": data.get("model"),
                    "key": data.get("key"),
                    "mode": data.get("mode"),
                    "quant": data.get("quant"),
                    "category": cat,
                    "test": call.get("test"),
                    "run": call.get("run"),
                    "correct": call.get("correct"),
                    "tool_native": call.get("tool_native"),
                    "error": call.get("error"),
                    "prompt_tps": call.get("prompt_tps"),
                    "gen_tps": call.get("gen_tps"),
                    "wall_s": call.get("wall_s"),
                }
            )
        configs.append(agg)

    import csv

    csv_path = os.path.join(RESULTS, "summary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["model"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    md = ["# Suite v1 — sanity + speed", ""]
    md.append(
        "| Model | Quant | Mode | Needle | Coding | Tool call | Total | Prompt t/s | Gen t/s | Errors | Status |"
    )
    md.append("|---|---|---|---|---|---|---|---|---|---|---|")
    summary_json = []
    for agg in configs:
        cats = agg["categories"]
        total_c = sum(v["correct"] for v in cats.values())
        total_t = sum(v["total"] for v in cats.values())
        p_tps = sum(agg["prompt_tps"]) / len(agg["prompt_tps"]) if agg["prompt_tps"] else None
        g_tps = sum(agg["gen_tps"]) / len(agg["gen_tps"]) if agg["gen_tps"] else None
        md.append(
            "| {} | {} | {} | {}/{} | {}/{} | {}/{} | {}/{} | {} | {} | {} | {} |".format(
                agg["model"],
                agg["quant"],
                agg["mode"],
                cats["needle"]["correct"],
                cats["needle"]["total"],
                cats["coding"]["correct"],
                cats["coding"]["total"],
                cats["tool_call"]["correct"],
                cats["tool_call"]["total"],
                total_c,
                total_t,
                f"{p_tps:.1f}" if p_tps else "-",
                f"{g_tps:.1f}" if g_tps else "-",
                agg["errors"],
                agg["status"],
            )
        )
        summary_json.append(
            {
                **{k: v for k, v in agg.items() if k not in ("categories", "prompt_tps", "gen_tps")},
                "categories": {k: dict(v) for k, v in cats.items()},
                "prompt_tps_mean": p_tps,
                "gen_tps_mean": g_tps,
            }
        )
    md_path = os.path.join(RESULTS, "summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    save_json(os.path.join(RESULTS, "summary.json"), summary_json)
    log(f"summary: {md_path} and {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="smoke-test the model that has a 'smoke' entry")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--mode", choices=["single", "dual"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--summary", action="store_true", help="only rebuild summary.md/csv/json")
    parser.add_argument("--cleanup", action="store_true", help="delete each model's HF cache when done")
    args = parser.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(LOGS, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)

    if args.summary:
        summarize()
        return 0

    if not os.path.exists(SERVER):
        log(f"ERROR: binary not found: {SERVER} (set LLAMA_SERVER)")
        return 1

    models = load_json(MODELS_PATH, [])
    if not models:
        log(f"ERROR: {MODELS_PATH} is empty or invalid")
        return 1

    if args.smoke:
        model = next((m for m in models if m.get("smoke")), None)
        if not model:
            log("ERROR: no model has a 'smoke' entry")
            return 1
        run_smoke(model, force=args.force)
        return 0

    selected = models
    if args.model:
        selected = [m for m in models if m["key"] == args.model]
        if not selected:
            log(f"ERROR: model {args.model} not found")
            return 1
    if not args.all and not args.model:
        parser.print_help()
        return 1

    for model in selected:
        for cfg in model["configs"]:
            if args.mode and cfg["mode"] != args.mode:
                continue
            run_config(model, cfg, force=args.force)
        if args.cleanup:
            for cfg in model["configs"]:
                d = cache_dir(cfg["repo"])
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
                if d in STATE["downloaded"]:
                    STATE["downloaded"].remove(d)
            save_state()

    summarize()
    return 0


if __name__ == "__main__":
    sys.exit(main())
