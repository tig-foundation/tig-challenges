#!/usr/bin/env bash
# Run the built-in baseline solver on all instances under datasets/<challenge>/test/TIG
# for knapsack, vehicle_routing, and job_scheduling. Writes solutions and periodic
# snapshots under runs/ (see README).

# Environment overrides:
#   TIMEOUT          Per-instance cap in seconds 
#   INTERVAL         Used in RUN_ROOT naming only (default 5).
#   SNAPSHOT_TIMES   Comma-separated elapsed seconds for snapshots on all three challenges
#                    (.solution.<T>). Default: 2,5,10,...,1800.
#                    If unset, falls back to VR_SNAPSHOT_TIMES when set (backward compatibility).
#   WORKERS          Parallel instances (default 8).
#   RUN_ROOT         Output root directory (default runs/baseline_testTIG_t${TIMEOUT}_i${INTERVAL}).
#
# Optional follow-up (not run here; can be very expensive for many snapshots):
#   python3 tig.py evaluate_solutions <challenge> datasets/<challenge>/test/TIG \
#     --solutions "$RUN_ROOT/<challenge>" --snapshots --csv eval_snapshots.csv

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMEOUT="${TIMEOUT:-20}"
INTERVAL="${INTERVAL:-5}"
_DEFAULT_SNAPSHOT_TIMES="2,5,10,20,30,60,90,120,300,600,900,1200,1500,1800"
SNAPSHOT_TIMES="${SNAPSHOT_TIMES:-${VR_SNAPSHOT_TIMES:-$_DEFAULT_SNAPSHOT_TIMES}}"
WORKERS="${WORKERS:-8}"
RUN_ROOT="${RUN_ROOT:-$ROOT_DIR/runs/baseline_testTIG_t${TIMEOUT}_i${INTERVAL}}"

mkdir -p "$RUN_ROOT"

{
  printf '{\n'
  printf '  "started_at": "%s",\n' "$(date -Iseconds)"
  printf '  "timeout_seconds": %s,\n' "$TIMEOUT"
  printf '  "snapshot_interval_seconds": %s,\n' "$INTERVAL"
  printf '  "snapshot_times_seconds": "%s",\n' "$SNAPSHOT_TIMES"
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

  algo_args=()
  case "$challenge" in
    job_scheduling)
      algo_args=(--hyperparameters '{"run_forever": true}')
      ;;
    vehicle_routing)
      algo_args=(--hyperparameters '{"exploration_level": 6}')
      ;;
    knapsack) ;;
  esac

  python3 tig.py run_algorithm "$challenge" "$dataset_dir" \
    --baseline \
    "${algo_args[@]}" \
    --timeout "$TIMEOUT" \
    --snapshot-times "$SNAPSHOT_TIMES" \
    --workers "$WORKERS" \
    --out "$out_dir" \
    --csv "$out_dir/runs.csv"
done
