import io
import os
import time
import zipfile
import shutil

import requests


ZIP_URL = "https://www.sintef.no/globalassets/project/top/vrptw/homberger"


def download_with_retries(url: str, max_retries: int = 3, backoff_seconds: int = 2) -> bytes:
    for i in range(max_retries):
        try:
            print(f"Downloading {url}")
            resp = requests.get(url)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            if i + 1 < max_retries:
                print(f"Retrying {url}: {i + 1} of {max_retries}")
                time.sleep(backoff_seconds * (i + 1))
    raise RuntimeError(f"Failed to download {url} after {max_retries} attempts.")


def extract_instances(zip_bytes: bytes, dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [
            m
            for m in zf.namelist()
            if m.lower().endswith(".txt")
        ]
        if not members:
            print("Warning: no .txt instances found in ZIP archive.")
        for member in members:
            filename = os.path.basename(member)
            if not filename:
                continue
            target_path = os.path.join(dest_dir, filename)
            with zf.open(member) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def main() -> None:
    this_dir = os.path.abspath(os.path.dirname(__file__))
    test_dir = os.path.abspath(os.path.join(this_dir, "..", "test"))
    os.makedirs(test_dir, exist_ok=True)

    print("Downloading Homberger & Gehring instances ZIPs for sizes 600-1000")
    for size in [600, 800, 1000]:
        url = f"{ZIP_URL}/{size}/homberger_{size}_customer_instances.zip"
        zip_bytes = download_with_retries(url)
        extract_instances(zip_bytes, test_dir)


if __name__ == "__main__":
    main()
