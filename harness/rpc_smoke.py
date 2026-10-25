#!/usr/bin/env python3
"""RPC smoke test: load a small model split across the head and the RPC worker, ask one question.

Usage: python3 rpc_smoke.py [repo:quant]     (default: ornith-ai/Ornith-1.5-9B-GGUF:Q6_K)
Run this before any dual-board benchmark to confirm the worker ($BENCH_RPC) is reachable
and speaks the same RPC protocol version as the head's llama.cpp build.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_bench  # noqa: E402


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else "ornith-ai/Ornith-1.5-9B-GGUF:Q6_K"
    repo, quant = spec.rsplit(":", 1)
    cfg = {"repo": repo, "quant": quant, "mode": "dual"}
    proc = logf = None
    try:
        proc, logf, log_path = run_bench.start_server(cfg, "rpc-smoke", "rpc-smoke")
        if not run_bench.wait_ready(proc, timeout=900):
            print(f"RPC smoke: server never became ready (see {log_path})", flush=True)
            return 1
        payload = {
            "model": "rpc-smoke",
            "messages": [{"role": "user", "content": "Responda apenas: ok"}],
            "max_tokens": 32,
            "temperature": 0,
            "stream": False,
        }
        resp, err, wall = run_bench.chat(payload, timeout=120)
        if err or not resp:
            print(f"RPC smoke: call failed: {err}", flush=True)
            return 1
        msg = resp["choices"][0]["message"]
        print(
            "RPC smoke OK: "
            f"content={msg.get('content')!r} "
            f"reasoning={str(msg.get('reasoning_content'))[:100]!r} "
            f"wall={wall:.1f}s",
            flush=True,
        )
        return 0
    finally:
        run_bench.stop_server(proc, logf)


if __name__ == "__main__":
    sys.exit(main())
