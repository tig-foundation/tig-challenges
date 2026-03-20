#!/usr/bin/env bash
# Run the built-in baseline solver on all instances under datasets/<challenge>/test/TIG
# for knapsack, vehicle_routing, and job_scheduling. Writes solutions and periodic
# snapshots under runs/ (see README).
#
# Environment overrides:
#   TIMEOUT   Per-instance cap in seconds (default 1800 = 30m). Not wall-clock for the whole challenge.
#   INTERVAL  Snapshot period in seconds (default 300 = 5m). Snapshots are .solution.<k> with k = n*INTERVAL.
#   WORKERS   Parallel instances (default 8).
#   RUN_ROOT  Output root directory (default runs/baseline_testTIG_t${TIMEOUT}_i${INTERVAL} under repo root).
#
# Optional follow-up (not run here; can be very expensive for many snapshots):
#   python3 tig.py evaluate_solutions <challenge> datasets/<challenge>/test/TIG \
#     --solutions "$RUN_ROOT/<challenge>" --snapshots --csv eval_snapshots.csv

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMEOUT="${TIMEOUT:-1800}"
INTERVAL="${INTERVAL:-300}"
WORKERS="${WORKERS:-8}"
RUN_ROOT="${RUN_ROOT:-$ROOT_DIR/runs/baseline_testTIG_t${TIMEOUT}_i${INTERVAL}}"

mkdir -p "$RUN_ROOT"

{
  printf '{\n'
  printf '  "started_at": "%s",\n' "$(date -Iseconds)"
  printf '  "timeout_seconds": %s,\n' "$TIMEOUT"
  printf '  "snapshot_interval_seconds": %s,\n' "$INTERVAL"
  printf '  "workers": %s,\n' "$WORKERS"
  printf '  "dataset_dirs": {\n'
  printf '    "knapsack": "datasets/knapsack/test/TIG",\n'
  printf '    "vehicle_routing": "datasets/vehicle_routing/test/TIG",\n'
  printf '    "job_scheduling": "datasets/job_scheduling/test/TIG"\n'
  printf '  }\n'
  printf '}\n'
} >"$RUN_ROOT/manifest.json"

for challenge in knapsack vehicle_routing job_scheduling; do
  dataset_dir="datasets/${challenge}/test/TIG"
  out_dir="$RUN_ROOT/$challenge"
  mkdir -p "$out_dir"
  python3 tig.py run_algorithm "$challenge" "$dataset_dir" \
    --baseline \
    --timeout "$TIMEOUT" \
    --interval "$INTERVAL" \
    --workers "$WORKERS" \
    --out "$out_dir" \
    --csv "$out_dir/runs.csv"
done
