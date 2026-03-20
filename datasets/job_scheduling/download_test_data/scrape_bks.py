#!/usr/bin/env python3
"""Scrape best-known solutions (BKS) for JSP and FJSP instances from:
  https://github.com/ScheduleOpt/benchmarks/tree/main

Sources:
  JSP:  jobshop/json/bks/bks.json       (structured JSON array)
  FJSP: flexible jobshop/README.md       (HTML tables embedded in Markdown)

The FJSP README has two table layouts:
  - Standard (Brandimarte, DauzerePeresPaulli, etc.): Instance | ... | UB | ...
  - Hurink multi-variant: Instance | Size | sdata | edata | rdata | vdata | ...
    where each variant cell holds the BKS makespan (or "LB / UB" when open,
    in which case UB is taken as the BKS).

Output: ../test/bks.csv
Columns:
  instance  - filename stem of the downloaded instance (e.g. "ft06", "mk01")
  variant   - Hurink data variant ("sdata"/"edata"/"rdata"/"vdata"), else ""
  bks       - best known makespan (upper bound)
"""

import csv
import json
import os
import time

import requests
from bs4 import BeautifulSoup


REPO_RAW = "https://raw.githubusercontent.com/ScheduleOpt/benchmarks/main"
JSP_BKS_URL = f"{REPO_RAW}/jobshop/json/bks/bks.json"
FJSP_README_URL = f"{REPO_RAW}/flexible%20jobshop/README.md"

RETRY_ATTEMPTS = 3
HURINK_VARIANTS = ("sdata", "edata", "rdata", "vdata")


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


def _hurink_cell_bks(td) -> int | None:
    """Extract the BKS makespan from a Hurink variant cell.

    Cell text is either "1234" or "LB / UB"; we always want the UB.
    """
    text = td.get_text(strip=True)
    try:
        return int(text.split("/")[-1].strip())
    except ValueError:
        return None


def fetch_jsp_bks() -> list:
    print("Fetching JSP BKS JSON …")
    entries = json.loads(_fetch(JSP_BKS_URL))
    rows = [
        {"instance": e["instance"], "variant": "", "bks": e["upper_bound"]}
        for e in entries
        if e.get("upper_bound") is not None
    ]
    print(f"  {len(rows)} JSP entries")
    return rows


def fetch_fjsp_bks() -> list:
    print("Fetching FJSP README …")
    soup = BeautifulSoup(_fetch(FJSP_README_URL).decode("utf-8"), "html.parser")
    rows = []

    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]

        hurink_cols = [h for h in headers if h in HURINK_VARIANTS]
        is_hurink = bool(hurink_cols)

        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            instance = cells[0].get_text(strip=True)
            if not instance:
                continue

            if is_hurink:
                for variant in hurink_cols:
                    vi = headers.index(variant)
                    if vi >= len(cells):
                        continue
                    bks = _hurink_cell_bks(cells[vi])
                    if bks is not None:
                        rows.append({"instance": instance, "variant": variant, "bks": bks})
            else:
                if "UB" not in headers:
                    continue
                try:
                    bks = int(cells[headers.index("UB")].get_text(strip=True))
                    rows.append({"instance": instance, "variant": "", "bks": bks})
                except (ValueError, IndexError):
                    continue

    print(f"  {len(rows)} FJSP entries")
    return rows


def main():
    this_dir = os.path.abspath(os.path.dirname(__file__))
    test_dir = os.path.abspath(os.path.join(this_dir, "..", "test"))
    os.makedirs(test_dir, exist_ok=True)
    output_path = os.path.join(test_dir, "bks.csv")

    rows = fetch_jsp_bks() + fetch_fjsp_bks()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["instance", "variant", "bks"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved {len(rows)} BKS entries → {output_path}")


if __name__ == "__main__":
    main()
