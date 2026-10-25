#!/bin/bash
# Full v2 queue (resumable): every config in models.json, then the best single config
# re-run on two boards with the same quant. Meant to run as a systemd --user service with
# Restart=on-failure, so an OOM kill restarts it and the harness resumes where it stopped.
set -o pipefail
cd "$(dirname "$0")"
OUT="${BENCH_OUT:-$(cd .. && pwd)/bc250}"
LOG="$OUT/bench-v2.log"
mkdir -p "$OUT"
python3 run_bench_v2.py --all --runs 3 --tag v2 2>&1 | tee -a "$LOG" || exit 1
python3 run_bench_v2.py --best-single-dual --runs 3 --tag v2 2>&1 | tee -a "$LOG" || exit 1
echo BENCH_V2_DONE >> "$LOG"
