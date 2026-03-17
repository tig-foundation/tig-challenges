#!/usr/bin/env python3
"""
Scraper for VRPTW Homberger-Gehring (1999) best known solutions from CVRPLIB.
Fetches the Internet Archive snapshot of http://vrp.galgos.inf.puc-rio.br/index.php/en/
and extracts the table data for the Homberger & Gehring instance set.

Output: datasets/vehicle_routing/test/bks.csv
Columns: Instance, n, K, Q, UB, Opt
"""

import requests
import csv
import os
import sys
import time
from bs4 import BeautifulSoup

WAYBACK_URL = (
    "https://web.archive.org/web/20250618233016/"
    "http://vrp.galgos.inf.puc-rio.br/index.php/en/"
)

FALLBACK_URLS = [
    "https://web.archive.org/web/20251012112528/https://vrp.galgos.inf.puc-rio.br/index.php/en/",
    "https://web.archive.org/web/20250909031336/https://vrp.galgos.inf.puc-rio.br/index.php/en/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "test", "bks.csv")


def fetch_page(url: str, retries: int = 3, delay: float = 2.0) -> str:
    """Fetch the HTML content of the page with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            print(f"  Attempt {attempt}/{retries}: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"  Failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    return ""


def get_html() -> str:
    """Try primary URL, then fallbacks."""
    all_urls = [WAYBACK_URL] + FALLBACK_URLS
    for url in all_urls:
        print(f"\nFetching from: {url}")
        html = fetch_page(url)
        if html:
            print(f"  Success! ({len(html):,} bytes)")
            return html
        print("  Moving to next fallback...")
    return ""


def parse_homberger_gehring(html: str) -> list[dict]:
    """
    Parse Homberger & Gehring (1999) instances (set15) from the CVRPLIB page.

    Each instance row has 8 <td> cells:
      [0] empty (benchmark col, only filled on header row)
      [1] Instance name
      [2] n (number of customers)
      [3] K (number of vehicles, may be empty)
      [4] Q (vehicle capacity)
      [5] UB (upper bound / best known solution)
      [6] Opt (whether optimal: "yes" or "no")
      [7] Features (links/icons — we skip this)
    """
    soup = BeautifulSoup(html, "html.parser")
    instances = []

    rows = soup.find_all(
        "tr",
        class_=lambda c: c and "set15" in c.split() and "collapse" in c.split(),
    )

    for row in rows:
        cells = row.find_all("td", class_="data")
        if len(cells) < 7:
            continue

        instance = cells[1].get_text(strip=True)
        if not instance:
            continue

        instances.append({
            "Instance": instance,
            "n": cells[2].get_text(strip=True),
            "K": cells[3].get_text(strip=True) or "",
            "Q": cells[4].get_text(strip=True),
            "UB": cells[5].get_text(strip=True),
            "Opt": cells[6].get_text(strip=True),
        })

    print(f"  Parsed {len(instances)} Homberger & Gehring instances")
    return instances


def save_csv(data: list[dict], filepath: str) -> None:
    """Save a list of dicts to CSV."""
    if not data:
        print(f"  No data to save for {filepath}")
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = ["Instance", "n", "K", "Q", "UB", "Opt"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"  Saved {len(data)} rows to {filepath}")


def print_table(data: list[dict]) -> None:
    """Pretty-print a table to stdout."""
    if not data:
        return
    print(f"\n{'='*70}")
    print(f" VRPTW Best Known Solutions — Homberger & Gehring (1999)")
    print(f"{'='*70}")
    header = f"{'Instance':<15} {'n':>5} {'K':>5} {'Q':>5} {'UB':>12} {'Opt':>5}"
    print(header)
    print("-" * 70)
    for row in data:
        print(
            f"{row['Instance']:<15} {row['n']:>5} {row['K']:>5} {row['Q']:>5} "
            f"{row['UB']:>12} {row['Opt']:>5}"
        )
    print(f"\nTotal instances: {len(data)}")


def parse_from_local_file(filepath: str) -> list[dict]:
    """Parse from a local HTML file (useful for testing / offline use)."""
    print(f"\nReading local file: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()
    print(f"  Read {len(html):,} bytes")
    return parse_homberger_gehring(html)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--local":
        filepath = sys.argv[2] if len(sys.argv) > 2 else "CVRPLIB_-_All_Instances_webpage.html"
        instances = parse_from_local_file(filepath)
    else:
        html = get_html()
        if not html:
            print("\nERROR: Could not fetch the page from any URL.")
            print("You can use a local HTML file instead:")
            print(f"  python {sys.argv[0]} --local <path_to_html_file>")
            sys.exit(1)
        instances = parse_homberger_gehring(html)

    save_csv(instances, OUTPUT_PATH)
    print_table(instances)
    print("\nDone.")


if __name__ == "__main__":
    main()