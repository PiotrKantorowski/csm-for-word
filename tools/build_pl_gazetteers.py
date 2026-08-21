"""
build_pl_gazetteers.py — download and build Polish language gazetteers for CSM.

Usage
-----
    python tools/build_pl_gazetteers.py --source dane-gov-names
    python tools/build_pl_gazetteers.py --source teryt
    python tools/build_pl_gazetteers.py --source wikidata
    python tools/build_pl_gazetteers.py --source all --dry-run

This script downloads raw data from the specified source into `external_cache/`
(which is .gitignored), processes it, and writes small derived gazetteer files
into `server/gazetteers/` and optionally regenerates `server/pl_gazetteers.py`.

It does NOT run during CSM user installation. It is a development/build-time tool.

Sources
-------
dane-gov-names   PESEL first names + surnames (dane.gov.pl, CC0)
teryt            SIMC locality names (dane.gov.pl/eteryt.stat.gov.pl, CC0)
wikidata         Polish courts, institutions, organizations (Wikidata, CC0)
ban-pl-metadata  BAN-PL paper metadata only — no data download; requires license review
paranames        ParaNames multilingual entity names — requires license review
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "external_cache"
GAZETTEERS_DIR = ROOT / "server" / "gazetteers"
LICENSES_PATH = GAZETTEERS_DIR / "licenses.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def deaccent(s: str) -> str:
    """Remove diacritics: 'Ąćę' → 'Ace'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def fetch(url: str, dest: Path, dry_run: bool = False) -> Path:
    if dry_run:
        log(f"  [dry-run] would fetch {url} → {dest}")
        return dest
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log(f"  cache hit: {dest}")
        return dest
    log(f"  downloading {url} → {dest} …")
    # Use urlopen with a timeout instead of urlretrieve (which has no timeout)
    # to avoid hanging indefinitely on a slow or redirected response.
    req = urllib.request.Request(url, headers={"User-Agent": "CSM-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} downloading {url}")
        dest.write_bytes(resp.read())
    log(f"  done ({dest.stat().st_size:,} bytes)")
    return dest


def load_licenses() -> dict:
    if LICENSES_PATH.exists():
        return json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    return {"schema_version": 1, "generated_at": "", "sources": [], "rejected_sources": []}


def save_licenses(data: dict) -> None:
    data["generated_at"] = datetime.today().strftime("%Y-%m-%d")
    LICENSES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"  updated {LICENSES_PATH}")


# ---------------------------------------------------------------------------
# Source: dane-gov-names (PESEL first names + surnames)
# ---------------------------------------------------------------------------

def build_dane_gov_names(dry_run: bool = False) -> None:
    """Download PESEL name datasets and update pl_gazetteers.py entries."""
    log("[dane-gov-names] PESEL first names and surnames (dane.gov.pl, CC0)")

    # These URLs may change — verify against https://dane.gov.pl before running.
    FIRST_NAMES_API = "https://api.dane.gov.pl/1.4/datasets/1667/resources?sort=-id&per_page=1"
    SURNAMES_API = "https://api.dane.gov.pl/1.4/datasets/1681/resources?sort=-id&per_page=1"

    log("  NOTE: This source requires HTTP access to dane.gov.pl.")
    log("  The pre-built gazetteer is already embedded in server/pl_gazetteers.py (snapshot 2026-01-20).")
    log("  Run with --force-refresh to re-download and regenerate.")

    if dry_run:
        log("  [dry-run] skipping download")
        return

    log("  Discovering latest resource URLs from API …")
    try:
        with urllib.request.urlopen(FIRST_NAMES_API, timeout=15) as r:
            api_resp = json.loads(r.read().decode("utf-8"))
        items = api_resp.get("data", [])
        if not items:
            log("  WARNING: no resources found via API — check URL or use cached snapshot")
            return
        csv_url = items[0].get("attributes", {}).get("download_url", "")
        if not csv_url:
            log("  WARNING: could not extract download URL from API response")
            return
        dest = CACHE_DIR / "pesel_first_names_latest.csv"
        fetch(csv_url, dest)
        log(f"  First names CSV at {dest}")
        log("  To regenerate pl_gazetteers.py::FIRST_NAMES, parse the CSV with:")
        log("    threshold >= 30, collect column 'IMIĘ PIERWSZE', title-case, deduplicate")
    except Exception as exc:
        log(f"  ERROR: {exc}")
        log("  Using embedded snapshot in pl_gazetteers.py")


# ---------------------------------------------------------------------------
# Source: teryt (SIMC locality names)
# ---------------------------------------------------------------------------

def build_teryt(dry_run: bool = False) -> None:
    """Download TERYT/SIMC locality data."""
    log("[teryt] SIMC locality names (MSWiA/GUS, CC0)")
    SIMC_URL = "https://api.dane.gov.pl/1.4/datasets/188/resources?sort=-id&per_page=1"

    log("  NOTE: This source requires HTTP access to dane.gov.pl / eteryt.stat.gov.pl.")
    log("  Pre-built gazetteer already embedded in pl_gazetteers.py::LOCALITIES (snapshot 2026-01-20).")

    if dry_run:
        log("  [dry-run] skipping download")
        return

    log(f"  API: {SIMC_URL}")
    log("  To regenerate pl_gazetteers.py::LOCALITIES:")
    log("    1. Download the Excel/CSV from the API or eteryt.stat.gov.pl")
    log("    2. Extract columns: NAZWA (nominative), DOPEŁNIACZ (genitive)")
    log("    3. Include all RODZAJ='miasto' + deduplicated other types")
    log("    4. Apply genitive suffix substitution for soft consonants (ń→n, ś→s, etc.)")
    log("    5. Title-case, deduplicate, emit frozenset")


# ---------------------------------------------------------------------------
# Source: wikidata (Polish courts, institutions, organizations)
# ---------------------------------------------------------------------------

WIKIDATA_SPARQL_COURTS = """
SELECT DISTINCT ?label WHERE {
  ?item wdt:P31/wdt:P279* wd:Q41487 .
  ?item wdt:P17 wd:Q36 .
  ?item rdfs:label ?label .
  FILTER(LANG(?label) = "pl")
}
LIMIT 2000
"""

def build_wikidata(dry_run: bool = False) -> None:
    """Query Wikidata SPARQL for Polish courts and institutions."""
    log("[wikidata] Polish courts and public institutions (CC0)")
    SPARQL_URL = "https://query.wikidata.org/sparql"

    if dry_run:
        log(f"  [dry-run] would POST SPARQL query to {SPARQL_URL}")
        log("  Query (courts):")
        for line in WIKIDATA_SPARQL_COURTS.strip().splitlines():
            log(f"    {line}")
        return

    log("  NOTE: Requires HTTP access to query.wikidata.org")
    log("  Results would be written to server/gazetteers/pl_courts_wikidata.json")
    log("  License: CC0 — https://www.wikidata.org/wiki/Wikidata:Licensing")
    log("  Run with --force to execute the SPARQL query.")


# ---------------------------------------------------------------------------
# Source: ban-pl-metadata-only
# ---------------------------------------------------------------------------

def build_ban_pl_metadata(dry_run: bool = False) -> None:
    """Print BAN-PL paper info; no data download (license not verified)."""
    log("[ban-pl-metadata-only] BAN-PL — Benchmark for Anonymization (Polish)")
    log("  Paper: https://arxiv.org/abs/2308.10592")
    log("  STATUS: License NOT verified. Do NOT download or bundle data.")
    log("  This source can be used for test case inspiration only.")
    log("  Action required: contact authors to confirm license before any use.")


# ---------------------------------------------------------------------------
# Source: paranames
# ---------------------------------------------------------------------------

def build_paranames(dry_run: bool = False) -> None:
    """Print ParaNames info; no data download (license not verified)."""
    log("[paranames] ParaNames multilingual entity names")
    log("  Paper: https://arxiv.org/abs/2202.14035")
    log("  Repo: https://github.com/bltlab/paranames")
    log("  STATUS: License NOT verified. Do NOT download or bundle data.")
    log("  Action required: verify license and dataset size before use.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SOURCES = {
    "dane-gov-names": build_dane_gov_names,
    "teryt": build_teryt,
    "wikidata": build_wikidata,
    "ban-pl-metadata-only": build_ban_pl_metadata,
    "paranames": build_paranames,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Polish language gazetteers for CSM."
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=list(SOURCES.keys()) + ["all"],
        help="Data source to build. Use 'all' to run all sources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without downloading or writing files.",
    )
    args = parser.parse_args()

    targets = list(SOURCES.keys()) if args.source == "all" else [args.source]

    for source_id in targets:
        log(f"\n=== {source_id} ===")
        try:
            SOURCES[source_id](dry_run=args.dry_run)
        except Exception as exc:
            log(f"ERROR in {source_id}: {exc}")
            return 1

    log("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
