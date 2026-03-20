#!/usr/bin/env python3
"""Download JSP and FJSP benchmark instances from:
  https://github.com/ScheduleOpt/benchmarks/tree/main

Two problem families are covered:

1. Flexible Job Shop (FJSP) — jobshop/instances/
   Files are already in Brandimarte .fjs format (compatible with
   Challenge::from_txt). These datasets are excluded:
     - BFFMOR2012: uses a DAG precedence-graph format that is incompatible
       with the Brandimarte parser.

2. Job Shop (JSP) — jobshop/instances/
   Files use a simpler format:
       <num_jobs> <num_machines>
       <machine_0> <duration_0>  <machine_1> <duration_1>  ...  (per job)
   where machine IDs are 0-based.  The script converts these to Brandimarte
   format (each operation has exactly one eligible machine) before saving.

Output files are stored under ../test/ in two subdirectories mirroring the
repo layout:
    test/
      fjsp/
        Brandimarte1993/mk01.txt
        HurinkJurischThole1994/edata/abz5.txt
        ...
      jsp/
        FisherThompson1963/ft06.txt
        Lawrence1984/la01.txt
        ...
"""

import json
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


REPO = "ScheduleOpt/benchmarks"
BRANCH = "main"

# ── Flexible job shop ──────────────────────────────────────────────────────────
FJSP_INSTANCES_DIR = "flexible jobshop/instances"

# Datasets whose files are in Brandimarte .fjs format (compatible with from_txt)
FJSP_COMPATIBLE_DATASETS = {
    "Brandimarte1993",
    "ChambersBarnes1996",
    "DauzerePeresPaulli1994",
    "FattahiMehrabadJolai2007",
    "BehnkeGeiger2012",
    "HurinkJurischThole1994",
    "KacemHammadiBorne2002",
}

# ── Classic job shop ───────────────────────────────────────────────────────────
JSP_INSTANCES_DIR = "jobshop/instances"

RETRY_ATTEMPTS = 3


# ── Network helpers ────────────────────────────────────────────────────────────

def _fetch(url: str) -> bytes:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            print(f"  Retry {attempt + 1}/{RETRY_ATTEMPTS}: {exc}")
            time.sleep(2 ** attempt)


def get_tree(repo: str, branch: str) -> list:
    """Fetch the full recursive git tree from the GitHub API."""
    url = f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
    print(f"Fetching repository tree from {url}")
    data = _fetch(url)
    return json.loads(data).get("tree", [])


# ── JSP → Brandimarte converter ───────────────────────────────────────────────

def _jsp_to_brandimarte(text: str) -> str:
    """Convert classic JSP format to Brandimarte FJSP format.

    Input format (0-based machine IDs):
        <num_jobs> <num_machines>
        <m0> <t0>  <m1> <t1>  ...  (one row per job, num_machines pairs)

    Output format (1-based machine IDs, 1 eligible machine per operation):
        <num_jobs> <num_machines> 1
        <num_ops>  1 <m0+1> <t0>  1 <m1+1> <t1>  ...  (one row per job)
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header = lines[0].split()
    num_jobs = int(header[0])
    num_machines = int(header[1])

    out_lines = [f"{num_jobs} {num_machines} 1"]
    for job_line in lines[1:num_jobs + 1]:
        tokens = list(map(int, job_line.split()))
        # Each pair: (machine_0based, duration)
        pairs = [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens), 2)]
        parts = [str(len(pairs))]
        for machine, duration in pairs:
            parts += ["1", str(machine + 1), str(duration)]
        out_lines.append(" ".join(parts))

    return "\n".join(out_lines) + "\n"


# ── Download logic ─────────────────────────────────────────────────────────────

def collect_fjsp_files(tree: list) -> list:
    """Return (repo_path, rel_path) for all compatible FJSP instance files."""
    prefix = FJSP_INSTANCES_DIR + "/"
    files = []
    skipped_datasets = set()
    for item in tree:
        if item["type"] != "blob":
            continue
        path = item["path"]
        if not path.startswith(prefix) or not path.endswith(".txt"):
            continue
        rel = path[len(prefix):]
        dataset = rel.split("/")[0]
        if dataset not in FJSP_COMPATIBLE_DATASETS:
            skipped_datasets.add(dataset)
            continue
        files.append(("fjsp", path, rel))
    if skipped_datasets:
        print(f"  FJSP: skipping incompatible datasets: {', '.join(sorted(skipped_datasets))}")
    return files


def collect_jsp_files(tree: list) -> list:
    """Return (repo_path, rel_path) for all JSP instance files."""
    prefix = JSP_INSTANCES_DIR + "/"
    files = []
    for item in tree:
        if item["type"] != "blob":
            continue
        path = item["path"]
        if not path.startswith(prefix) or not path.endswith(".txt"):
            continue
        rel = path[len(prefix):]
        files.append(("jsp", path, rel))
    return files


def main() -> None:
    this_dir = os.path.abspath(os.path.dirname(__file__))
    test_dir = os.path.abspath(os.path.join(this_dir, "..", "test"))

    tree = get_tree(REPO, BRANCH)

    fjsp_files = collect_fjsp_files(tree)
    jsp_files = collect_jsp_files(tree)

    print(f"  FJSP instances found: {len(fjsp_files)}")
    print(f"  JSP  instances found: {len(jsp_files)}")
    print(f"  Total: {len(fjsp_files) + len(jsp_files)}\n")

    base_raw = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

    def download_one(args):
        kind, path, rel = args
        dest = os.path.join(test_dir, kind, rel)
        if os.path.exists(dest):
            return dest, False
        url = base_raw + "/" + urllib.parse.quote(path)
        raw = _fetch(url)
        content = _jsp_to_brandimarte(raw.decode("utf-8")).encode("utf-8") if kind == "jsp" else raw
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(content)
        return dest, True

    all_files = fjsp_files + jsp_files
    downloaded = 0
    already_present = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_one, item): item for item in all_files}
        for future in as_completed(futures):
            dest, was_downloaded = future.result()
            if was_downloaded:
                downloaded += 1
                print(f"  Downloaded {os.path.relpath(dest, test_dir)}")
            else:
                already_present += 1

    print(f"\nDone: {downloaded} downloaded, {already_present} already present.")


if __name__ == "__main__":
    main()
