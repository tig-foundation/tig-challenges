"""
Download and convert Standard-QKP, QKPGroupII, and QKPGroupIII benchmark
instances into TIG format under datasets/knapsack/standard-QKP/.

Sources:
  Standard:   https://cedric.cnam.fr/~soutif/QKP
  Group II:   https://leria-info.univ-angers.fr/~jinkao.hao/QKPDATA/QKPGroupII.zip
  Group III:  https://leria-info.univ-angers.fr/%7Ejinkao.hao/QKPDATA/QKPGroupIII.zip
  Results:    https://github.com/phil85/results-for-qkp-benchmark-instances
"""

import os
import io
import time
import shutil
import zipfile
import multiprocessing
import concurrent.futures

import requests
import pdfplumber
import patoolib


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "test", "standard-QKP"))
RAW_DIR = os.path.join(OUTPUT_DIR, "_raw")

MAX_WORKERS = 8
RETRY_ATTEMPTS = 3
SOTA_ALGOS = ('QKBP', 'RG', 'IHEA', 'LDP', 'DP', 'QK', 'Gurobi', 'Hexaly')

STANDARD_URL_BASE = "https://cedric.cnam.fr/~soutif/QKP"
STANDARD_PDF = (
    "https://github.com/phil85/results-for-qkp-benchmark-instances"
    "/raw/main/tables/Standard-QKP_detailed_results.pdf"
)

GROUP_II_ZIP = "https://leria-info.univ-angers.fr/~jinkao.hao/QKPDATA/QKPGroupII.zip"
GROUP_II_PDF = (
    "https://raw.githubusercontent.com/phil85/results-for-qkp-benchmark-instances"
    "/main/tables/QKPGroupII_detailed_results.pdf"
)

GROUP_III_ZIP = "https://leria-info.univ-angers.fr/%7Ejinkao.hao/QKPDATA/QKPGroupIII.zip"
GROUP_III_PDF = (
    "https://raw.githubusercontent.com/phil85/results-for-qkp-benchmark-instances"
    "/main/tables/QKPGroupIII_detailed_results.pdf"
)

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

GROUP_III_COMBOS = [
    (nn, d, idx)
    for nn in [5000, 6000]
    for d in sorted(map(str, [25, 50, 75, 100]))
    for idx in range(1, 6)
]

GROUP_II_RAR_MAP = {
    1000: [25, 50, 75, 100],
    2000: ['25', '50(1)', '50(2)', '75(1)', '75(2)', '100(1)', '100(2)'],
}

all_instance_data: dict = {}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _fetch(url: str) -> bytes:
    """Download with simple retry logic."""
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


def _parse_pdf_results(pdf_url: str, combos: list, crop_box: tuple) -> dict:
    """Extract OFV, gap, and runtime data from a results PDF."""
    print("  Downloading results PDF …")
    raw = _fetch(pdf_url)
    data = {}
    page = 1
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for nn, d, idx in combos:
            crop = pdf.pages[page].crop(crop_box)
            table = crop.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            })
            if table[0][0] == 'γ BestOFV':
                table[0][:1] = list(table[0][0].split(' '))
                table[2][:1] = list(table[2][0].split(' '))
            assert tuple(table[0]) == ('γ', 'BestOFV') + SOTA_ALGOS + SOTA_ALGOS
            assert tuple(
                row[0] for i, row in enumerate(table) if i != 2
            ) == ('γ', '', '', 'Avg', 'Min', 'Max')
            row = table[2]
            data[f"{nn}_{d}_{idx}.txt"] = {
                'ofv': int(float(row[1].replace(',', ''))),
                'gaps': {
                    algo: None if row[2 + j] == '—'
                    else float(row[2 + j].replace(',', ''))
                    for j, algo in enumerate(SOTA_ALGOS)
                },
                'runtimes': {
                    algo: None if row[2 + len(SOTA_ALGOS) + j] == '—'
                    else float(row[2 + len(SOTA_ALGOS) + j])
                    for j, algo in enumerate(SOTA_ALGOS)
                },
            }
            page += 1
    print(f"  Extracted data for {len(data)} instances")
    return data


def _parse_edges(lines: list, nn: int, linear_line: int, quad_start: int):
    """Parse linear (self-loop) + upper-triangular quadratic utilities.
    Returns (i, j, value) tuples with zero-value entries removed."""
    edges = []
    linear = [int(v) for v in lines[linear_line].split() if v]
    for i in range(nn):
        edges.append((i, i, linear[i]))
    for i in range(nn):
        quad = [int(v) for v in lines[quad_start + i].split() if v]
        for j in range(i + 1, nn):
            edges.append((i, j, quad[j - (i + 1)]))
    return [e for e in edges if e[2] != 0]


def _write_tig(path: str, nn: int, edges: list, weights: list,
               budget: int, ofv: int) -> None:
    """Write one instance in TIG format."""
    with open(path, 'w') as f:
        f.write(f"{nn} {len(edges)} int\n")
        for i, j, val in edges:
            f.write(f"{i} {j} {val:.6f}\n")
        f.write(" ".join(str(w) for w in weights) + "\n")
        f.write(f"{budget}\n")
        f.write(f"{ofv}\n")


# ---------------------------------------------------------------------------
# Standard QKP  (n = 100, 200, 300)
# ---------------------------------------------------------------------------
def _download_standard_instance(instance: str, instance_data: dict) -> None:
    url = f"{STANDARD_URL_BASE}/jeu_{instance}"
    print(f"  Downloading {instance} …")
    raw = _fetch(url).decode()
    lines = raw.split('\n')

    nn = int(lines[1].strip())
    edges = _parse_edges(lines, nn, linear_line=2, quad_start=3)
    budget = int(lines[4 + nn].strip())
    weights = [int(v) for v in lines[5 + nn].split() if v]

    _write_tig(os.path.join(OUTPUT_DIR, instance),
               nn, edges, weights, budget, instance_data[instance]['ofv'])


def download_standard() -> None:
    print("\n=== Standard QKP (100 / 200 / 300 nodes) ===")
    data = _parse_pdf_results(STANDARD_PDF, STANDARD_COMBOS, (40, 145, 535, 195))
    all_instance_data.update(data)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_download_standard_instance,
                      f"{nn}_{d}_{idx}.txt", data): (nn, d, idx)
            for nn, d, idx in STANDARD_COMBOS
        }
        for fut in concurrent.futures.as_completed(futures):
            exc = fut.exception()
            if exc:
                print(f"  ERROR {futures[fut]}: {exc}")


# ---------------------------------------------------------------------------
# QKPGroupII  (n = 1000, 2000)
# ---------------------------------------------------------------------------
def _process_group_ii_instance(instance: str, instance_data: dict) -> None:
    dat_path = os.path.join(RAW_DIR, instance.replace('.txt', '.dat'))
    lines = open(dat_path, 'r').read().splitlines()

    nn = int(lines[0].strip())
    edges = _parse_edges(lines, nn, linear_line=1, quad_start=2)
    budget = int(lines[3 + nn].strip())
    weights = [int(v) for v in lines[4 + nn].split() if v]

    _write_tig(os.path.join(OUTPUT_DIR, instance),
               nn, edges, weights, budget, instance_data[instance]['ofv'])


def download_group_ii() -> None:
    if not shutil.which('unrar'):
        print("WARNING: 'unrar' not installed — skipping Group II.")
        return

    print("\n=== QKPGroupII (1000 / 2000 nodes) ===")
    data = _parse_pdf_results(GROUP_II_PDF, GROUP_II_COMBOS, (35, 142, 535, 192))
    all_instance_data.update(data)

    os.makedirs(RAW_DIR, exist_ok=True)

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
        pool.starmap(_process_group_ii_instance,
                     [(inst, data) for inst in instances])

    shutil.rmtree(RAW_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# QKPGroupIII  (n = 5000, 6000)
# ---------------------------------------------------------------------------
def download_group_iii() -> None:
    print("\n=== QKPGroupIII (5000 / 6000 nodes) ===")
    data = _parse_pdf_results(GROUP_III_PDF, GROUP_III_COMBOS, (35, 142, 535, 192))
    all_instance_data.update(data)

    print("  Downloading Group III zip …")
    raw = _fetch(GROUP_III_ZIP)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(OUTPUT_DIR)

    extracted_dir = os.path.join(OUTPUT_DIR, "QKPGroupIII")
    for fname in os.listdir(extracted_dir):
        os.replace(os.path.join(extracted_dir, fname),
                   os.path.join(OUTPUT_DIR, fname))
    os.rmdir(extracted_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    download_standard()
    download_group_ii()
    download_group_iii()
    print("\nDone.")
