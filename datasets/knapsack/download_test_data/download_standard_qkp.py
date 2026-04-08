"""
Download Standard-QKP, QKPGroupII, QKPGroupIII instances into TIG format under
datasets/knapsack/test/standard-QKP/.

BKS for gap comparison: datasets/knapsack/test/standard-QKP/standard_qkp_bks.csv

Sources:
  Standard-QKP: https://cedric.cnam.fr/~soutif/QKP
  Group II:  https://leria-info.univ-angers.fr/~jinkao.hao/QKPDATA/QKPGroupII.zip
  Group III: https://leria-info.univ-angers.fr/%7Ejinkao.hao/QKPDATA/QKPGroupIII.zip
  Results:   https://github.com/phil85/results-for-qkp-benchmark-instances
"""

import io
import os
import shutil
import time
import zipfile
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import patoolib

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "test", "standard-QKP"))
RAW_DIR = os.path.join(OUTPUT_DIR, "_raw")

MAX_WORKERS = 8
RETRY_ATTEMPTS = 3

STANDARD_URL_BASE = "https://cedric.cnam.fr/~soutif/QKP"

GROUP_II_ZIP = "https://leria-info.univ-angers.fr/~jinkao.hao/QKPDATA/QKPGroupII.zip"

GROUP_III_ZIP = "https://leria-info.univ-angers.fr/%7Ejinkao.hao/QKPDATA/QKPGroupIII.zip"

STANDARD_COMBOS = [
    (nn, d, idx)
    for nn in [100, 200, 300]
    for d in {100: [25, 50, 75, 100],
              200: [25, 50, 75, 100],
              300: [25, 50]}[nn]
    for idx in range(1, 11)
]

GROUP_II_COMBOS = [
    (nn, d, idx)
    for nn in [1000, 2000]
    for d in sorted(map(str, [25, 50, 75, 100]))
    for idx in sorted(map(str, range(1, 11)))
]

GROUP_II_RAR_MAP = {
    1000: [25, 50, 75, 100],
    2000: ['25', '50(1)', '50(2)', '75(1)', '75(2)', '100(1)', '100(2)'],
}


def _fetch(url: str) -> bytes:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            print(f"  Retry {attempt + 1}/{RETRY_ATTEMPTS}: {exc}")
            time.sleep(2 ** attempt)


def _parse_edges(lines: list, nn: int, linear_line: int, quad_start: int):
    edges = []
    linear = [int(v) for v in lines[linear_line].split() if v]
    for i in range(nn):
        edges.append((i, i, linear[i]))
    for i in range(nn):
        quad = [int(v) for v in lines[quad_start + i].split() if v]
        for j in range(i + 1, nn):
            edges.append((i, j, quad[j - (i + 1)]))
    return [e for e in edges if e[2] != 0]


def _write_tig(path: str, nn: int, edges: list, weights: list, budget: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{nn} {len(edges)} int\n")
        for i, j, val in edges:
            f.write(f"{i} {j} {int(val)}\n")
        f.write(" ".join(str(int(w)) for w in weights) + "\n")
        f.write(f"{int(budget)}\n")


def _parse_leria_group_iii(text: str) -> tuple:
    lines = text.splitlines()
    if len(lines) < 3:
        raise ValueError("LERIA Group III: file too short")

    nn = int(lines[1].strip())

    i = 2
    while i < len(lines) and not lines[i].strip():
        i += 1
    matrix_start = i
    if matrix_start + nn > len(lines):
        raise ValueError("LERIA Group III: matrix rows truncated")

    edges = []
    for row in range(nn):
        vals = [int(x) for x in lines[matrix_start + row].split()]
        expected = nn - row
        if len(vals) != expected:
            raise ValueError(
                f"LERIA Group III: row {row} has {len(vals)} values, expected {expected}"
            )
        for k, v in enumerate(vals):
            j = row + k
            if v != 0:
                edges.append((row, j, v))

    ti = matrix_start + nn
    while ti < len(lines) and not lines[ti].strip():
        ti += 1
    if ti >= len(lines):
        raise ValueError("LERIA Group III: missing budget after matrix")

    first_tok = lines[ti].split()
    if len(first_tok) == 1 and first_tok[0] == "0":
        ti += 1
        if ti >= len(lines):
            raise ValueError("LERIA Group III: missing budget after 0 line")
        budget = int(lines[ti].strip())
        ti += 1
    else:
        budget = int(first_tok[0])
        ti += 1

    while ti < len(lines) and not lines[ti].strip():
        ti += 1
    if ti >= len(lines):
        raise ValueError("LERIA Group III: missing weights line")
    weights = [int(x) for x in lines[ti].split()]
    if len(weights) != nn:
        raise ValueError(
            f"LERIA Group III: expected {nn} weights, got {len(weights)}"
        )

    return nn, edges, weights, budget


def _download_standard_instance(instance: str) -> None:
    url = f"{STANDARD_URL_BASE}/jeu_{instance}"
    print(f"  Downloading {instance} …")
    raw = _fetch(url).decode()
    lines = raw.split('\n')

    nn = int(lines[1].strip())
    edges = _parse_edges(lines, nn, linear_line=2, quad_start=3)
    budget = int(lines[4 + nn].strip())
    weights = [int(v) for v in lines[5 + nn].split() if v]

    _write_tig(os.path.join(OUTPUT_DIR, instance), nn, edges, weights, budget)


def download_standard() -> None:
    print("\n=== Standard QKP (100 / 200 / 300 nodes) ===")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {
            ex.submit(_download_standard_instance, f"{nn}_{d}_{idx}.txt"): (nn, d, idx)
            for nn, d, idx in STANDARD_COMBOS
        }
        for fut in as_completed(futs):
            exc = fut.exception()
            if exc:
                print(f"  ERROR {futs[fut]}: {exc}")


def _process_group_ii_instance(instance: str) -> None:
    dat_path = os.path.join(RAW_DIR, instance.replace('.txt', '.dat'))
    with open(dat_path, 'r') as f:
        lines = f.read().splitlines()

    nn = int(lines[0].strip())
    edges = _parse_edges(lines, nn, linear_line=1, quad_start=2)
    budget = int(lines[3 + nn].strip())
    weights = [int(v) for v in lines[4 + nn].split() if v]

    _write_tig(os.path.join(OUTPUT_DIR, instance), nn, edges, weights, budget)


def download_group_ii() -> None:
    if not shutil.which('unrar'):
        print("WARNING: 'unrar' not installed — skipping Group II.")
        return

    print("\n=== QKPGroupII (1000 / 2000 nodes) ===")

    os.makedirs(RAW_DIR, exist_ok=True)
    try:
        print("  Downloading Group II zip …")
        raw = _fetch(GROUP_II_ZIP)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.extractall(RAW_DIR)

        for prefix, dens_list in GROUP_II_RAR_MAP.items():
            for d in dens_list:
                rar_path = os.path.join(RAW_DIR, "QKPGroupII", f"{prefix}_{d}.rar")
                patoolib.extract_archive(rar_path, outdir=RAW_DIR)
                folder = os.path.join(RAW_DIR, f"{prefix}_{d}")
                if os.path.isdir(folder):
                    for fname in os.listdir(folder):
                        os.replace(os.path.join(folder, fname),
                                   os.path.join(RAW_DIR, fname))

        instances = [f"{nn}_{d}_{idx}.txt" for nn, d, idx in GROUP_II_COMBOS]
        with multiprocessing.Pool(MAX_WORKERS) as pool:
            pool.map(_process_group_ii_instance, instances)
    finally:
        shutil.rmtree(RAW_DIR, ignore_errors=True)


def _convert_group_iii_file(src_path: str, dest_path: str) -> tuple:
    with open(src_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    nn, edges, weights, budget = _parse_leria_group_iii(text)
    _write_tig(dest_path, nn, edges, weights, budget)
    return nn, len(edges)


def download_group_iii() -> None:
    print("\n=== QKPGroupIII (5000 / 6000 nodes) → TIG ===")
    print("  Downloading Group III zip …")
    raw = _fetch(GROUP_III_ZIP)
    os.makedirs(RAW_DIR, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            zf.extractall(RAW_DIR)

        extracted_dir = os.path.join(RAW_DIR, "QKPGroupIII")
        if not os.path.isdir(extracted_dir):
            raise FileNotFoundError(
                f"Expected 'QKPGroupIII' directory in zip, not found under {RAW_DIR}"
            )

        for fname in sorted(os.listdir(extracted_dir)):
            if not fname.endswith(".txt"):
                continue
            src = os.path.join(extracted_dir, fname)
            dest = os.path.join(OUTPUT_DIR, fname)
            print(f"  Converting {fname} …")
            try:
                nn, m = _convert_group_iii_file(src, dest)
            except Exception as exc:
                raise RuntimeError(f"Group III {fname}: {exc}") from exc
            print(f"    → TIG: {nn} nodes, {m} edges")
    finally:
        shutil.rmtree(RAW_DIR, ignore_errors=True)


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    download_standard()
    download_group_ii()
    download_group_iii()
    print("\nDone.")
