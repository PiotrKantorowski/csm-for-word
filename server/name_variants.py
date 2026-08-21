from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Set

from legal_lexicon import COMMON_POLISH_FIRST_NAMES, deaccent_role

DATA_PATH = Path(__file__).resolve().parent / "data" / "legal_lexicon" / "name_variants_pl.json"


def _title_like(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    return value[:1].upper() + value[1:].lower()


@lru_cache(maxsize=1)
def _load_data() -> dict:
    if not DATA_PATH.exists():
        return {"names": {}}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"names": {}}


@lru_cache(maxsize=1)
def _form_to_canonical_key() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical in COMMON_POLISH_FIRST_NAMES:
        key = deaccent_role(canonical)
        mapping[key] = key
    names = _load_data().get("names", {})
    for canonical, payload in names.items():
        canonical_key = deaccent_role(canonical)
        mapping[canonical_key] = canonical_key
        forms = [canonical]
        if isinstance(payload, dict):
            forms += list(payload.get("forms", []) or [])
            forms += list(payload.get("diminutives", []) or [])
            forms += list(payload.get("ascii_forms", []) or [])
        for form in forms:
            if isinstance(form, str) and form.strip():
                mapping[deaccent_role(form)] = canonical_key
    return mapping


@lru_cache(maxsize=1)
def _canonical_to_forms() -> dict[str, Set[str]]:
    out: dict[str, Set[str]] = {}
    names = _load_data().get("names", {})
    for canonical, payload in names.items():
        canonical_key = deaccent_role(canonical)
        forms: Set[str] = {canonical}
        if isinstance(payload, dict):
            for key in ("forms", "diminutives", "ascii_forms"):
                forms.update(v for v in payload.get(key, []) or [] if isinstance(v, str) and v.strip())
        out.setdefault(canonical_key, set()).update(forms)
    for canonical in COMMON_POLISH_FIRST_NAMES:
        key = deaccent_role(canonical)
        out.setdefault(key, set()).add(_title_like(canonical))
    return out


def first_name_key(value: str) -> str:
    up = deaccent_role(value).strip(".,;:()[]{}„”\"'")
    if not up:
        return up
    mapping = _form_to_canonical_key()
    if up in mapping:
        return mapping[up]
    candidates = {up}
    # Conservative generic inflection fallbacks used only to map to a known base.
    for suffix in ("OWI", "EM", "IE", "A", "Y", "EGO", "U", "Ą", "Ę", "YM"):
        if up.endswith(suffix) and len(up) > len(suffix) + 2:
            base = up[:-len(suffix)]
            candidates.add(base)
            if suffix in {"Ą", "Ę"}:
                candidates.add(base + "A")
    for candidate in candidates:
        if candidate in mapping:
            return mapping[candidate]
    return up


def is_first_name_form(value: str) -> bool:
    return first_name_key(value) in _canonical_to_forms()


def first_name_variants(value: str) -> Set[str]:
    key = first_name_key(value)
    variants: Set[str] = set(_canonical_to_forms().get(key, set()))
    if value:
        variants.add(value)
    # Generic fallback for names not present in the JSON but already known to CSM.
    canonical = _title_like(key)
    if canonical:
        variants.add(canonical)
        if canonical.endswith("a") and len(canonical) > 3:
            stem = canonical[:-1]
            variants.update({stem + "y", stem + "ie", stem + "ą", stem + "ę"})
        elif len(canonical) > 3:
            variants.update({canonical + "a", canonical + "owi", canonical + "em", canonical + "ie", canonical + "u"})
    return {v for v in variants if isinstance(v, str) and v.strip()}


def expand_given_names_variants(parts: Iterable[str], limit: int = 128) -> Set[str]:
    """Return inflected/diminutive combinations for one or more given names.

    Used for full legal names with multiple given names, e.g. "Michał Adam
    Nowacki" -> "Michała Adama Nowackiego". The expansion is capped so a
    pathological name cannot explode the replacement map.
    """
    pools = [sorted(first_name_variants(p), key=lambda x: (len(x), x))[:12] for p in parts if p]
    if not pools:
        return set()
    out = {""}
    for pool in pools:
        next_out: Set[str] = set()
        for prefix in out:
            for item in pool:
                next_out.add((prefix + " " + item).strip())
                if len(next_out) >= limit:
                    break
            if len(next_out) >= limit:
                break
        out = next_out
    return out
