#!/usr/bin/env python3

import argparse
import csv
import glob
import json
import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TIG_SOLVER = os.path.join(ROOT_DIR, "target", "release", "tig_solver")
TIG_EVALUATOR = os.path.join(ROOT_DIR, "target", "release", "tig_evaluator")
TIG_GENERATOR = os.path.join(ROOT_DIR, "target", "release", "tig_generator")

logger = logging.getLogger("tig")


def setup_logging(log_level: str) -> None:
    level = getattr(logging, (log_level or "").upper(), None)
    if not isinstance(level, int):
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def require_cargo() -> None:
    try:
        result = subprocess.run(["cargo", "version"], check=True, capture_output=True, text=True)
        logger.debug("Cargo detected: %s", (result.stdout or result.stderr or "").strip())
    except Exception:
        logger.error("Cargo is not installed or not on PATH.")
        logger.error("Install Cargo: https://doc.rust-lang.org/cargo/getting-started/installation.html")
        raise SystemExit(1)


def generate_dataset(challenge: str, config_path: str, out_dir: str):
    if not os.path.exists(TIG_GENERATOR):
        logger.info("Building `tig_generator` (release)")
        subprocess.run(
            ["cargo", "build", "-r", "--bin", "tig_generator", "--features", "generator"],
            check=True,
            cwd=ROOT_DIR,
        )
    with open(config_path, "r") as f:
        config = json.load(f)
    seed = config.pop("seed")
    if out_dir is None:
        out_dir = os.path.join("datasets", challenge)
    for name, x in config.items():
        start = time.time()
        track = x["track"]
        n = x["n_instances"]
        logger.info("Generating %s/%s instances (seed=%s, n=%s)", challenge, name, seed, n)
        subprocess.run([
            TIG_GENERATOR,
            challenge,
            json.dumps(track, separators=(",", ":"), sort_keys=True),
            "--seed", seed,
            "-n", str(n),
            "-o", os.path.join(out_dir, name),
        ], check=True)
        logger.info("Generated in %.2fs", time.time() - start)


def run_algorithm_on_instance(
    challenge: str,
    dataset_dir: str,
    instance_file: str,
    hyperparameters: str = None,
    timeout: int = 60,
    interval: int = None,
    out_dir: str = None,
    snapshot_times: list = None,
) -> tuple:
    try:
        time_taken, memory = None, None
        if out_dir:
            os.makedirs(
                os.path.join(out_dir, os.path.dirname(instance_file)),
                exist_ok=True
            )
            solution_path = os.path.join(out_dir, f"{instance_file}.solution")
        else:
            solution_path = os.path.join(dataset_dir, f"{instance_file}.solution")
        logger.info("Solving %s", instance_file)

        cmd = [
            "/usr/bin/time",
            "-f", "Time: %e Memory: %M",
            "timeout", str(timeout),
            TIG_SOLVER,
            challenge,
            os.path.join(dataset_dir, instance_file),
            solution_path,
        ]
        if hyperparameters:
            cmd += ["--hyperparameters", hyperparameters]
        logger.debug("Solver command: %s", " ".join(cmd))

        snapshot_times_sorted = None
        if snapshot_times:
            snapshot_times_sorted = sorted(
                {int(t) for t in snapshot_times if int(t) > 0}
            )
        snapshot_idx = 0
        snapshot_count = 0
        start_time = time.time()
        if snapshot_times_sorted:
            next_snapshot_at = None
        elif interval:
            next_snapshot_at = start_time + interval
        else:
            next_snapshot_at = None

        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
        stderr = None
        while True:
            now = time.time()
            if snapshot_times_sorted:
                while (
                    snapshot_idx < len(snapshot_times_sorted)
                    and now >= start_time + snapshot_times_sorted[snapshot_idx]
                ):
                    label = snapshot_times_sorted[snapshot_idx]
                    snapshot_path = f"{solution_path}.{label}"
                    if os.path.exists(solution_path):
                        shutil.copy2(solution_path, snapshot_path)
                        logger.debug("Snapshot %s -> %s", solution_path, snapshot_path)
                    else:
                        logger.debug(
                            "Snapshot skipped; solution does not exist yet: %s",
                            solution_path,
                        )
                    snapshot_idx += 1
            elif next_snapshot_at is not None and now >= next_snapshot_at:
                snapshot_count += 1
                snapshot_path = f"{solution_path}.{snapshot_count * interval}"
                if os.path.exists(solution_path):
                    shutil.copy2(solution_path, snapshot_path)
                    logger.debug("Snapshot %s -> %s", solution_path, snapshot_path)
                else:
                    logger.debug("Snapshot skipped; solution does not exist yet: %s", solution_path)
                next_snapshot_at += interval

            try:
                _, stderr = proc.communicate(timeout=0.1)
                end_now = time.time()
                if snapshot_times_sorted:
                    while snapshot_idx < len(snapshot_times_sorted):
                        label = snapshot_times_sorted[snapshot_idx]
                        if label > timeout:
                            snapshot_idx += 1
                            continue
                        snapshot_path = f"{solution_path}.{label}"
                        if os.path.exists(solution_path):
                            shutil.copy2(solution_path, snapshot_path)
                            logger.debug(
                                "Post-exit snapshot %s -> %s", solution_path, snapshot_path
                            )
                        snapshot_idx += 1
                elif interval and next_snapshot_at is not None:
                    cap = min(end_now - start_time, float(timeout))
                    while (snapshot_count + 1) * interval <= cap:
                        snapshot_count += 1
                        snapshot_path = f"{solution_path}.{snapshot_count * interval}"
                        if os.path.exists(solution_path):
                            shutil.copy2(solution_path, snapshot_path)
                            logger.debug(
                                "Post-exit snapshot %s -> %s", solution_path, snapshot_path
                            )
                break
            except subprocess.TimeoutExpired:
                pass

        for line in (stderr or "").strip().split("\n"):
            if line.startswith("Time:"):
                parts = line.split(" ")
                time_taken = float(parts[1].strip())
                memory = int(parts[3].strip())

        logger.info(
            "Solved %s | time=%.3fs memory=%sKB",
            instance_file,
            time_taken if time_taken is not None else -1,
            memory,
        )
        return instance_file, time_taken, memory
    except Exception as e:
        logger.exception("Unexpected error: %s (%s)", instance_file, e)
        return instance_file, None, None


def run_algorithm(
    challenge: str,
    dataset_dir: str,
    num_workers: int = 1,
    hyperparameters: str = None,
    timeout: int = 60,
    interval: int = None,
    out_dir: str = None,
    baseline: bool = False,
    csv_path: str = None,
    snapshot_times: list = None,
) -> list:
    if baseline:
        logger.info("Building `tig_solver` (release, features=solver,baseline,%s)", challenge)
        subprocess.run(
            ["cargo", "build", "-r", "--bin", "tig_solver", "--features", f"solver,baseline,{challenge}"],
            check=True,
            cwd=ROOT_DIR,
        )
    else:
        logger.info("Building `tig_solver` (release, features=solver,%s)", challenge)
        subprocess.run(
            ["cargo", "build", "-r", "--bin", "tig_solver", "--features", f"solver,{challenge}"],
            check=True,
            cwd=ROOT_DIR,
        )

    instances = [
        os.path.relpath(path, dataset_dir)
        for path in glob.glob(f"{dataset_dir}/**/*.txt", recursive=True)
    ]
    logger.info(
        "Running %s instances (challenge=%s workers=%s timeout=%ss interval=%s snapshot_times=%s out=%s)",
        len(instances),
        challenge,
        num_workers,
        timeout,
        interval,
        snapshot_times,
        out_dir,
    )
    logger.debug("Dataset dir: %s", dataset_dir)

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        results = list(pool.map(
            lambda instance: run_algorithm_on_instance(
                challenge,
                dataset_dir,
                instance,
                hyperparameters,
                timeout,
                interval,
                out_dir,
                snapshot_times,
            ),
            instances,
        ))

    if csv_path:
        with open(csv_path, "w") as f:
            writer = csv.writer(f)
            writer.writerow(["instance_file", "time_taken", "memory"])
            for result in results:
                writer.writerow(result)

    return results


def evaluate_solution(
    challenge: str,
    dataset_dir: str,
    solutions_dir: str,
    instance_file: str,
    snapshots: bool = False,
) -> tuple:
    logger.info("Evaluating solutions for %s", instance_file)
    if solutions_dir is None:
        solutions_dir = dataset_dir

    def _glob_final():
        paths = glob.glob(os.path.join(solutions_dir, f"{instance_file}.solution"))
        if not paths:
            base = os.path.basename(instance_file)
            if base != instance_file:
                paths = glob.glob(os.path.join(solutions_dir, f"{base}.solution"))
        return paths

    def _glob_snapshots():
        paths = sorted(glob.glob(os.path.join(solutions_dir, f"{instance_file}.solution.*")))
        if not paths:
            base = os.path.basename(instance_file)
            if base != instance_file:
                paths = sorted(glob.glob(os.path.join(solutions_dir, f"{base}.solution.*")))
        return paths

    if snapshots:
        final_paths = _glob_final()
        snapshot_paths = _glob_snapshots()
        paths = list(final_paths) + snapshot_paths
        solutions = [os.path.relpath(path, solutions_dir) for path in paths]
    else:
        solutions = [
            os.path.relpath(path, solutions_dir)
            for path in _glob_final()
        ]
    if len(solutions) == 0:
        logger.info("No solutions found for %s", instance_file)
        return [(f"{instance_file}.solution", "not_found")]
    results = []
    for s in solutions:
        solution_file = os.path.join(solutions_dir, s)
        cmd = [
            TIG_EVALUATOR,
            challenge,
            os.path.join(dataset_dir, instance_file),
            solution_file,
        ]
        logger.debug("Evaluator command: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err_tail = (result.stderr or "").strip()
            out_tail = (result.stdout or "").strip()
            detail = err_tail or out_tail or "(no message from evaluator)"
            logger.warning(
                "Evaluator failed | instance=%s solution=%s exit=%s msg=%s",
                os.path.join(dataset_dir, instance_file),
                solution_file,
                result.returncode,
                detail,
            )
            logger.debug(
                "Evaluator full stdout=%r stderr=%r",
                result.stdout,
                result.stderr,
            )
            output = "error"
        else:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Output:"):
                    output = line.split(":")[1].strip()
                    break
            else:
                output = "unknown"
            logger.info("Evaluated %s | output=%s", solution_file, output)
        results.append((s, output))
    return results


def evaluate_solutions(
    challenge: str,
    dataset_dir: str,
    solutions_dir: str = None,
    snapshots: bool = False,
    num_workers: int = 1,
    csv_path: str = None,
) -> list:
    if not os.path.exists(TIG_EVALUATOR):
        logger.info("Building `tig_evaluator` (release)")
        subprocess.run(
            ["cargo", "build", "-r", "--bin", "tig_evaluator", "--features", "evaluator"],
            check=True,
            cwd=ROOT_DIR,
        )
    instances = [
        os.path.relpath(path, dataset_dir)
        for path in glob.glob(f"{dataset_dir}/**/*.txt", recursive=True)
    ]
    logger.info(
        "Evaluating solutions for %s instances (challenge=%s workers=%s csv=%s)",
        len(instances),
        challenge,
        num_workers,
        csv_path,
    )

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        results = []
        for batch in pool.map(
            lambda instance: evaluate_solution(challenge, dataset_dir, solutions_dir, instance, snapshots),
            instances,
        ):
            results.extend(batch)

    if csv_path:
        with open(csv_path, "w") as f:
            writer = csv.writer(f)
            writer.writerow(["solution_file", "output"])
            for result in results:
                writer.writerow(result)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TIG Challenges CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"], help="Logging level")

    generate_parser = subparsers.add_parser("generate_dataset", help="Generate datasets")
    generate_parser.add_argument("challenge", choices=["knapsack", "vehicle_routing", "job_scheduling"], help="Challenge name")
    generate_parser.add_argument("config", help="Dataset config file path")
    generate_parser.add_argument("--out", default=None, help="Output directory for dataset (defaults to datasets/<challenge>)")

    run_parser = subparsers.add_parser("run_algorithm", help="Run the algorithm on datasets")
    run_parser.add_argument("challenge", choices=["knapsack", "vehicle_routing", "job_scheduling"], help="Challenge name")
    run_parser.add_argument(
        "dataset_dir",
        help="Dataset directory (recursively finds .txt instance files)",
    )
    run_parser.add_argument("--workers", type=int, default=1, help="Number of worker threads")
    run_parser.add_argument("--hyperparameters", help="Hyperparameters string")
    run_parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    run_parser.add_argument("--interval", type=int, default=None, help="Interval (seconds) to snapshot the latest solution")
    run_parser.add_argument(
        "--snapshot-times",
        default=None,
        metavar="T1,T2,...",
        help="Comma-separated elapsed seconds at which to snapshot; files are .solution.<T>. "
        "If set, overrides --interval.",
    )
    run_parser.add_argument("--out", default=None, help="Output directory for saving solutions (defaults to dataset directory)")
    run_parser.add_argument("--baseline", action="store_true", help="Run the baseline algorithm")
    run_parser.add_argument("--csv", default=None, help="CSV file path for saving results")

    evaluate_parser = subparsers.add_parser("evaluate_solutions", help="Evaluate solutions")
    evaluate_parser.add_argument("challenge", choices=["knapsack", "vehicle_routing", "job_scheduling"], help="Challenge name")
    evaluate_parser.add_argument(
        "dataset_dir",
        help="Dataset directory (recursively finds .txt instance files)",
    )
    evaluate_parser.add_argument("--solutions", default=None, help="Solutions directory (defaults to dataset directory. Search for <instance>.solution* files.)")
    evaluate_parser.add_argument(
        "--snapshots",
        action="store_true",
        help="Evaluate the final <instance>.solution plus all <instance>.solution.* snapshot files",
    )
    evaluate_parser.add_argument("--workers", type=int, default=1, help="Number of worker threads")
    evaluate_parser.add_argument("--csv", default=None, help="CSV file path for saving results")

    args = parser.parse_args()
    setup_logging(args.log_level)
    require_cargo()

    try:
        if args.command == "generate_dataset":
            logger.info("\n\tcommand=generate_dataset\n\tchallenge=%s\n\tconfig=%s\n\tout=%s", args.challenge, args.config, args.out)
            generate_dataset(args.challenge, args.config, args.out)
        elif args.command == "run_algorithm":
            snapshot_times = None
            if args.snapshot_times:
                snapshot_times = [
                    int(x.strip())
                    for x in args.snapshot_times.split(",")
                    if x.strip()
                ]
            logger.info(
                "\n\tcommand=run_algorithm\n\tchallenge=%s\n\tdataset_dir=%s\n\tworkers=%s\n\thyperparameters=%s\n\ttimeout=%s\n\tinterval=%s\n\tsnapshot_times=%s\n\tout=%s\n\tbaseline=%s\n\tcsv=%s",
                args.challenge,
                args.dataset_dir,
                args.workers,
                args.hyperparameters,
                args.timeout,
                args.interval,
                snapshot_times,
                args.out,
                args.baseline,
                args.csv,
            )
            run_algorithm(
                args.challenge,
                args.dataset_dir,
                args.workers,
                args.hyperparameters,
                args.timeout,
                args.interval,
                args.out,
                args.baseline,
                args.csv,
                snapshot_times,
            )
        elif args.command == "evaluate_solutions":
            logger.info("\n\tcommand=evaluate_solutions\n\tchallenge=%s\n\tdataset_dir=%s\n\tsolutions=%s\n\tworkers=%s\n\tcsv=%s", args.challenge, args.dataset_dir, args.solutions, args.workers, args.csv)
            evaluate_solutions(
                args.challenge,
                args.dataset_dir,
                args.solutions,
                args.snapshots,
                args.workers,
                args.csv,
            )
        else:
            parser.print_help()
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        raise SystemExit(1)
