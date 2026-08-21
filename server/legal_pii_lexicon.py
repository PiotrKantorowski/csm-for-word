from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

_BASE = Path(__file__).resolve().parent / "data" / "legal_lexicon"

_DEFAULTS = {
    "identity_document_labels": [
        "dowód osobisty", "dowod osobisty", "seria i numer dowodu osobistego",
        "numer dowodu osobistego", "nr dowodu osobistego", "dokument tożsamości",
        "dokumentu tożsamości", "dokumentów tożsamości", "tożsamości",
    ],
    "person_labels_contracts": [
        "reprezentacja", "dane reprezentanta", "osoba do kontaktu operacyjnego",
        "osoba do kontaktu", "imię i nazwisko", "imie i nazwisko",
        "reprezentowany przez", "reprezentowana przez", "działający przez",
        "działająca przez", "podpisany przez",
    ],
    "person_labels_process": [
        "powód", "powod", "powódka", "pozwany", "pozwana", "wnioskodawca",
        "wnioskodawczyni", "uczestnik", "uczestniczka", "skarżący", "skarzacy",
        "pełnomocnik", "pelnomocnik",
    ],
    "birth_family_labels": [
        "ur.", "urodzony", "urodzona", "data i miejsce urodzenia",
        "imiona rodziców", "imiona rodzicow", "nazwisko rodowe",
        "nazwisko panieńskie", "nazwisko panienskie",
    ],
    "public_authority_phrases": [
        "Rada Gminy", "Rady Gminy", "Gmina", "Gminy", "Rada Miasta",
        "Rady Miasta", "Urząd Miasta", "Urzad Miasta", "Urząd Gminy",
        "Urzad Gminy", "Starostwo Powiatowe", "Powiat", "Województwo", "Wojewodztwo",
    ],
}

_CACHE: dict | None = None


def _load() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    data = {k: list(v) for k, v in _DEFAULTS.items()}
    path = _BASE / "legal_contexts_pl.json"
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, values in loaded.items():
                    if isinstance(values, list):
                        merged = list(data.get(key, []))
                        for value in values:
                            if isinstance(value, str) and value not in merged:
                                merged.append(value)
                        data[key] = merged
        except Exception:
            pass
    _CACHE = data
    return data


def get_lexicon_list(key: str) -> list[str]:
    values = _load().get(key, [])
    return [v for v in values if isinstance(v, str) and v.strip()]


def alternation(values: Iterable[str]) -> str:
    import re
    return "|".join(re.escape(v) for v in values if v)
