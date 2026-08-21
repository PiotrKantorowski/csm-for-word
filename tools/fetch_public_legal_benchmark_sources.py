#!/usr/bin/env python3
"""Fetch or verify public legal-form sources used to design the CSM benchmark.

The executable benchmark uses synthetic PII embedded in structures inspired by
public legal forms.  This utility keeps the source traceability package honest:

- downloads the public reference files when the network is available;
- verifies already bundled files when the network is unavailable;
- does not replace a valid cached file/manifest with an error-only manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import urllib.request
from datetime import datetime, timezone
from typing import Any

SOURCES = {
    "gov_vehicle_sale_pdf": "https://www.gov.pl/attachment/1de13e93-b0bc-4214-a780-bf32d9154517",
    "gov_vehicle_sale_pdf_alt": "https://www.gov.pl/attachment/d1ee1c5d-e8df-4010-aa20-ad40e0c439c9",
    "gov_power_of_attorney": "https://www.gov.pl/attachment/0b0203e3-aad9-4d14-a0ec-9e453171f50c",
    "gov_commercial_lease": "https://www.gov.pl/attachment/aef63d8c-1fa0-4891-9770-956926af1742",
    "senat_commercial_lease_doc": "https://www.senat.gov.pl/gfx/senat/userfiles/_public/bss/wzory/29_umowa_najmu_podnajmu_lokalu_uzytkowego.doc",
    "so_warszawa_response_to_claim_doc": "https://bip.warszawa.so.gov.pl/uploads/files/migration/mstoleczne/boi/wzory_i_formularze/OP%20formularz%20%20-%20odpowiedz%20na%20pozew.doc",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(name: str, url: str, target: pathlib.Path, data: bytes, status: str) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "file": str(target).replace("\\", "/"),
        "bytes": len(data),
        "sha256": _sha256(data),
        "status": status,
        "verified_at": datetime.now(timezone.utc).date().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="tests/fixtures/public_sources_raw")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Do not download; only verify already bundled files and manifest them.",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for name, url in SOURCES.items():
        target = out_dir / f"{name}.bin"
        data: bytes | None = None
        status = "cached"
        error = ""

        if not args.verify_only:
            try:
                with urllib.request.urlopen(url, timeout=args.timeout) as response:
                    data = response.read()
                target.write_bytes(data)
                status = "downloaded"
                print(f"OK {name}: downloaded {len(data)} bytes")
            except Exception as exc:  # pragma: no cover - network utility only
                error = repr(exc)
                print(f"WARN {name}: download failed ({exc}); checking cached file")

        if data is None and target.exists():
            data = target.read_bytes()
            print(f"OK {name}: cached {len(data)} bytes")

        if data is None:
            manifest.append({"name": name, "url": url, "file": str(target).replace("\\", "/"), "error": error or "missing cached file"})
            continue

        entry = _entry(name, url, target, data, status)
        if error:
            entry["download_error"] = error
        manifest.append(entry)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [entry for entry in manifest if entry.get("error")]
    if failures:
        print(f"DONE with {len(failures)} missing source(s); see {manifest_path}")
        raise SystemExit(2)
    print(f"DONE: manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
