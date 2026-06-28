"""
find_company_websites.py
========================
Reads it_sponsors_filtered.csv, searches for each company's official website
using DuckDuckGo, and writes results to it_sponsors_with_websites.csv.

SETUP
-----
pip install ddgs requests

USAGE
-----
python find_company_websites.py

Options (edit the constants at the top of the file):
  INPUT_CSV   - path to the filtered IT sponsors CSV
  OUTPUT_CSV  - output path
  DELAY_SEC   - seconds to wait between searches (avoid rate limiting, recommended >= 1.5)
  START_FROM  - row index (0-based) to resume from if the script was interrupted
  MAX_ROWS    - set to a number to limit how many rows to process (None = all)
"""

import csv
import re
import time
import sys
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

INPUT_CSV  = "it_sponsors_filtered.csv"
OUTPUT_CSV = "it_sponsors_with_websites.csv"
DELAY_SEC  = 1.5        # pause between searches
START_FROM = 0          # resume from this 0-based row index
MAX_ROWS   = None       # None = all rows

# ── Helpers ──────────────────────────────────────────────────────────────────

STOP_WORDS = {
    "linkedin", "glassdoor", "indeed", "reed.co.uk", "totaljobs", "cwjobs",
    "companies house", "companies-house", "gov.uk", "wikip", "facebook",
    "twitter", "instagram", "crunchbase", "bloomberg", "reuters", "ft.com",
}

def looks_like_company_site(url: str, name: str) -> bool:
    """Return True if a search-result URL looks like the official site."""
    url_lower = url.lower()
    if any(sw in url_lower for sw in STOP_WORDS):
        return False
    return True


def slug_from_name(name: str) -> str:
    """Turn 'Acme Tech Ltd' into 'acmetech' for rough domain matching."""
    cleaned = re.sub(r"[^a-z0-9]", "", name.lower())
    for suffix in ("ltd", "limited", "plc", "uk", "inc", "corp", "group"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned


def best_url_from_results(results: list[dict], name: str) -> str:
    """Pick the best URL from DDG results for a given company name."""
    slug = slug_from_name(name)
    candidates = []
    for r in results:
        href = r.get("href") or r.get("url") or ""
        if not href:
            continue
        if not looks_like_company_site(href, name):
            continue
        # Try to pull root domain
        m = re.match(r"(https?://[^/]+)", href)
        root = m.group(1) if m else href
        # Score: higher if domain contains slug characters
        domain = re.sub(r"https?://(www\.)?", "", root).lower()
        domain_plain = re.sub(r"[^a-z0-9]", "", domain)
        score = 2 if (slug and slug[:6] in domain_plain) else 1
        candidates.append((score, root))

    if not candidates:
        return ""
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        from ddgs import DDGS
    except ImportError:
        print("ERROR: 'ddgs' is not installed. Run:  pip install ddgs")
        sys.exit(1)

    input_path  = Path(INPUT_CSV)
    output_path = Path(OUTPUT_CSV)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path.resolve()}")
        sys.exit(1)

    # Read all rows
    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    # Load already-done results so we can resume
    done: dict[str, str] = {}
    if output_path.exists():
        with output_path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name = r.get("organisation_name", "").strip()
                url  = r.get("company_website", "").strip()
                if name and url:
                    done[name] = url

    fieldnames = [
        "organisation_name", "town_city", "county", "type_rating", "route",
        "company_website",
    ]

    rows_to_process = all_rows[START_FROM:]
    if MAX_ROWS is not None:
        rows_to_process = rows_to_process[:MAX_ROWS]

    total   = len(rows_to_process)
    found   = 0
    skipped = 0

    print(f"Processing {total} companies (starting at row {START_FROM})...")
    print(f"Output: {output_path.resolve()}\n")

    # Open output in append mode so we can resume
    write_header = not output_path.exists() or output_path.stat().st_size == 0
    out_f = output_path.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_f, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()

    try:
        for idx, row in enumerate(rows_to_process, start=START_FROM + 1):
            name = row.get("organisation_name", "").strip()

            # Skip already done
            if name in done:
                skipped += 1
                print(f"[{idx}/{total+START_FROM}] SKIP (already done): {name}")
                continue

            query = f"{name} official website UK"
            url   = ""
            try:
                with DDGS(timeout=15) as ddgs:
                    results = list(ddgs.text(query, max_results=8))
                url = best_url_from_results(results, name)
            except Exception as e:
                print(f"[{idx}/{total+START_FROM}] SEARCH ERROR for '{name}': {e}")
                time.sleep(DELAY_SEC * 2)

            if url:
                found += 1
                print(f"[{idx}/{total+START_FROM}] FOUND: {name}  →  {url}")
            else:
                print(f"[{idx}/{total+START_FROM}] NOT FOUND: {name}")

            writer.writerow({
                "organisation_name": name,
                "town_city":         row.get("town_city",   "").strip(),
                "county":            row.get("county",      "").strip(),
                "type_rating":       row.get("type_rating", "").strip(),
                "route":             row.get("route",       "").strip(),
                "company_website":   url,
            })
            out_f.flush()

            done[name] = url
            time.sleep(DELAY_SEC)
    finally:
        out_f.close()

    print(f"\nDone. {found}/{total} websites found. Results saved to {output_path.resolve()}")


if __name__ == "__main__":
    main()
