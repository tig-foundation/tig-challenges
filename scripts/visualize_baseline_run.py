#!/usr/bin/env python3
"""
Visualize outputs from scripts/run_baseline_test_tig.sh (or any compatible run layout).

Reads:
  <run_root>/<challenge>/runs.csv
    columns: instance_file, time_taken, memory

Optional quality plots from evaluate_solutions CSVs:
  <run_root>/<challenge>/eval_final.csv     — solution_file, output
  <run_root>/<challenge>/eval_snapshots.csv — includes .solution.<T> paths
  plots/eval_snapshots_progress.png         — median + IQR of % gap to final (per instance)
  plots/eval_snapshots_per_instance.png     — one %gap-vs-T polyline per instance

  % gap uses the same evaluator metric as `evaluate_solutions` (makespan / distance / value).
  Baseline final metric: eval_final.csv if present; else `tig_evaluator` on
  `<instance>.solution` (no numeric suffix) under the run dir; else latest snapshot
  (gap 0 at last T).

Either pass existing eval CSV paths, or use --run-eval to invoke tig.py (slow on large runs).

Examples:
  cd /path/to/tig-challenges
  python3 scripts/visualize_baseline_run.py --run runs/baseline_testTIG_t20_i5 --challenge job_scheduling

  python3 scripts/visualize_baseline_run.py --run runs/baseline_testTIG_t20_i5 --challenge job_scheduling --run-eval --eval-workers 8

Requires: matplotlib (pip install matplotlib)
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_runs_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(dict(row))
    return rows


def _load_eval_csv(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r, None)
        if not header:
            return rows
        for row in r:
            if len(row) >= 2:
                rows.append((row[0], row[1]))
    return rows


_RE_SNAPSHOT = re.compile(r"^(?P<base>.+)\.solution\.(?P<t>\d+)$")


def _parse_eval_rows(rows: list[tuple[str, str]]):
    """Split into final-only rows (.solution) and snapshot rows (.solution.<T>)."""
    final: list[tuple[str, float | None]] = []
    snaps: list[tuple[str, float, float | None]] = []  # instance_key, t_sec, quality
    for rel, out in rows:
        rel = rel.replace("\\", "/")
        m = _RE_SNAPSHOT.match(rel)
        if m:
            q = _parse_quality(out)
            snaps.append((m.group("base"), float(m.group("t")), q))
            continue
        if rel.endswith(".solution") and ".solution." not in rel:
            q = _parse_quality(out)
            final.append((rel, q))
    return final, snaps


def _parse_quality(s: str) -> float | None:
    s = (s or "").strip()
    if s.lower() in ("error", "not_found", "unknown", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _final_solution_key(rel: str) -> str | None:
    """`job/x/0.txt.solution` -> `job/x/0.txt`; snapshot paths return None."""
    rel = rel.replace("\\", "/")
    if _RE_SNAPSHOT.match(rel):
        return None
    if rel.endswith(".solution"):
        return rel[: -len(".solution")]
    return None


def _evaluator_binary() -> Path | None:
    p = ROOT_DIR / "target" / "release" / "tig_evaluator"
    return p if p.is_file() else None


def _metric_via_evaluator(
    challenge: str,
    instance_file: Path,
    solution_file: Path,
    timeout_s: float = 120.0,
) -> float | None:
    exe = _evaluator_binary()
    if not exe:
        return None
    try:
        r = subprocess.run(
            [str(exe), challenge, str(instance_file), str(solution_file)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    for line in (r.stdout or "").strip().split("\n"):
        if line.startswith("Output:"):
            return _parse_quality(line.split(":", 1)[1].strip())
    return None


def _build_final_metric_by_instance(
    final_parsed: list[tuple[str, float | None]],
    snaps: list[tuple[str, float, float | None]],
    challenge: str,
    dataset_dir: Path,
    solutions_dir: Path,
) -> tuple[dict[str, float], bool, int]:
    """
    Map instance base (e.g. job_shop/.../0.txt) -> metric at run end.

    Order per instance: eval_final row; else evaluate `<base>.solution` on disk vs dataset
    instance `<base>`; else latest snapshot metric.

    Returns: (map, used_snapshot_proxy, n_from_disk_solution_files)
    """
    out: dict[str, float] = {}
    for rel, q in final_parsed:
        if q is None:
            continue
        key = _final_solution_key(rel)
        if key is not None:
            out[key] = float(q)

    by_base: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for base, t, q in snaps:
        if q is not None:
            by_base[base].append((t, float(q)))

    used_proxy = False
    n_from_disk = 0
    exe = _evaluator_binary()

    missing = [b for b in by_base if b not in out]

    def _try_disk(base: str) -> tuple[str, float | None]:
        sol_path = solutions_dir / f"{base}.solution"
        inst_path = dataset_dir / base
        if exe is None or not sol_path.is_file() or not inst_path.is_file():
            return base, None
        return base, _metric_via_evaluator(challenge, inst_path, sol_path)

    if missing and exe is not None:
        workers = min(16, max(len(missing), 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_try_disk, b) for b in missing]
            for fut in as_completed(futures):
                base, q_disk = fut.result()
                if q_disk is not None:
                    out[base] = q_disk
                    n_from_disk += 1

    for base, pairs in by_base.items():
        if base in out:
            continue
        _tmax, q_at_max = max(pairs, key=lambda p: p[0])
        out[base] = q_at_max
        used_proxy = True
    return out, used_proxy, n_from_disk


def _pct_gap_to_final(challenge: str, q_snap: float, q_final: float) -> float | None:
    """
    Percent gap vs final solution (0 means as good as final on the evaluator metric).
    job_scheduling / vehicle_routing: minimize metric -> 100 * (snap - final) / |final|.
    knapsack: maximize value -> 100 * (final - snap) / |final|.
    """
    denom = max(abs(q_final), 1e-12)
    if challenge in ("job_scheduling", "vehicle_routing"):
        return 100.0 * (q_snap - q_final) / denom
    if challenge == "knapsack":
        return 100.0 * (q_final - q_snap) / denom
    return None


def _snapshots_as_pct_gap(
    challenge: str,
    snaps: list[tuple[str, float, float | None]],
    final_by_inst: dict[str, float],
) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    for base, t, q in snaps:
        if q is None:
            continue
        qf = final_by_inst.get(base)
        if qf is None:
            continue
        g = _pct_gap_to_final(challenge, float(q), qf)
        if g is None:
            continue
        rows.append((base, t, g))
    return rows


def _gap_ylabel_and_note(
    challenge: str,
    used_proxy: bool,
    n_from_disk: int,
) -> tuple[str, str]:
    if challenge in ("job_scheduling", "vehicle_routing"):
        y = "% gap to final (vs best metric in run)"
        note = (
            "minimize: 100·(metric_T − metric_final) / |metric_final|; "
            "0 = same as final; >0 worse."
        )
    else:
        y = "% gap to final (vs best value in run)"
        note = (
            "maximize: 100·(value_final − value_T) / |value_final|; "
            "0 = same as final; >0 worse."
        )
    if n_from_disk:
        note += (
            " Final metric from plain `<instance>.solution` files via tig_evaluator "
            "(no eval_final row or eval_final.csv absent)."
        )
    if used_proxy:
        note += (
            " Some instances use latest snapshot as final (no usable `<instance>.solution` "
            "or tig_evaluator missing/failed)."
        )
    return y, note


def _run_evaluator(
    challenge: str,
    dataset_dir: Path,
    solutions_dir: Path,
    final_csv: Path,
    snapshots_csv: Path,
    workers: int,
) -> None:
    py = sys.executable
    base = [
        py,
        str(ROOT_DIR / "tig.py"),
        "evaluate_solutions",
        challenge,
        str(dataset_dir),
        "--solutions",
        str(solutions_dir),
        "--workers",
        str(workers),
        "--csv",
    ]
    subprocess.run(
        base + [str(final_csv)],
        cwd=str(ROOT_DIR),
        check=True,
    )
    subprocess.run(
        base + [str(snapshots_csv), "--snapshots"],
        cwd=str(ROOT_DIR),
        check=True,
    )


def _plot_runs(rows: list[dict[str, str]], out: Path) -> None:
    import matplotlib.pyplot as plt

    times = [float(r["time_taken"]) for r in rows if r.get("time_taken")]
    mem = [float(r["memory"]) for r in rows if r.get("memory")]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.suptitle("Baseline run — resource use per instance")

    if times:
        axes[0].hist(times, bins=min(30, max(5, len(times) // 3)), color="#2a6f97", edgecolor="white")
        axes[0].set_xlabel("time_taken (s)")
        axes[0].set_ylabel("count")
        axes[0].axvline(statistics.median(times), color="#e76f51", linestyle="--", label=f"median={statistics.median(times):.2g}s")
        axes[0].legend()
    else:
        axes[0].text(0.5, 0.5, "no time data", ha="center", va="center")

    if mem:
        axes[1].hist(mem, bins=min(30, max(5, len(mem) // 3)), color="#264653", edgecolor="white")
        axes[1].set_xlabel("memory")
        axes[1].set_ylabel("count")
        axes[1].axvline(statistics.median(mem), color="#e9c46a", linestyle="--", label=f"median={statistics.median(mem):.0f}")
        axes[1].legend()
    else:
        axes[1].text(0.5, 0.5, "no memory data", ha="center", va="center")

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_final_quality(final: list[tuple[str, float | None]], out: Path) -> None:
    import matplotlib.pyplot as plt

    vals = [q for _, q in final if q is not None]
    fig, ax = plt.subplots(figsize=(8, 4))
    if not vals:
        ax.text(0.5, 0.5, "No numeric quality in eval_final", ha="center", va="center")
    else:
        ax.hist(vals, bins=min(40, max(8, len(vals) // 4)), color="#52796f", edgecolor="white")
        ax.set_xlabel("quality (evaluator output)")
        ax.set_ylabel("count")
        ax.axvline(statistics.median(vals), color="#bc4749", linestyle="--", label=f"median={statistics.median(vals):.4g}")
        ax.legend()
    ax.set_title("Final solution quality distribution")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_snapshots(
    gap_rows: list[tuple[str, float, float]],
    out: Path,
    ylabel: str,
    note: str,
) -> None:
    import matplotlib.pyplot as plt

    by_t: dict[float, list[float]] = defaultdict(list)
    for _inst, t, g in gap_rows:
        by_t[t].append(g)

    ts = sorted(by_t.keys())
    medians = []
    p25 = []
    p75 = []
    counts = []
    for t in ts:
        gs = sorted(by_t[t])
        counts.append(len(gs))
        medians.append(statistics.median(gs))
        if len(gs) >= 2:
            p25.append(statistics.quantiles(gs, n=4)[0])
            p75.append(statistics.quantiles(gs, n=4)[2])
        else:
            p25.append(gs[0])
            p75.append(gs[0])

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if not ts:
        ax.text(0.5, 0.5, "No snapshot %gap data", ha="center", va="center")
    else:
        ax.axhline(0.0, color="#6c757d", linewidth=0.9, linestyle="--", zorder=1)
        ax.fill_between(ts, p25, p75, alpha=0.35, color="#457b9d", label="25–75% across instances")
        ax.plot(ts, medians, color="#1d3557", marker="o", markersize=4, label="median % gap")
        ax.set_xlabel("snapshot wall time T (s) — from filename .solution.<T>")
        ax.set_ylabel(ylabel)
        ax.set_title("% gap to final vs snapshot time (aggregated over instances)")
        ax.legend(loc="upper right")
        ax2 = ax.twinx()
        ax2.bar(
            ts,
            counts,
            width=min(5.0, (max(ts) - min(ts)) / max(len(ts), 1) * 0.4) if len(ts) > 1 else 2.0,
            alpha=0.2,
            color="gray",
            label="n instances",
        )
        ax2.set_ylabel("instances with data at T")
    fig.text(0.5, 0.02, note, ha="center", fontsize=7)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_snapshots_per_instance(
    gap_rows: list[tuple[str, float, float]],
    out: Path,
    max_instances: int | None,
    ylabel: str,
    note: str,
) -> None:
    """One line per instance: % gap to final vs snapshot time (no cross-instance aggregation)."""
    import matplotlib.pyplot as plt

    by_inst: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for base, t, g in gap_rows:
        by_inst[base].append((t, g))

    fig, ax = plt.subplots(figsize=(10, 5))
    if not by_inst:
        ax.text(0.5, 0.5, "No per-instance snapshot %gap data", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out, dpi=150)
        plt.close(fig)
        return

    total = len(by_inst)
    items = sorted(by_inst.items(), key=lambda kv: kv[0])
    capped = False
    if max_instances is not None and max_instances > 0 and len(items) > max_instances:
        items = items[:max_instances]
        capped = True

    n = len(items)
    ax.axhline(0.0, color="#6c757d", linewidth=0.9, linestyle="--", zorder=1)
    if n <= 200:
        cmap = plt.cm.plasma
        for i, (_base, series) in enumerate(items):
            series = sorted(series, key=lambda p: p[0])
            ts_, gs_ = zip(*series)
            ax.plot(
                ts_,
                gs_,
                color=cmap(i / max(n - 1, 1)),
                linewidth=0.9,
                alpha=0.82,
            )
    else:
        alpha = max(0.02, min(0.11, 45.0 / n))
        for _base, series in items:
            series = sorted(series, key=lambda p: p[0])
            ts_, gs_ = zip(*series)
            ax.plot(ts_, gs_, color="#1d3557", linewidth=0.45, alpha=alpha)

    ax.set_xlabel("snapshot wall time T (s) — from filename .solution.<T>")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.1)
    title = f"% gap to final — one line per instance (showing {n} of {total})"
    if capped:
        title += f"; capped (--per-instance-snapshot-max={max_instances})"
    ax.set_title(title)
    fig.text(0.5, 0.02, note, ha="center", fontsize=7)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(out, dpi=150)
    
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(description="Plot baseline run CSVs and optional eval outputs.")
    p.add_argument(
        "--run",
        type=Path,
        required=True,
        help="Run root directory (e.g. runs/baseline_testTIG_t20_i5)",
    )
    p.add_argument(
        "--challenge",
        choices=["knapsack", "vehicle_routing", "job_scheduling"],
        required=True,
    )
    p.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset dir passed to evaluate_solutions (default: datasets/<challenge>/test/TIG)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for PNG figures (default: <run>/<challenge>/plots)",
    )
    p.add_argument("--final-csv", type=Path, default=None, help="Precomputed eval CSV (final solutions only)")
    p.add_argument("--snapshots-csv", type=Path, default=None, help="Precomputed eval CSV (includes .solution.<T>)")
    p.add_argument(
        "--run-eval",
        action="store_true",
        help="Run tig.py evaluate_solutions (final + snapshots); writes eval CSVs under challenge dir",
    )
    p.add_argument("--eval-workers", type=int, default=8)
    p.add_argument(
        "--per-instance-snapshot-max",
        type=int,
        default=None,
        metavar="N",
        help="Draw at most N instance trajectories (sorted by solution path); default: all",
    )
    args = p.parse_args()

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("Install matplotlib:  pip install matplotlib", file=sys.stderr)
        return 1

    run_root = args.run.resolve()
    ch_dir = run_root / args.challenge
    out_dir = (args.out_dir or (ch_dir / "plots")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_dir = args.dataset or (ROOT_DIR / "datasets" / args.challenge / "test" / "TIG")
    if not dataset_dir.is_dir():
        print(f"Warning: dataset dir not found: {dataset_dir}", file=sys.stderr)

    runs_path = ch_dir / "runs.csv"
    if not runs_path.is_file():
        print(f"Missing {runs_path}", file=sys.stderr)
        return 1

    final_csv = (args.final_csv or (ch_dir / "eval_final.csv")).resolve()
    snaps_csv = (args.snapshots_csv or (ch_dir / "eval_snapshots.csv")).resolve()

    if args.run_eval:
        if not dataset_dir.is_dir():
            print(f"--run-eval needs a valid --dataset (missing {dataset_dir})", file=sys.stderr)
            return 1
        print("Running tig.py evaluate_solutions (final + snapshots)…")
        _run_evaluator(
            args.challenge,
            dataset_dir,
            ch_dir,
            final_csv,
            snaps_csv,
            args.eval_workers,
        )

    rows = _load_runs_csv(runs_path)
    print(f"Loaded {len(rows)} rows from {runs_path}")
    times = [float(r["time_taken"]) for r in rows if r.get("time_taken")]
    mem = [float(r["memory"]) for r in rows if r.get("memory")]
    if times:
        print(f"  time_taken: min={min(times):.3g}s max={max(times):.3g}s median={statistics.median(times):.3g}s")
    if mem:
        print(f"  memory: min={min(mem):.0f} max={max(mem):.0f} median={statistics.median(mem):.0f}")

    p_runs = out_dir / "runs_resources.png"
    _plot_runs(rows, p_runs)
    print(f"Wrote {p_runs}")

    if final_csv.is_file():
        eval_rows = _load_eval_csv(final_csv)
        final_parsed, _ = _parse_eval_rows(eval_rows)
        numeric = [q for _, q in final_parsed if q is not None]
        print(f"Loaded {len(final_parsed)} final eval rows from {final_csv} ({len(numeric)} numeric)")
        p_fin = out_dir / "eval_final_quality.png"
        _plot_final_quality(final_parsed, p_fin)
        print(f"Wrote {p_fin}")
    else:
        print(f"No {final_csv} — skip final quality plot (use --run-eval or evaluate_solutions manually)")

    if snaps_csv.is_file():
        eval_rows = _load_eval_csv(snaps_csv)
        _, snaps = _parse_eval_rows(eval_rows)
        nq = sum(1 for *_, q in snaps if q is not None)
        print(f"Loaded {len(snaps)} snapshot eval rows from {snaps_csv} ({nq} numeric)")

        final_for_gap: list[tuple[str, float | None]] = []
        if final_csv.is_file():
            fr = _load_eval_csv(final_csv)
            final_for_gap, _ = _parse_eval_rows(fr)
        if not _evaluator_binary():
            print(
                "  Note: `target/release/tig_evaluator` not found — "
                "build with: cargo build -r --bin tig_evaluator --features evaluator",
                file=sys.stderr,
            )
        final_by_inst, used_proxy, n_disk = _build_final_metric_by_instance(
            final_for_gap,
            snaps,
            args.challenge,
            dataset_dir,
            ch_dir,
        )
        gap_rows = _snapshots_as_pct_gap(args.challenge, snaps, final_by_inst)
        print(
            f"  % gap: {len(final_by_inst)} instance baselines, {len(gap_rows)} (instance,T) points"
            + (f"; {n_disk} baselines from `<instance>.solution` on disk" if n_disk else "")
            + ("; some from latest snapshot (fallback)" if used_proxy else "")
        )

        ylabel, note = _gap_ylabel_and_note(args.challenge, used_proxy, n_disk)
        p_sn = out_dir / "eval_snapshots_progress.png"
        _plot_snapshots(gap_rows, p_sn, ylabel, note)
        print(f"Wrote {p_sn}")
        p_sn_pi = out_dir / "eval_snapshots_per_instance.png"
        _plot_snapshots_per_instance(gap_rows, p_sn_pi, args.per_instance_snapshot_max, ylabel, note)
        print(f"Wrote {p_sn_pi}")
    else:
        print(f"No {snaps_csv} — skip snapshot progress plot")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
