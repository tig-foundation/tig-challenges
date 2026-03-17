"""
Download and convert TeamFormation-QKP benchmark instances to TIG format.

Sources:
  Synthetic: https://github.com/phil85/benchmark-instances-for-qkp/tree/main/raw_data/synthetic%20team%20formation%20data%20sets
  Real:      https://github.com/phil85/benchmark-instances-for-qkp/tree/main/raw_data/real%20team%20formation%20data%20sets

Based off code:
https://github.com/phil85/benchmark-instances-for-qkp/blob/main/download_synthetic_instances.py
https://github.com/phil85/benchmark-instances-for-qkp/blob/main/generate_instances_from_raw_data.py

"""

import os
import io
import time
import concurrent.futures

import numpy as np
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
# Project root is three levels up from this file:
#   tig-challenges/src/knapsack/download_test_data/download_teamformation_qkp.py
TIG_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", ".."))
TEST_ROOT = os.path.join(TIG_ROOT, "datasets", "knapsack", "test")

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------
BUDGET_FRACTIONS = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75]
MAX_WEIGHT_VAL = 10          # item weights drawn from U[1, MAX_WEIGHT_VAL]
JACCARD_SCALE  = 1000        # float Jaccard → int (× 1000), matching Rust generator
RANDOM_SEED    = 24
MAX_WORKERS    = 8
RETRY_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# GitHub raw-content base URLs
# ---------------------------------------------------------------------------
_GH_RAW = "https://raw.githubusercontent.com/phil85/benchmark-instances-for-qkp/main/raw_data"
SYNTHETIC_BASE = f"{_GH_RAW}/synthetic%20team%20formation%20data%20sets"
REAL_BASE      = f"{_GH_RAW}/real%20team%20formation%20data%20sets"

SYNTHETIC_FILES = [f"Synthetic_TF-{i}.txt" for i in range(1, 11)]
REAL_FILES      = ["Bibsonomy.xlsx", "DBLP.xlsx", "IMDB.xlsx", "StackOverflow.xlsx"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch(url: str) -> bytes:
    """Download url with simple retry logic."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            print(f"  Retry {attempt + 1}/{RETRY_ATTEMPTS} for {url}: {exc}")
            time.sleep(2 ** attempt)


def _budgets_for_weights(weights: np.ndarray) -> list[int]:
    total = int(weights.sum())
    return [max(1, int(f * total)) for f in BUDGET_FRACTIONS]


def _write_tig(out_path: str,
               n: int,
               edges: list[tuple[int, int, int]],
               weights: np.ndarray,
               budgets: list[int]) -> None:
    """Write a challenge file in TIG's graph-txt format (integer edges)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(f"{n} {len(edges)} int\n")
        for i, j, u in edges:
            f.write(f"{i} {j} {u}\n")
        f.write(" ".join(str(w) for w in weights) + "\n")
        # One budget per fraction, space-separated on a single line
        f.write(" ".join(str(b) for b in budgets) + "\n")


# ---------------------------------------------------------------------------
# Synthetic TF-1 … TF-10  (pre-computed graphs, float Jaccard edges)
# ---------------------------------------------------------------------------

def _process_synthetic_file(filename: str) -> None:
    url = f"{SYNTHETIC_BASE}/{filename}"
    stem = os.path.splitext(filename)[0]           # e.g. "Synthetic_TF-1"
    out_dir = os.path.join(TEST_ROOT, "TeamFormation-QKP")

    print(f"  Downloading {filename} …")
    raw = _fetch(url).decode()

    lines = raw.splitlines()
    header = lines[0].split()
    n, m = int(header[0]), int(header[1])

    # Parse edges; scale float Jaccard to int (×1000) so TIG's i32 parser works
    edges: list[tuple[int, int, int]] = []
    for line in lines[1 : 1 + m]:
        parts = line.split()
        i, j = int(parts[0]), int(parts[1])
        u = max(1, round(float(parts[2]) * JACCARD_SCALE))
        edges.append((i, j, u))

    # Deterministic per-file weights (seed varies by filename index)
    file_idx = int(stem.split("-")[1])
    rng = np.random.default_rng(RANDOM_SEED + file_idx)
    weights = rng.integers(1, MAX_WEIGHT_VAL + 1, size=n)
    budgets = _budgets_for_weights(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"{stem}_b{int(frac * 1000):04d}.txt"
        _write_tig(os.path.join(out_dir, out_name), n, edges, weights, [budget])


def download_synthetic() -> None:
    print(f"\n=== Synthetic TF files ({len(SYNTHETIC_FILES)} instances) ===")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_process_synthetic_file, f): f for f in SYNTHETIC_FILES}
        for fut in concurrent.futures.as_completed(futures):
            exc = fut.exception()
            if exc:
                print(f"  ERROR processing {futures[fut]}: {exc}")


# ---------------------------------------------------------------------------
# Real TF files  (Bibsonomy, DBLP, IMDB, StackOverflow xlsx)
# ---------------------------------------------------------------------------
# Each xlsx contains two sheets:
#   "adjacency_matrix"  – square similarity matrix (participants × participants)
#   "weights"           – optional per-participant weights (fallback: random)
# If the sheet names differ the code falls back to sheet index 0 / 1.

def _process_real_file(filename: str) -> None:
    """Parse real TF xlsx files.

    Each xlsx has a single sheet in adjacency-list format:
      col 0: participant name/ID
      col 1: participant weight (e.g. number of projects)
      col 2, 4, 6, …: neighbour name/ID
      col 3, 5, 7, …: edge weight (co-authorship count)
    """
    try:
        import pandas as pd
    except ImportError:
        print("  pandas not installed — skipping real xlsx files.  "
              "Install with:  pip install pandas openpyxl")
        return

    url = f"{REAL_BASE}/{filename}"
    stem = os.path.splitext(filename)[0]
    out_dir = os.path.join(TEST_ROOT, "TeamFormation-QKP")

    print(f"  Downloading {filename} …")
    raw = _fetch(url)

    xls = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
    df = xls.parse(xls.sheet_names[0], header=None, index_col=None)

    # Map participant name/ID (col 0) → sequential index
    participants = df.iloc[:, 0].tolist()
    part_to_idx: dict = {p: i for i, p in enumerate(participants)}
    n = len(participants)

    # Participant weights from col 1; fall back to random where missing/invalid
    raw_w = pd.to_numeric(df.iloc[:, 1], errors="coerce").values
    rng = np.random.default_rng(RANDOM_SEED)
    weights = np.where(
        np.isnan(raw_w) | (raw_w < 1),
        rng.integers(1, MAX_WEIGHT_VAL + 1, size=n),
        raw_w,
    ).astype(int)

    # Build undirected edge list from (col2, col3), (col4, col5), … pairs
    ncols = df.shape[1]
    edges_dict: dict[tuple[int, int], int] = {}
    for k_start in range(2, ncols - 1, 2):
        nb_col  = df.iloc[:, k_start]
        wt_col  = df.iloc[:, k_start + 1]
        valid   = nb_col.notna() & wt_col.notna()
        for row_i in df.index[valid]:
            i   = part_to_idx[df.iat[row_i, 0]]
            nb  = nb_col.iat[row_i]
            if nb not in part_to_idx:
                continue
            j   = part_to_idx[nb]
            a, b = min(i, j), max(i, j)
            if a == b:
                continue
            u = max(1, int(round(float(wt_col.iat[row_i]))))
            if (a, b) not in edges_dict or edges_dict[(a, b)] < u:
                edges_dict[(a, b)] = u
    edges = [(a, b, u) for (a, b), u in edges_dict.items()]

    budgets = _budgets_for_weights(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"{stem}_b{int(frac * 1000):04d}.txt"
        _write_tig(os.path.join(out_dir, out_name), n, edges, weights, [budget])


def download_real() -> None:
    print(f"\n=== Real TF files ({len(REAL_FILES)} datasets) ===")
    # Real files can be large; run sequentially to avoid memory pressure
    for filename in REAL_FILES:
        try:
            _process_real_file(filename)
        except Exception as exc:
            print(f"  ERROR processing {filename}: {exc}")


# ---------------------------------------------------------------------------
# Synthetic TF-2  (generated locally — O(n²) Jaccard, done once)
# ---------------------------------------------------------------------------

TF2_N_PARTICIPANTS = [1000, 2000, 4000, 6000, 8000, 10000]
TF2_N_PROJECTS     = 30000
TF2_LOG_MEAN       = 4
TF2_LOG_STD        = 1


def _generate_tf2_instance(n_participants: int) -> None:
    out_dir = os.path.join(TEST_ROOT, "TeamFormation-QKP")
    np.random.seed(RANDOM_SEED)

    projects = np.arange(TF2_N_PROJECTS)

    # Step 1: generate subsets
    indices, counter = [], 0
    while counter < TF2_N_PROJECTS:
        cardinality = 1 + int(np.random.lognormal(TF2_LOG_MEAN, TF2_LOG_STD))
        counter += cardinality
        indices.append(counter)
    subsets = np.split(projects, indices)[:-1]
    n_subsets = len(subsets)

    # Step 2: number of projects per participant
    n_proj_per = [1 + int(np.random.lognormal(TF2_LOG_MEAN, TF2_LOG_STD))
                  for _ in range(n_participants)]

    # Step 3: choose projects for each participant
    projects_dict: dict[int, np.ndarray] = {}
    for i in range(n_participants):
        sid = np.random.randint(n_subsets)
        sub = subsets[sid]
        if n_proj_per[i] < len(sub):
            sel = np.random.choice(sub, n_proj_per[i], replace=False)
        else:
            rest = np.setdiff1d(projects, sub)
            extra = np.random.choice(rest, n_proj_per[i] - len(sub), replace=False)
            sel = np.concatenate((sub, extra))
        projects_dict[i] = sel

    # Step 4: Jaccard similarity → int edges
    edges: list[tuple[int, int, int]] = []
    for i in range(n_participants):
        for j in range(i + 1, n_participants):
            ni = len(projects_dict[i])
            nj = len(projects_dict[j])
            intersection = len(np.intersect1d(projects_dict[i], projects_dict[j]))
            if intersection == 0:
                continue
            jac = intersection / (ni + nj - intersection)
            u = max(1, round(jac * JACCARD_SCALE))
            edges.append((i, j, u))

    rng = np.random.default_rng(RANDOM_SEED)
    weights = rng.integers(1, MAX_WEIGHT_VAL + 1, size=n_participants)
    budgets = _budgets_for_weights(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"synthetic_tf_{n_participants}_b{int(frac * 1000):04d}.txt"
        _write_tig(os.path.join(out_dir, out_name), n_participants, edges, weights, [budget])


def download_synthetic_tf2() -> None:
    print(f"\n=== Synthetic TF-2 files ({len(TF2_N_PARTICIPANTS)} instances — generated locally) ===")
    for n in TF2_N_PARTICIPANTS:
        print(f"  Generating n={n} …")
        try:
            _generate_tf2_instance(n)
        except Exception as exc:
            print(f"  ERROR generating n={n}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    download_synthetic()
    download_real()
    # download_synthetic_tf2()
    print("\nDone.")
