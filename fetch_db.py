"""
fetch_db.py

Pulls the latest london_transport.db from the transport repo's raw GitHub
URL — no auth needed since it's a public repo, and no gateway/hosting
required. Run this before starting the agent to make sure you're querying
current data (GitHub Actions there commits a fresh .db every 15 min).

Usage:
    python fetch_db.py
"""
import requests
from pathlib import Path

RAW_URL = (
    "https://raw.githubusercontent.com/Aashleshaj/"
    "London_Transport_Reliability_and_Economic_Impact/main/data/london_transport.db"
)
DEST = Path(__file__).resolve().parent / "london_transport.db"


def main():
    print(f"Fetching latest database from {RAW_URL} ...")
    resp = requests.get(RAW_URL, timeout=30)
    resp.raise_for_status()
    DEST.write_bytes(resp.content)
    print(f"✅ Saved {len(resp.content):,} bytes to {DEST}")


if __name__ == "__main__":
    main()
