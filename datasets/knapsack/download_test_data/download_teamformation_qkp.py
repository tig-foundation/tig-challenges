"""
Download / generate TeamFormation-QKP instances into TIG format under
datasets/knapsack/test/TeamFormation-QKP/.

Synthetic: https://github.com/phil85/benchmark-instances-for-qkp/tree/main/raw_data/synthetic%20team%20formation%20data%20sets
Real:      https://github.com/phil85/benchmark-instances-for-qkp/tree/main/raw_data/real%20team%20formation%20data%20sets
"""

from __future__ import annotations

import io
import os
import time

import numpy as np
import requests

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
TIG_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", ".."))
OUT_DIR = os.path.join(TIG_ROOT, "datasets", "knapsack", "test", "TeamFormation-QKP")

BUDGET_FRACTIONS = [0.025, 0.05, 0.1, 0.25, 0.5, 0.75]
MAX_WEIGHT_VAL = 10
RANDOM_SEED = 24
RETRY_ATTEMPTS = 3

_GH_RAW = "https://raw.githubusercontent.com/phil85/benchmark-instances-for-qkp/main/raw_data"
SYNTHETIC_BASE = f"{_GH_RAW}/synthetic%20team%20formation%20data%20sets"
REAL_BASE = f"{_GH_RAW}/real%20team%20formation%20data%20sets"

SYNTHETIC_FILES = [f"Synthetic_TF-{i}.txt" for i in range(1, 11)]
REAL_FILES = ["Bibsonomy.xlsx", "DBLP.xlsx", "IMDB.xlsx", "StackOverflow.xlsx"]

TF2_N_PARTICIPANTS = [1000, 2000, 4000, 6000, 8000, 10000]
TF2_N_PROJECTS = 30000
TF2_LOG_MEAN = 4
TF2_LOG_STD = 1


def _fetch(url: str) -> bytes:
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


def _budgets_phil85(weights: np.ndarray) -> list[int]:
    total = int(np.sum(weights))
    return [int(f * total) for f in BUDGET_FRACTIONS]


def _write_tig_float(
    out_path: str,
    n: int,
    edges: list[tuple[int, int, float]],
    weights: np.ndarray,
    budget: int,
    *,
    m_header: int | None = None,
) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    m = len(edges) if m_header is None else m_header
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{n} {m} float\n")
        for i, j, u in edges:
            f.write(f"{i} {j} {u:.6f}\n")
        f.write(" ".join(str(int(w)) for w in weights) + "\n")
        f.write(f"{int(budget)}\n")


def _utility_from_xlsx(xlsx_bytes: bytes) -> np.ndarray:
    import pandas as pd

    df = pd.read_excel(io.BytesIO(xlsx_bytes), header=None, index_col=None)

    n_persons = df.shape[0]
    max_n_collaborators = df.shape[1]

    utility_matrix = np.zeros((n_persons, n_persons))
    names = df.iloc[:, 0].tolist()

    n_projects_dict: dict[str, tuple] = {}
    for i in range(n_persons):
        n_projects_dict[names[i]] = (i, df.iloc[i, 1])

    for i in range(n_persons):
        for j in range(2, max_n_collaborators, 2):
            if np.isnan(df.iloc[i, j + 1]):
                break
            collaborator = df.iloc[i, j]
            collaborator_pos = n_projects_dict[collaborator][0]
            n_projects_collaborator = n_projects_dict[collaborator][1]
            n_joint_projects = df.iloc[i, j + 1]
            n_projects_person = df.iloc[i, 1]
            utility_matrix[i, collaborator_pos] = n_joint_projects / (
                n_projects_person + n_projects_collaborator - n_joint_projects
            )

    utility_matrix[np.diag_indices_from(utility_matrix)] = 0
    return utility_matrix


def _process_synthetic_file(filename: str) -> None:
    url = f"{SYNTHETIC_BASE}/{filename}"
    stem = os.path.splitext(filename)[0]

    print(f"  Downloading {filename} …")
    lines = _fetch(url).decode("utf-8").splitlines()
    header = lines[0].split()
    n, m = int(header[0]), int(header[1])

    edges: list[tuple[int, int, float]] = []
    for line in lines[1 : 1 + m]:
        parts = line.split()
        i, j = int(parts[0]), int(parts[1])
        val = float(parts[2])
        if i != j:
            edges.append((i, j, val))

    np.random.seed(RANDOM_SEED)
    weights = np.random.randint(1, MAX_WEIGHT_VAL + 1, size=n)
    budgets = _budgets_phil85(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"{stem}_b{int(frac * 1000):04d}.txt"
        _write_tig_float(os.path.join(OUT_DIR, out_name), n, edges, weights, budget)


def download_synthetic() -> None:
    print(f"\n=== Synthetic TF files ({len(SYNTHETIC_FILES)} instances) ===")
    for f in SYNTHETIC_FILES:
        try:
            _process_synthetic_file(f)
        except Exception as exc:
            print(f"  ERROR processing {f}: {exc}")


def _process_real_file(filename: str) -> None:
    url = f"{REAL_BASE}/{filename}"
    stem = os.path.splitext(filename)[0]

    print(f"  Downloading {filename} …")
    try:
        utility_matrix = _utility_from_xlsx(_fetch(url))
    except ImportError:
        print(
            "  pandas/openpyxl not installed — skipping real xlsx files. "
            "pip install pandas openpyxl"
        )
        return

    n_nodes = utility_matrix.shape[0]
    n_edges = int(np.count_nonzero(utility_matrix) / 2)

    edges: list[tuple[int, int, float]] = []
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if utility_matrix[i, j] > 0:
                edges.append((i, j, float(utility_matrix[i, j])))

    np.random.seed(RANDOM_SEED)
    weights = np.random.randint(1, MAX_WEIGHT_VAL + 1, size=n_nodes)
    budgets = _budgets_phil85(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"{stem}_b{int(frac * 1000):04d}.txt"
        _write_tig_float(
            os.path.join(OUT_DIR, out_name),
            n_nodes,
            edges,
            weights,
            budget,
            m_header=n_edges,
        )


def download_real() -> None:
    print(f"\n=== Real TF files ({len(REAL_FILES)} datasets) ===")
    for filename in REAL_FILES:
        try:
            _process_real_file(filename)
        except Exception as exc:
            print(f"  ERROR processing {filename}: {exc}")


def _generate_tf2_instance(n_participants: int) -> None:
    np.random.seed(RANDOM_SEED)

    projects = np.arange(TF2_N_PROJECTS)

    indices, counter = [], 0
    while counter < TF2_N_PROJECTS:
        cardinality = 1 + int(np.random.lognormal(TF2_LOG_MEAN, TF2_LOG_STD))
        counter += cardinality
        indices.append(counter)
    subsets = np.split(projects, indices)[:-1]
    n_subsets = len(subsets)

    n_proj_per = [
        1 + int(np.random.lognormal(TF2_LOG_MEAN, TF2_LOG_STD)) for _ in range(n_participants)
    ]

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

    edges: list[tuple[int, int, float]] = []
    for i in range(n_participants):
        for j in range(i + 1, n_participants):
            ni = len(projects_dict[i])
            nj = len(projects_dict[j])
            intersection = len(np.intersect1d(projects_dict[i], projects_dict[j]))
            if intersection == 0:
                continue
            jac = intersection / (ni + nj - intersection)
            edges.append((i, j, float(jac)))

    weights = np.random.randint(1, MAX_WEIGHT_VAL + 1, size=n_participants)
    budgets = _budgets_phil85(weights)

    for frac, budget in zip(BUDGET_FRACTIONS, budgets):
        out_name = f"synthetic_tf_{n_participants}_b{int(frac * 1000):04d}.txt"
        _write_tig_float(os.path.join(OUT_DIR, out_name), n_participants, edges, weights, budget)


def download_synthetic_tf2() -> None:
    print(f"\n=== Synthetic TF-2 ({len(TF2_N_PARTICIPANTS)} instances, local) ===")
    for n in TF2_N_PARTICIPANTS:
        print(f"  Generating n={n} …")
        try:
            _generate_tf2_instance(n)
        except Exception as exc:
            print(f"  ERROR generating n={n}: {exc}")


if __name__ == "__main__":
    download_synthetic()
    download_real()
    download_synthetic_tf2()
    print("\nDone.")
