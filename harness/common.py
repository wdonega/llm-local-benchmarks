#!/usr/bin/env python3
"""Shared helpers: config, server lifecycle, chat calls, disk management, Docker sandbox.

Configuration comes from environment variables (see README):
  LLAMA_SERVER, BENCH_RPC, BENCH_PORT, BENCH_MODELS, BENCH_OUT, HF_HUB_CACHE
"""

import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(BASE)

SERVER = os.environ.get("LLAMA_SERVER", os.path.expanduser("~/llama.cpp/build/bin/llama-server"))
HF_CACHE = os.path.expanduser(os.environ.get("HF_HUB_CACHE", "~/.cache/huggingface/hub"))
PORT = int(os.environ.get("BENCH_PORT", "8081"))
RPC = os.environ.get("BENCH_RPC", "llm4.lab:50052")
OUT = os.path.abspath(os.environ.get("BENCH_OUT", os.path.join(REPO, "bc250")))
MODELS_PATH = os.path.abspath(os.environ.get("BENCH_MODELS", os.path.join(OUT, "models.json")))
CALL_TIMEOUT = 300
LOAD_TIMEOUT = 3600
LOGS = os.path.join(OUT, "logs")
WORK = os.path.join(OUT, "work")
STATE_PATH = os.path.join(OUT, "state.json")
GIB = 2**30

API_BASE = None  # set while a "remote" config runs: an already-running OpenAI-compatible server
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
    if API_BASE:
        return API_BASE.rstrip("/").removesuffix("/v1") + path
    return f"http://127.0.0.1:{PORT}{path}"


def health():
    r = subprocess.run(
        ["curl", "-sf", "--max-time", "5", call_url("/v1/models" if API_BASE else "/health")],
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





