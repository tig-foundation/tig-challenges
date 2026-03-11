#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import os
import glob
import subprocess
import tempfile
import argparse
import time
import json


try:
    subprocess.run(["cargo", "version"], check=True)
except Exception as e:
    print(f"Error: Cargo is not installed")
    print("Please install Cargo: https://doc.rust-lang.org/cargo/getting-started/installation.html")
    exit(1)


def generate_datasets(challenge: str):
    if not os.path.exists("target/release/tig_generator"):
        print("Building tig_generator")
        subprocess.run(["cargo", "build", "-r", "--bin", "tig_generator", "--features", "generator"], check=True)
    with open("datasets_config.json", "r") as f:
        datasets_config = json.load(f)[challenge]
    for track_id, config in datasets_config.items():
        for split, n in config.items():
            start = time.time()
            print(f"Generating {challenge}/{track_id} instances: {split}, {n}")
            subprocess.run([
                "./target/release/tig_generator",
                challenge,
                track_id,
                "--seed", split,
                "-n", str(n),
                "-o", f"datasets/{challenge}/{split}/{track_id}",
            ], check=True)
            print(f"Time taken: {time.time() - start:.2f} seconds")

def run_test(
    challenge: str,
    instance_file: str,
    hyperparameters: str = None,
    timeout: int = 60,
    debug: bool = False,
) -> tuple:
    try:
        quality, time, memory = None, None, None
        with tempfile.NamedTemporaryFile() as solution_file:
            cmd = [
                "/usr/bin/time",
                "-f", "Memory: %M",
                "target/release/tig_solver",
                challenge,
                instance_file,
                solution_file.name,
            ]
            if hyperparameters:
                cmd += ["--hyperparameters", hyperparameters]
            if debug:
                print("Running command:", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Time:"):
                    time = float(line.split(":")[1].strip())
            for line in result.stderr.strip().split("\n"):
                if line.startswith("Memory:"):
                    memory = int(line.split(":")[1].strip())

            cmd = [
                "target/release/tig_evaluator",
                challenge,
                instance_file,
                solution_file.name,
            ]
            if debug:
                print("Running command:", " ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise ValueError(f"Evaluation failed: {result.stderr.strip()}")
            for line in result.stdout.strip().split("\n"):
                if line.startswith("Quality:"):
                    quality = line.split(":")[1].strip()
            if debug:
                print(f"Instance: {instance_file}, Quality: {quality}, Time: {time}, Memory: {memory}KB")
        return quality, time, memory
    except Exception as e:
        print(f"Instance: {instance_file}, Error: {e}")
        return None, None, None

def test_algorithm(
    challenge: str,
    dataset_dir: str,
    num_workers: int = 1,
    hyperparameters: str = None,
    timeout: int = 60,
    debug: bool = False,
) -> list:
    if not os.path.exists("target/release/tig_evaluator"):
        print("Building tig_evaluator")
        subprocess.run(["cargo", "build", "-r", "--bin", "tig_evaluator", "--features", "evaluator"], check=True)
    print("Building tig_solver")
    subprocess.run(["cargo", "build", "-r", "--bin", "tig_solver", "--features", f"solver,{challenge}"], check=True)
    
    pool = ThreadPoolExecutor(max_workers=num_workers)
    start = time.time()

    instances = glob.glob(f"{dataset_dir}/*.txt", recursive=True)
    
    results = list(pool.map(
        lambda instance: run_test(challenge, instance, hyperparameters, timeout, debug),
        instances
    ))
    
    # Calculate final stats
    solved = [r for r in results if r[0] is not None]
    num_solved = len(solved)
    elapsed = time.time() - start
    avg_quality = int(sum(float(r[0]) for r in solved) / num_solved) if num_solved > 0 else 0
    
    print(f"#solved: {num_solved}, elapsed: {elapsed:.2f}s, avg_quality: {avg_quality:,}")
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TIG Challenges CLI Tool")    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # generate_datasets subcommand
    generate_parser = subparsers.add_parser("generate_datasets", help="Generate datasets")
    generate_parser.add_argument("challenge", choices=["knapsack", "vehicle_routing", "job_scheduling"], help="Challenge name")
    # test_algorithm subcommand
    test_parser = subparsers.add_parser("test_algorithm", help="Test the algorithm")
    test_parser.add_argument("challenge", choices=["knapsack", "vehicle_routing", "job_scheduling"], help="Challenge name")
    test_parser.add_argument("dataset_dir", help="Dataset directory")
    test_parser.add_argument("--workers", type=int, default=1, help="Number of worker threads")
    test_parser.add_argument("--hyperparameters", help="Hyperparameters string")
    test_parser.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    test_parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    try:
        if args.command == "generate_datasets":
            generate_datasets(args.challenge)
        elif args.command == "test_algorithm":
            test_algorithm(
                args.challenge,
                args.dataset_dir,
                args.workers,
                args.hyperparameters,
                args.timeout,
                args.debug
            )
        else:
            parser.print_help()
    except Exception as e:
        print(f"Error: {e}")