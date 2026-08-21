"""
verify_gazetteer_licenses.py — validate license metadata for all bundled gazetteers.

Usage
-----
    python tools/verify_gazetteer_licenses.py          # exits 0 if all OK, 1 if any issue
    python tools/verify_gazetteer_licenses.py --strict  # also fail on warned sources

This tool is designed to be run as a CI gate and from tests. It checks that every
source marked `bundled: true` in `server/gazetteers/licenses.json` has:
  - a non-empty, acceptable license identifier
  - a non-empty license_url
  - a non-empty downloaded_at date
  - allowed_for_runtime: true

Forbidden license values:
    unknown, research-only, non-commercial, no-redistribution, restricted, proprietary*

(*) 'proprietary' is allowed only for sources with url='internal' — hand-authored data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSES_PATH = ROOT / "server" / "gazetteers" / "licenses.json"

FORBIDDEN_LICENSES = frozenset({
    "unknown",
    "research-only",
    "non-commercial",
    "no-redistribution",
    "restricted",
})

ALLOWED_LICENSES = frozenset({
    "CC0",
    "CC BY 4.0",
    "CC BY-SA 4.0",
    "MIT",
    "Apache-2.0",
    "ODbL",
    "public domain",
    "proprietary",  # internal/hand-authored only
})


def check_licenses(strict: bool = False) -> list[str]:
    """Return list of error strings. Empty list = all OK."""
    if not LICENSES_PATH.exists():
        return [f"licenses.json not found at {LICENSES_PATH}"]

    try:
        data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"licenses.json is invalid JSON: {exc}"]

    errors: list[str] = []
    warnings: list[str] = []

    sources = data.get("sources", [])
    if not sources:
        warnings.append("licenses.json has no 'sources' entries")

    for source in sources:
        sid = source.get("id", "<no id>")
        bundled = source.get("bundled", False)
        if not bundled:
            continue

        lic = source.get("license", "")
        lic_url = source.get("license_url", "")
        downloaded_at = source.get("downloaded_at", "")
        allowed_runtime = source.get("allowed_for_runtime", False)
        url = source.get("url", "")

        if not lic:
            errors.append(f"[{sid}] missing 'license'")
        elif lic.lower() in FORBIDDEN_LICENSES:
            errors.append(f"[{sid}] forbidden license: '{lic}'")
        elif lic == "proprietary" and url != "internal":
            errors.append(
                f"[{sid}] 'proprietary' license only allowed for url='internal' (hand-authored) sources"
            )
        elif lic not in ALLOWED_LICENSES:
            warnings.append(f"[{sid}] unrecognized license '{lic}' — verify it is permissive")

        if not lic_url:
            errors.append(f"[{sid}] missing 'license_url'")
        elif lic_url == "internal" and url != "internal":
            errors.append(f"[{sid}] 'internal' license_url only valid for internal sources")

        if not downloaded_at:
            errors.append(f"[{sid}] missing 'downloaded_at'")

        if not allowed_runtime:
            errors.append(f"[{sid}] bundled source has 'allowed_for_runtime': false — cannot be shipped")

    if strict:
        errors.extend(warnings)
        warnings.clear()

    return errors


def main() -> int:
    strict = "--strict" in sys.argv

    errors = check_licenses(strict=strict)

    if errors:
        print("LICENSE VERIFICATION FAILED", file=sys.stderr)
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1

    sources = json.loads(LICENSES_PATH.read_text(encoding="utf-8")).get("sources", [])
    bundled = [s for s in sources if s.get("bundled")]
    print(f"OK — {len(bundled)} bundled source(s) verified")
    for s in bundled:
        print(f"  [{s['id']}] license={s['license']} downloaded={s.get('downloaded_at','?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
