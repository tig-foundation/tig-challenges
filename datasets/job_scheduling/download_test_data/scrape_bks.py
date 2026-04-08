#!/usr/bin/env python3
"""Download JSP/FJSP BKS from ScheduleOpt/benchmarks (solutions/bks.json)."""

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_B = "https://raw.githubusercontent.com/ScheduleOpt/benchmarks/main"
_SPECS = (
    ("jsp", f"{_B}/jobshop/solutions/bks.json"),
    ("fjsp", f"{_B}/flexible%20jobshop/solutions/bks.json"),
)
_FJSP_MT = {"ft06": "mt06", "ft10": "mt10", "ft20": "mt20"}
_RETRIES = 3


def _get(url: str) -> bytes:
    for attempt in range(_RETRIES):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as e:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(2**attempt)


def _rows(problem: str, data: bytes) -> list[dict]:
    rows = []
    for e in json.loads(data):
        ub = e.get("upper_bound")
        if ub is None:
            continue
        name = e["instance"]
        if problem == "fjsp":
            name = _FJSP_MT.get(name, name)
            variant = e.get("variant") or ""
        else:
            variant = ""
        rows.append(
            {"instance": name, "problem": problem, "variant": variant, "bks": ub}
        )
    return rows


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "test" / "bks.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        payloads = pool.map(lambda s: (s[0], _get(s[1])), _SPECS)

    rows: list[dict] = []
    for problem, raw in payloads:
        rows.extend(_rows(problem, raw))

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instance", "problem", "variant", "bks"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows → {out}")


if __name__ == "__main__":
    main()
