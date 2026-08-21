from __future__ import annotations

import base64
import bisect
import ctypes
import io
import unicodedata
import zipfile
import hashlib
import json
import os
from functools import lru_cache
import platform
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Set, Any

BASE_DIR = Path(os.environ.get("CSM_BASE_DIR", r"C:\CSM" if os.name == "nt" else str(Path.home() / "CSM")))
MAPS_DIR = BASE_DIR / "maps"
INSTALL_ROOT = Path(os.environ.get("CSM_INSTALL_ROOT", str(Path(__file__).resolve().parents[1])))
INSTALL_BACKUPS_DIR = Path(os.environ.get("CSM_INSTALL_BACKUPS_DIR", str(INSTALL_ROOT / "backups")))


from engine_types import Finding, Replacement
from legal_lexicon import COMMON_UPPERCASE_STOPWORDS, ROLE_ALIASES, LEGAL_TITLE_STOP_PHRASES, LEGAL_WORD_STOPLIST, COMMON_POLISH_FIRST_NAMES, deaccent_role
from legal_pii_lexicon import get_lexicon_list, alternation as lexicon_alternation
from name_variants import first_name_key as lexicon_first_name_key, first_name_variants as lexicon_first_name_variants, is_first_name_form, expand_given_names_variants
from validators import only_digits, valid_pl_iban, valid_iban, valid_idcard_pl, valid_passport_pl, valid_pesel
from security import load_config, csm_dev_mode
try:
    from bielik_detector import collect_bielik_findings
except Exception:  # pragma: no cover - optional detector must never break core CSM
    def collect_bielik_findings(text: str) -> List[Finding]:
        return []

# Repeated normalisation/diacritic stripping is hot on long Word files.
# Keep the external legal_lexicon helper but memoise it locally; all callers in
# this module use the imported name below.
deaccent_role = lru_cache(maxsize=131072)(deaccent_role)


MAX_DOCX_XML_BYTES_DEFAULT = 50_000_000
DOCX_ZIP_COMPRESSLEVEL_FAST = 1


def _open_docx_output_zip(target) -> zipfile.ZipFile:
    """Open a DOCX output zip with fast deflate.

    DOCX is a temporary/workflow artifact in CSM; users care more about keeping
    Word responsive than maximum compression ratio. Python 3.7+ supports
    compresslevel; the fallback keeps compatibility with older interpreters.
    """
    try:
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=DOCX_ZIP_COMPRESSLEVEL_FAST)
    except TypeError:  # pragma: no cover - compatibility fallback
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED)


class XmlSecurityError(Exception):
    """Raised when DOCX XML contains unsafe constructs."""


class DocxXmlTooLargeError(Exception):
    """Raised when decompressed DOCX XML exceeds the configured safety limit."""

_FORBIDDEN_DOCTYPE_RE = re.compile(rb"<!DOCTYPE\b", re.IGNORECASE)
_FORBIDDEN_ENTITY_RE = re.compile(rb"<!ENTITY\b", re.IGNORECASE)


def max_docx_xml_bytes() -> int:
    try:
        return int(load_config().get("max_docx_xml_bytes", MAX_DOCX_XML_BYTES_DEFAULT) or MAX_DOCX_XML_BYTES_DEFAULT)
    except Exception:
        return MAX_DOCX_XML_BYTES_DEFAULT


def _reject_unsafe_xml_prefix(data: bytes) -> None:
    # Scan the *full* document — not just the first 4096 bytes — so that a
    # crafted payload with DOCTYPE/ENTITY declarations past the prefix cannot
    # bypass the guard.  re.search on a bytes object is fast (no decoding needed)
    # and terminates as soon as the first forbidden token is found.
    if _FORBIDDEN_DOCTYPE_RE.search(data):
        raise XmlSecurityError("DOCX XML contains a <!DOCTYPE declaration")
    if _FORBIDDEN_ENTITY_RE.search(data):
        raise XmlSecurityError("DOCX XML contains an <!ENTITY declaration")


def _parse_docx_xml(data: bytes) -> ET.Element:
    _reject_unsafe_xml_prefix(data)
    return ET.fromstring(data)


def _parse_xml_text(xml: str | bytes) -> ET.Element:
    if isinstance(xml, bytes):
        return _parse_docx_xml(xml)
    _reject_unsafe_xml_prefix(xml.encode("utf-8", errors="ignore"))
    return ET.fromstring(xml)


def _check_docx_xml_uncompressed_limit(zf: zipfile.ZipFile) -> None:
    total_uncompressed = 0
    for info in zf.infolist():
        if info.filename.lower().endswith(".xml"):
            total_uncompressed += int(info.file_size or 0)
    limit = max_docx_xml_bytes()
    if total_uncompressed > limit:
        raise DocxXmlTooLargeError(
            "DOCX package XML zbyt duży po dekompresji "
            f"({total_uncompressed} bajtów > limit {limit} bajtów)."
        )

LATIN_UPPER = "A-ZÀ-ÖØ-ÞŁŚŻŹĆŃÓĘĄ"
LATIN_LOWER = "a-zà-öø-ÿłśżźćńóęą"
LATIN_LETTERS = f"{LATIN_UPPER}{LATIN_LOWER}"
POLISH_CAP = rf"[{LATIN_UPPER}][{LATIN_LOWER}]+"
ENTITY_WORD = rf"[{LATIN_UPPER}0-9][{LATIN_LETTERS}0-9&\-]*"
ENTITY_SEQUENCE = rf"{ENTITY_WORD}(?:(?:\s+|\s*&\s*){ENTITY_WORD}){{0,10}}"
# Contextual party/document-title matching must not cross paragraph or table-cell
# boundaries. The broad ENTITY_SEQUENCE may span newlines and virtual OOXML
# separators, which can turn generic headings such as "UMOWA NAJMU..." into
# false confidential contractor candidates.
ENTITY_SEQUENCE_LINE = rf"{ENTITY_WORD}(?:(?:[ \t\u00A0]+|[ \t\u00A0]*&[ \t\u00A0]*){ENTITY_WORD}){{0,10}}"
COMPANY_SUFFIX = (
    r"sp\.?\s*z\s*o\.?\s*o\.?|"
    # Bare "z o.o." / "z o. o." without leading "sp." — used in some company names
    # in documents where the drafter omits the "sp." abbreviation, e.g. "BIG PIŁA z o.o."
    r"z\s+o\.?\s*o\.?(?:\s+sp\.?\s*k\.?)?|"
    r"spółk(?:a|ą|ę|i)?\s+z\s+ograniczoną\s+odpowiedzialnością(?:\s+sp\.?\s*k\.?)?|"
    r"spółka\s+z\s+ograniczoną\s+odpowiedzialnością|"
    r"s\.?\s*a\.?|spółka\s+akcyjna|"
    r"p\.?\s*s\.?\s*a\.?|prosta\s+spółka\s+akcyjna|"
    r"sp\.?\s*j\.?|spółka\s+jawna|"
    r"sp\.?\s*k\.?|spółka\s+komandytowa|"
    r"s\.?\s*k\.?\s*a\.?|spółka\s+komandytowo-akcyjna|"
    r"sp\.?\s*p\.?|spółka\s+partnerska|"
    r"spółka\s+cywilna|s\.?\s*c\.?|"
    # Common foreign legal forms seen in Polish B2B contracts.
    r"gmbh|ug|ag|ltd\.?|limited|llc|inc\.?|corp\.?|corporation|sas|s\.?a\.?s\.?|sarl|s\.?a\.?r\.?l\.?|"
    r"bv|b\.?v\.?|nv|n\.?v\.?|s\.?r\.?o\.?|a\.?s\.?"
)
ORG_PREFIX = (
    r"fundacja|stowarzyszenie|spółdzielnia|bank|towarzystwo|instytut|centrum|"
    r"przedsiębiorstwo|zakład|agencja|kancelaria|spółka|firma|uczelnia|uniwersytet|"
    r"szpital|klinika|izba|samorząd|gmina|powiat|województwo|jednostka|urząd|"
    # Common Polish sole-proprietor / trade-activity abbreviations that precede a
    # trade name in invoices and B2B contracts, e.g. 'P.P.H.U. "KOWEX"',
    # 'F.H.U. Jan Kowalski', 'PPUH BUDMEX'. Optional dots and spacing handled.
    r"p\.?\s*p\.?\s*h\.?\s*u\.?|p\.?\s*h\.?\s*u\.?|f\.?\s*h\.?\s*u\.?|"
    r"p\.?\s*p\.?\s*u\.?\s*h\.?|p\.?\s*u\.?\s*h\.?"
)
ROLE_CONTEXT = (
    r"zamawiający|zamawiajacy|wykonawca|usługodawca|uslugodawca|usługobiorca|uslugobiorca|"
    r"klient|kontrahent|partner|dostawca|odbiorca|sprzedawca|kupujący|kupujacy|"
    r"licencjodawca|licencjobiorca|administrator|podmiot przetwarzający|podmiot przetwarzajacy"
)
PROJECT_KEYWORDS = r"projekt|system|platforma|aplikacja|portal|moduł|modul|narzędzie|narzedzie|program|serwis|panel|CRM|ERP|SaaS"

# Lightweight, local legal lexicon focused on contracts and pleadings.
# It is deliberately data-driven so adding new legal contexts does not require
# changing the recognizer code. The recognizers below follow a Presidio-like
# approach: pattern + legal context + validation/invalidation, without adding
# heavy ML dependencies to the installer.
LEGAL_IDENTITY_LABEL_RE = lexicon_alternation(get_lexicon_list("identity_document_labels"))
LEGAL_PERSON_LABEL_RE = lexicon_alternation(
    get_lexicon_list("person_labels_contracts")
    + get_lexicon_list("person_labels_process")
    + get_lexicon_list("birth_family_labels")
)
LEGAL_PUBLIC_AUTHORITY_RE = lexicon_alternation(get_lexicon_list("public_authority_phrases"))

STREET_PREFIX = r"(?:ul\.|ulica|al\.|aleja|pl\.|plac|os\.|osiedle|rondo)"
STREET_TOKEN = r"[A-ZŁŚŻŹĆŃÓĘĄ0-9][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9.'’:-]*"
STREET_NAME = rf"{STREET_TOKEN}(?:\s+{STREET_TOKEN}){{0,7}}?"
BUILDING_NUMBER = r"\d+[A-Za-z]?(?:\s*/\s*\d+[A-Za-z]?)?"
CITY_WORD = rf"[{LATIN_UPPER}][{LATIN_LETTERS}\-]+"
CITY_NAME = rf"{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}}(?:/{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}})?"
ADDRESS_STREET = rf"(?i:{STREET_PREFIX})\s+(?i:{STREET_NAME})\s+{BUILDING_NUMBER}"

PATTERNS: Dict[str, re.Pattern] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "DOMAIN": re.compile(r"(?i)\b(?:www\.)?(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+(?:pl|com|eu|org|net|io|ai|dev|biz|info|gov|edu)\b"),
    "URL": re.compile(r"\bhttps?://[^\s<>()]+", re.IGNORECASE),
    "IP_ADDRESS": re.compile(r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!(?:\.\d)|\d)"),
    "SECRET": re.compile(r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|ghs_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{30,})\b"),
    "PESEL": re.compile(r"(?<!\d)\d{11}(?!\d)"),
    "NIP": re.compile(r"(?<!\d)(?:\d{3}[- ]?\d{3}[- ]?\d{2}[- ]?\d{2}|\d{3}[- ]?\d{2}[- ]?\d{2}[- ]?\d{3}|\d{10})(?!\d)"),
    "REGON": re.compile(r"(?<!\d)(?:\d{14}|\d{9})(?!\d)"),
    "KRS": re.compile(r"(?i)\bKRS\s*[:\-]?\s*\d{10}\b"),
    # Direct IBAN/NRB detector. It accepts spaces, NBSP/narrow NBSP and common dash
    # separators. Direct matches are still checksum-validated in category_ok;
    # context-anchored BANK_ACCOUNT below is intentionally safer and masks even
    # fictional/test account numbers in bank-account clauses.
    "IBAN": re.compile(r"(?i)(?<![A-Z0-9])PL[\s\u00A0\u202F\-–—]*(?:\d[\s\u00A0\u202F\-–—]*){26}(?!\d)|(?<!\d)(?:\d[\s\u00A0\u202F\-–—]*){26}(?!\d)|(?<![A-Z0-9])(?!PL)[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?![A-Z0-9])"),
    "IDCARD_PL": re.compile(r"\b[A-Z]{3}\s?\d{6}\b"),
    "PASSPORT_PL": re.compile(r"\b[A-Z]{2}\s?\d{7}\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+?48[\s\-.]?)?(?:\(\d{2,3}\)[\s\-.]?)?\d{2,3}[\s\-.]?\d{2,3}[\s\-.]?\d{2,3}(?:[\s\-.]?\d{1,3})?(?!\d)"),
    # Exact street address with postcode and city. This intentionally does not mask city names alone.
    "ADDRESS_FULL": re.compile(rf"\b{ADDRESS_STREET}\s*,?\s*\d{{2}}-\d{{3}}\s+{CITY_NAME}\b"),
    # Rural/village address: locality name + building number + postcode + city, e.g. "Pustynia 84F, 39-200 Dębica".
    "ADDRESS_RURAL": re.compile(rf"\b{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}}\s+{BUILDING_NUMBER}\s*,\s*\d{{2}}-\d{{3}}\s+{CITY_NAME}\b"),
    # Company registered address in locality context: "siedzibą w Pustyni" / "siedzibę w Pustyni".
    # Named group "id" causes RegexDetector to extract only the locality token, not the full phrase.
    "ADDRESS_SIEDZIBA": re.compile(rf"(?i:\bsiedzib[aąę]\s+w\s+)(?P<id>{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}})(?=\s*,|\s*[.;)]|\s+{BUILDING_NUMBER}|$)"),
    "KW": re.compile(r"(?i)\b[A-Z]{2}[0-9A-Z]{1,2}\s*/\s*\d{8}\s*/\s*\d\b"),
    "SYGNATURA": re.compile(r"\b(?:sygn\.?\s*(?:akt)?\s*)?[IVXLCDM]{0,6}\s?[A-Z]{1,4}\s?\d{1,5}/\d{2,4}(?:/\d{1,4})?\b", re.IGNORECASE),
    "REPERTORIUM": re.compile(r"(?i)\b(?:rep(?:ertorium)?\.?\s+|repertorium\s+)(?:notarialne\s+)?[A-Z]\s*(?:nr\.?\s*)?\d{1,6}/\d{2,4}\b"),
    # Administrative-decision identifiers. Keep the label in clear text and mask
    # only the actual reference number. The earlier broad pattern could classify
    # the words "Decyzja Prezesa" as an identifier when a decision number appeared
    # later in the phrase.
    "DECYZJA_ADM": re.compile(r"(?i)\b(?:decyzj(?:a|i|ą|ę|ami|ach)\s*(?:administracyjn(?:a|ej|ą|ę|ych|ymi))?(?:\s+Prezesa(?:\s+(?:UODO|UOKiK|Urzędu\s+Ochrony\s+Danych\s+Osobowych|Urzędu\s+Ochrony\s+Konkurencji\s+i\s+Konsumentów))?)?\s*(?:nr\.?|numer|znak)|nr\s+decyzji|znak\s+decyzji)\s*[:\-]?\s*(?P<id>[A-Z0-9][A-Z0-9./\-]{2,80})\b"),
    # Court detector stops on real court-name boundaries, not at the end of a full
    # sentence. The previous broad [^,;\n]{0,80} could swallow verbs and following
    # clauses when the drafter omitted a comma after the court name.
    "COURT": re.compile(rf"\b(?:S[ąa]d(?:em|owi|u|zie)?)\s+(?:Rejonow|Okręgow|Okregow|Apelacyjn|Najwyższ|Najwyzsz)(?:ego|emu|ym|y|m)(?:\s+(?:(?:dla)\s+(?:m\.\s*st\.\s+)?{CITY_WORD}(?:[ \t\u00A0-]+{CITY_WORD}){{0,4}}|(?:w|we)\s+{CITY_WORD}(?:[ \t\u00A0-]+{CITY_WORD}){{0,3}}))?"),
    "COMPANY": re.compile(rf"\b(?:{ENTITY_SEQUENCE}[\"'”„]?\s*\.?\s+(?i:{COMPANY_SUFFIX})(?=\s|,|;|:|\.|[\"”'»\)\]]|$)|(?i:{ORG_PREFIX})\s+[\"'”„]?{ENTITY_SEQUENCE}[\"'”„]?(?:\s+{ENTITY_SEQUENCE})?)"),
    "PROJECT": re.compile(rf"\b(?i:(?:{PROJECT_KEYWORDS}))\s+(?:[A-ZŁŚŻŹĆŃÓĘĄ0-9][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9&\-]*(?:\s+[A-ZŁŚŻŹĆŃÓĘĄ0-9][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9&\-]*){{0,4}})"),
    "COMPANY_CODE": re.compile(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ0-9&.-]{2,14}\b"),
    "ADDRESS": re.compile(rf"\b{ADDRESS_STREET}(?:\s*,?\s*(?:(?i:(?:w|we))\s+)?{CITY_NAME})?\b"),
    "POSTCODE_PL": re.compile(r"\b\d{2}-\d{3}\b"),
    "PERSON": re.compile(rf"\b(?:(?i:Pan|Pani|Mec\.|radca prawny|adw\.|adwokat|pełnomocnik|pelnomocnik|prokurent|powód|pozwany|wnioskodawca|uczestnik|pracownik|pracodawca|prezes|członek zarządu|czlonek zarzadu)[ \t\u00A0]+)?{POLISH_CAP}[ \t\u00A0]+{POLISH_CAP}(?:-{POLISH_CAP})?\b"),
}

# Overlapping person detector.
# The standard PERSON regex is non-overlapping. In sentences such as
# "Usunięto Adam Nowicki" it can first see the rejected pair "Usunięto Adam"
# and then skip the real name "Adam Nowicki". This is especially dangerous in
# tracked-change deletions (w:delText), where hidden historical text must be
# anonymized as well. A lookahead-based pass finds valid overlapping name pairs.

# Professional partnership / law-firm names often contain partner surnames
# separated by commas and conjunctions before the legal suffix, e.g.
# "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j.". The generic COMPANY
# detector used to stop at the comma and leave "Głąb" visible. Keep this
# detector narrowly anchored to professional-office prefixes and a company
# suffix so ordinary comma-separated prose is not swallowed.
PROFESSIONAL_PARTNERSHIP_COMPANY_PATTERN = re.compile(
    rf"(?i)\b(?P<company>(?:kancelaria(?:\s+prawna|\s+radcowska|\s+adwokacka)?|spółka\s+partnerska|spolka\s+partnerska|biuro\s+rachunkowe|doradcy\s+podatkowi)\s+"
    rf"[{LATIN_UPPER}0-9][{LATIN_LETTERS}0-9&.\-]*(?:[ \t\u00A0]+[{LATIN_UPPER}0-9][{LATIN_LETTERS}0-9&.\-]*){{0,4}}"
    rf"(?:\s*,\s*[{LATIN_UPPER}][{LATIN_LETTERS}.\-]*(?:[ \t\u00A0]+[{LATIN_UPPER}][{LATIN_LETTERS}.\-]*){{0,3}})+"
    rf"(?:\s+i\s+[{LATIN_UPPER}][{LATIN_LETTERS}.\-]*(?:[ \t\u00A0]+[{LATIN_UPPER}][{LATIN_LETTERS}.\-]*){{0,3}})?"
    rf"\s+(?i:{COMPANY_SUFFIX})(?=\s|,|;|:|\.|[\"”'»\)\]]|$))"
)

KGL_LAW_FIRM_PATTERN = re.compile(
    rf"(?i)\b(?P<company>kancelaria\s+prawna\s+kantorowski\s*,?\s*głąb\s+i\s+wspólnicy"
    rf"(?:\s+(?:{COMPANY_SUFFIX}))?"
    rf"(?=\s|,|;|:|\.|[\"”'»\)\]]|$))"
)

# Spolka cywilna: "OSOBA1 i OSOBA2 s.c." / "OSOBA1, OSOBA2 spolka cywilna"
# Each OSOBA is 1-3 capitalized tokens. Also handles "OSOBA i Wspolnicy s.c."
# _SC_PERSON: exactly 1-3 uppercase-led tokens.
# IMPORTANT: do NOT compile with re.IGNORECASE — that would make [LATIN_UPPER]
# match lowercase letters too, causing "s" from "s.c." to be consumed as part
# of a person token.  The suffix uses inline (?i:...) for its own case logic.
_SC_PERSON = rf"[{LATIN_UPPER}][{LATIN_LETTERS}\-]+(?:[ \t][{LATIN_UPPER}][{LATIN_LETTERS}\-]+){{0,2}}"
# Partnership suffix: s.c. / spółka cywilna / Sp.j. / Spółka jawna / Sp.p. / Spółka partnerska
_SC_SUFFIX_IC = (
    r"(?i:sp[o\xf3][lł]k[aąei]\s+cywiln[aą]|s\.?\s*c\.?|"
    r"sp\.?\s*j\.?|sp[o\xf3][lł]ka\s+jawna|"
    r"sp\.?\s*p\.?|sp[o\xf3][lł]ka\s+partnerska)"
)
# Optional "z siedzibą w CITY" appended to the company name in legal documents.
_CITY_WORD = rf"[{LATIN_UPPER}][{LATIN_LETTERS}\-]+"
_SC_SIEDZIBA = rf"(?:\s+z\s+siedzib[aą]\s+w\s+{_CITY_WORD}(?:\s+{_CITY_WORD}){{0,2}})?"
CIVIL_PARTNERSHIP_PATTERN = re.compile(
    rf"(?P<company>"
    rf"(?:{_SC_PERSON})"                                                  # first partner
    rf"(?:"
    rf"(?:\s*,\s*|\s+[Ii]\s+)"                                            # comma or "i/I"
    rf"(?:[Ww]sp[oó]lni(?:cy|ka|kami|kom)|{_SC_PERSON})"                 # next partner or "Wspólnicy"
    rf")+"
    rf"\s+{_SC_SUFFIX_IC}"                                                # legal form suffix
    rf"{_SC_SIEDZIBA}"                                                    # optional: z siedzibą w CITY
    r'(?=\s|,|;|:|\.|["»\)\]]|$)'
    r")"
)

# Module-level helpers for partnership name token extraction (compiled once).
_PARTNER_TOKEN_RE = re.compile(
    r"\b([A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]{1,}(?:-[A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]+)?)\b"
)
_PARTNER_SKIP_WORDS = frozenset({
    "Kancelaria", "Prawna", "Radcowska", "Adwokacka", "Notarialna",
    "Spółka", "Spolka", "Biuro", "Rachunkowe", "Doradcy", "Podatkowi",
    "Wspólnicy", "Wspolnicy", "Partnerska", "Cywilna",
})
# Pre-filter: civil-partnership regex only runs when a partnership marker is present.
# "i Wspólnicy" / "i Wspolnicy" is the key indicator — it only appears in
# partnership firm names. Bare "Sp.j." is NOT used as a trigger to avoid
# running the expensive CIVIL_PARTNERSHIP_PATTERN on every Polish legal document
# that merely mentions any Sp.j. company.
_SC_MARKER_RE = re.compile(
    r"s\.?\s*c\.?|"
    r"sp[o\xf3][lł]k\w*\s+cywil|"
    r"i\s+[Ww]sp[o\xf3]lni|"
    r"[Ww]sp[o\xf3]lni\w+\s+[Ss]p",
    re.IGNORECASE
)

PERSON_OVERLAP_PATTERN = re.compile(
    rf"(?=\b((?:(?i:Pan|Pani|Mec\.|radca prawny|adw\.|adwokat|pełnomocnik|pelnomocnik|prokurent|powód|pozwany|wnioskodawca|uczestnik|pracownik|pracodawca|prezes|członek zarządu|czlonek zarzadu)[ \t\u00A0]+)?{POLISH_CAP}[ \t\u00A0]+{POLISH_CAP}(?:-{POLISH_CAP})?\b))"
)

# Context-anchored person candidates for Polish legal documents.
# The generic PERSON recognizer is intentionally conservative and checks first names
# against a small lexicon. Deeds and contracts often contain inflected or foreign
# names next to high-confidence markers (PESEL, zamieszkał/a/y, małżonek, po
# zmianie imienia i nazwiska). These recognizers use the context as evidence,
# similar to Presidio-style pattern recognizers with context, without making every
# Title Case pair a person.
PERSON_NAME_LOOSE = rf"{POLISH_CAP}(?:[ \t\u00A0]+{POLISH_CAP}){{1,3}}(?:-{POLISH_CAP})?"
# Inflected professional / procedural titles that often precede personal names
# in Polish legal documents.  Keep this in one place so context recognizers,
# title stripping and role-based patterns stay aligned.
LEGAL_PROFESSIONAL_TITLE = (
    r"Pan|Pana|Panu|Panem|Pani|Panią|Pania|"
    r"Mec\.?|mecenas|"
    r"adw\.?|adwokat(?:a|owi|em|ką|ka|kę|ce|ach|ami)?|"
    r"radc(?:a|y|ę|e|ą|om|ami)?\s+prawn(?:y|ego|emu|ym|ą|a|ych|ymi|ej)|"
    r"r\.\s*pr\.|"
    r"notariusz\w*|komornik\w*|mediator\w*|"
    r"interwenient\w*|pokrzywdzon\w*|oskarżon\w*|oskarzon\w*|"
    r"pełnomocni\w*|pelnomocni\w*|prokurent\w*|"
    r"biegł\w*|biegl\w*|świadk\w*|swiadk\w*|"
    r"tłumacz\w*\s+przysięgł\w*|tlumacz\w*\s+przysiegl\w*"
)
LEGAL_PROFESSIONAL_TITLE_PREFIX = rf"(?i:(?:{LEGAL_PROFESSIONAL_TITLE})(?:[ \t\u00A0]+(?:{LEGAL_PROFESSIONAL_TITLE})){{0,1}})[ \t\u00A0]+"
PERSON_CONTEXT_PREFIXED_PATTERN = re.compile(
    rf"(?P<prefix>(?:^|[\n\r]|(?<!\d)\d+\.\s*|[;:]\s*))(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:\([^\)]{{0,160}}\)\s*)?,?\s*(?:PESEL\b|zamieszkał|zamieszkała|zamieszkały|zamieszkałą|zamieszkal|zamieszkala|zamieszkaly|zamieszkala))",
    re.IGNORECASE | re.MULTILINE,
)
PERSON_AFTER_RELATION_PATTERN = re.compile(
    rf"(?i)\b(?:mężem|mezem|żoną|zona|małżonkiem|malzonkiem|małżonką|malzonka|partnerem|partnerką|partnerka|synem|córką|corka|ojcem|matką|matka|bratem|siostrą|siostra|spadkobiercą|spadkobierca|pełnomocnikiem|pelnomocnikiem)\s+(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:\(|,|—|–|-|\s+na\b|\s+w\b|\s+do\b|\s+PESEL\b|\s+zamieszkał|\s+zamieszkała|\s+zamieszkały|$))"
)
PERSON_RENAMED_PATTERN = re.compile(
    rf"(?i)\b(?:po\s+zmianie\s+imienia\s+i\s+nazwiska|poprzednio|uprzednio|obecnie)\s*[:\-–]?\s*(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:\)|,|;|—|–|-|\s+PESEL\b|$))"
)
PERSON_TITLE_CONTEXT_PATTERN = re.compile(
    rf"\b{LEGAL_PROFESSIONAL_TITLE_PREFIX}(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|;|\(|\)|—|–|-|\s+PESEL\b|\s+zamieszkał|\s+zamieszkała|\s+zamieszkały|\s+wniósł|\s+wniosła|\s+złożył|\s+złożyła|\s+podpisał|\s+podpisała|\s+ustanowiono|\s+został|\s+została|$))"
)

# Single-token surname/name after a legal title. This covers Polish legal text
# such as "Pani Mucha" or "Pan Pustynia", where the token may also be an
# ordinary word. It is intentionally title-anchored, so bare occurrences like
# "mucha była w pokoju" are not masked.
PERSON_TITLE_SINGLE_TOKEN_PATTERN = re.compile(
    rf"\b{LEGAL_PROFESSIONAL_TITLE_PREFIX}(?P<name>{POLISH_CAP})(?=\s*(?:,|;|\.|\(|\)|—|–|-|\s+PESEL\b|\s+zamieszkał|\s+zamieszkała|\s+zamieszkały|\s+złożył|\s+złożyła|\s+wniósł|\s+wniosła|\s+oświadczył|\s+oświadczyła|\s+[{LATIN_LOWER}]|$))"
)
LOWERCASE_LEGAL_PERSON_PATTERN = re.compile(
    rf"\b{LEGAL_PROFESSIONAL_TITLE_PREFIX}(?P<name>[{LATIN_LOWER}]{{2,}}[ \t\u00A0]+[{LATIN_LOWER}]{{2,}}(?:-[{LATIN_LOWER}]{{2,}})?)(?=\s*(?:,|;|\.|\)|—|–|-|PESEL\b|adres\b|tel\.?|e-mail|$))"
)

# Additional high-confidence legal-context person recognizers. These are anchored
# to strong contextual markers (PESEL, birth data, role suffixes, representation)
# and therefore allow inflected/foreign names which are not present in the small
# first-name lexicon. They intentionally do not turn every Title Case pair into PII.
PERSON_BEFORE_ID_OR_BIRTH_PATTERN = re.compile(
    rf"(?i)\b(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-)\s*(?:PESEL\b|ur\.|urodzon|zamieszkał|zamieszkała|zamieszkały|seria\s+i\s+numer\s+dowodu|dow[oó]d\s+osobisty))"
)
PERSON_ROLE_SUFFIX_PATTERN = re.compile(
    # \w* after each role word catches Polish inflected forms:
    # Pełnomocnika (gen.), Pełnomocnikowi (dat.), Prokurenta (gen.), Dyrektora (gen.) etc.
    rf"(?i)\b(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-)\s*(?:Prezes\w*\s+Zarządu\w*|Członek\w*\s+Zarządu\w*|Czlonek\w*\s+Zarzadu\w*|Prokurent\w*|Wspólnik\w*|Wspolnik\w*|Kierownik\w*|Dyrektor\w*|Manager\w*|Koordynator\w*|Przedstawiciel\w*|Pełnomocnik\w*|Pelnomocnik\w*)\b)"
)
PERSON_AFTER_REPRESENTED_BY_PATTERN = re.compile(
    rf"(?i)\b(?:reprezentowan\w*|działając\w*|dzialajac\w*|podpisan\w*\s+przez|przez)\s+(?:{LEGAL_PROFESSIONAL_TITLE_PREFIX})?(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-|\s+zwan|\s+adres|\s+NIP\b|\s+PESEL\b|\s+wniósł|\s+wniosła|\s+złożył|\s+złożyła|\s+podpisał|\s+podpisała|\.|$))"
)
PERSON_AT_PARTY_ROW_PATTERN = re.compile(
    rf"(?im)(?:^|[\n\r]|(?<!\d)\d+\.\s*)\s*(?P<name>{PERSON_NAME_LOOSE})(?=\s+(?:[A-ZŁŚŻŹĆŃÓĘĄ0-9][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9&\-]+\s+){{0,5}}(?:adres\b|NIP\b|reprezentowan|zwany|zwana|prowadząc|prowadzac))"
)
# Contextual identity-document recognizers. Real Polish ID cards use checksum,
# but legal/test templates often use fictitious values such as AZL 000000. When
# the value is next to an explicit "dowód osobisty / seria" label, it must be
# anonymized even if checksum validation fails.
IDCARD_PL_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:seria\s+i\s+numer\s+dowodu\s+osobistego|nr\s+dowodu\s+osobistego|numer\s+dowodu\s+osobistego|dow[oó]d\s+osobisty\s*(?:seria)?|dowodem\s+osobistym\s*(?:seria)?|dowodu\s+osobistego\s*(?:seria)?)\s*[:\-]?\s*(?P<id>[A-Z]{3}\s*(?:nr\.?\s*)?\d{6})\b"
)
# Broader legal-context identity-document detector for tables/pleadings. It can
# see across OOXML table-cell separators (private-use U+E000) and masks only the
# actual series+number value. This covers rows like:
# "Dokumentu tożsamości | dowód osobisty seria AZL 000000 ...".
IDCARD_PL_LEGAL_CONTEXT_PATTERN = re.compile(
    rf"(?i)(?:\b(?:{LEGAL_IDENTITY_LABEL_RE})\b)[\s\S]{{0,180}}?(?P<id>[A-Z]{{3}}(?:\s|\ue000)*(?:nr\.?\s*)?\d{{6}})\b"
)
# Contextual legal/administrative identifiers used in contracts, deeds and pleadings.
# They intentionally rely on labels/context so ordinary dates, paragraph numbers,
# amounts or attachment numbers are not masked as identifiers.
BDO_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:numer\s+rejestrowy\s+BDO|nr\.?\s*BDO|BDO)\s*[:#nr\.\- ]{0,12}(?P<id>\d{9})\b"
)
CEIDG_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:identyfikator\s+wpisu\s+CEIDG|numer\s+wpisu\s+w\s+CEIDG|numer\s+CEIDG|CEIDG[-\s]?ID)\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9./_\-]{5,80})\b"
)
CASE_REF_CONTEXT_PATTERN = re.compile(
    # Keep internal dots/slashes/dashes inside references such as ABC.123.4.2026.
    # Only the label is case-insensitive; the reference body must look like an
    # identifier, not ordinary sentence text after a final dot.
    r"(?i:\b(?:sygn\.?\s*(?:akt)?|sygnatura\s+akt|nr\.?\s+sprawy|numer\s+sprawy|znak\s+sprawy|znak\s+pisma|sprawa\s+nr\.?)\s*[:\- ]{0,8})(?P<id>[A-ZĄĆĘŁŃÓŚŹŻ0-9][A-ZĄĆĘŁŃÓŚŹŻ0-9./_\-]*(?: [A-ZĄĆĘŁŃÓŚŹŻ0-9][A-ZĄĆĘŁŃÓŚŹŻ0-9./_\-]*){0,8})(?=\s*(?:,|;|\n|$)|\.(?:\s|$))"
)
PERMIT_LICENSE_CONTEXT_PATTERN = re.compile(
    # Permit/licence IDs are label-anchored. Administrative decisions are handled
    # by DECYZJA_ADM so that decision numbers keep their own placeholder family.
    r"(?i)\b(?:zezwolenie|pozwolenie|koncesja|licencja|zgoda\s+administracyjna)\s*(?:nr\.?|numer|znak)?\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
VEHICLE_VIN_PATTERN = re.compile(r"(?i)\b(?:VIN|nr\.?\s+VIN|numer\s+VIN)\s*[:\- ]{0,8}(?P<id>[A-HJ-NPR-Z0-9]{17})\b")
VEHICLE_REG_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:nr\.?\s+rejestracyjny|nr\.?\s+rej\.?|numer\s+rejestracyjny|numer\s+rej\.?|tablic(?:a|y)\s+rejestracyjn(?:a|e)|pojazd\s+o\s+nr\.?\s+rej\.?)\s*[:\- ]{0,8}(?P<id>[A-Z]{1,3}\s?[A-Z0-9]{4,6})\b"
)
VEHICLE_ENGINE_BODY_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:nr\.?\s+silnika|numer\s+silnika|nr\.?\s+nadwozia|numer\s+nadwozia)\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9\-]{5,30})\b"
)
PASSPORT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:paszport|nr\.?\s+paszportu|numer\s+paszportu|passport(?:\s*(?:no\.?|number))?)\s*(?:nr\.?|numer|no\.?|number)?\s*[:#\- ]{0,8}(?P<id>[A-Z0-9]{1,3}\s?[A-Z0-9]{6,9})\b"
)
RESIDENCE_CARD_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:karta\s+pobytu|nr\.?\s+karty\s+pobytu|numer\s+karty\s+pobytu)\s*(?:nr\.?|numer)?\s*[:\- ]{0,8}(?P<id>[A-Z]{1,3}\s?\d{6,9}|PL[-\s]?[A-Z0-9]{6,12})\b"
)
DRIVING_LICENSE_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:prawo\s+jazdy|nr\.?\s+prawa\s+jazdy|numer\s+prawa\s+jazdy)\s*(?:nr\.?|numer)?\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9/\- ]{4,30})\b"
)
PROF_LICENSE_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:PWZ|prawo\s+wykonywania\s+zawodu|numer\s+wpisu\s+(?:radcy\s+prawnego|adwokata|doradcy\s+podatkowego|doradcy\s+restrukturyzacyjnego)|nr\.?\s+licencji\s+zawodowej)\s*(?:nr\.?|numer)?\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9/\-]{3,30})\b"
)
PROPERTY_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:działk(?:a|i|ę|e)\s*(?:ewidencyjn(?:a|ej|ą|ych))?\s*(?:nr\.?|numer)?|identyfikator\s+działki|obręb(?:ie)?\s*(?:ewidencyjn(?:y|ym))?|jednostka\s+ewidencyjna)\s*[:\- ]{0,8}(?P<id>[0-9]{1,8}(?:/[0-9]{1,8})?|[0-9]{6}_[0-9](?:\.[0-9]{4})?(?:\.[0-9]{1,8}(?:/[0-9]{1,8})?)?)\b"
)
EDELIVERY_EPUAP_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:adres\s+ePUAP|identyfikator\s+ePUAP|skrytka\s+ePUAP|adres\s+do\s+doręczeń\s+elektronicznych|adres\s+do\s+doreczen\s+elektronicznych|AE:)\s*[:\- ]{0,8}(?P<id>(?:/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)|(?:AE:)?PL[-A-Z0-9]{6,30}|[A-Za-z0-9_.-]{5,40})\b"
)
POLICY_CLAIM_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:polisa(?:\s+OC)?(?:\s*(?:nr\.?|numer))?|nr\.?\s+polisy|numer\s+polisy|szkoda|numer\s+szkody|nr\.?\s+szkody|numer\s+roszczenia|nr\.?\s+roszczenia)\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,50})\b"
)
SHIPMENT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:list\s+polecony|list\s+przewozowy(?:\s*(?:nr\.?|numer))?|nr\.?\s+listu\s+przewozowego|numer\s+przesyłki|numer\s+przesylki|tracking|przesyłka(?:\s+[A-Z0-9]{2,20})?\s+nr|przesylka(?:\s+[A-Z0-9]{2,20})?\s+nr|przesyłka(?:\s+[A-Z0-9]{2,20})?|przesylka(?:\s+[A-Z0-9]{2,20})?)\s*[:\- ]{0,8}(?P<id>[A-Z0-9][A-Z0-9./_\-]{5,50})\b"
)
PROJECT_ORDER_CONTEXT_PATTERN = re.compile(
    # Public contract registers and procurement contracts commonly use complex
    # references such as "Umowa nr BRPO-WZP.261.123.2026". Treat these as
    # project/contract identifiers only when anchored to a document label.
    r"(?i)\b(?:zamówienie|zamowienie|zlecenie|umowa|kontrakt|nr\.?\s+umowy|nr\.?\s+kontraktu|nr\.?\s+zamówienia|nr\.?\s+zamowienia|nr\.?\s+zlecenia|numer\s+umowy|numer\s+kontraktu|numer\s+zamówienia|numer\s+zamowienia|numer\s+zlecenia|projekt|ticket|zgłoszenie|zgloszenie|identyfikator\s+pomocy|numer\s+referencyjny\s+środka\s+pomocowego|numer\s+referencyjny\s+srodka\s+pomocowego)\s*(?:nr\.?|numer|ID)?\s*[:\- ]{0,8}(?P<id>(?:[A-ZĄĆĘŁŃÓŚŹŻ]{1,20}\.\d{2,20})|(?:[A-ZĄĆĘŁŃÓŚŹŻ]{2,20}[-/][A-Z0-9ĄĆĘŁŃÓŚŹŻ][A-Z0-9ĄĆĘŁŃÓŚŹŻ./_\-]{2,80})|(?:[A-ZĄĆĘŁŃÓŚŹŻ]{2,20}(?:[-.][A-Z0-9ĄĆĘŁŃÓŚŹŻ]{2,20}){2,8})|(?:\d{4,20}))\b"
)

# Internet/IT identifiers frequently present in B2B, e-commerce and process
# exhibits. They are label/context anchored where broad detection would cause
# too many false positives, and direct where the format is unambiguous (IP).
DOMAIN_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:domena|subdomena|adres\s+strony|adres\s+www|strona\s+internetowa|panel\s+administracyjny|panel\s+klienta|adres\s+panelu)\s*[:\-–— ]{0,12}(?P<id>(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,})\b"
)
LOGIN_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:login(?:u|em)?(?:\s+(?:administratora|użytkownika|uzytkownika))?|nazwa\s+użytkownika|nazwa\s+uzytkownika|konto\s+administratora|konto\s+użytkownika|konto\s+uzytkownika|identyfikator\s+użytkownika|identyfikator\s+uzytkownika|user\s*id|username)(?:\s+(?:panelu|systemu|aplikacji|portalu|konta))?\s*(?:[:=\-–—]+|\s+)\s*(?P<id>[A-Za-z0-9._@\-]{3,80})\b"
)
API_SECRET_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:token\s+API|klucz\s+API|api\s*key|access\s*token|client[_\s-]?secret|client[_\s-]?id|secret|hasło|haslo|password|klucz\s+SSH)\s*[:=\-–— ]{0,12}(?P<id>[A-Za-z0-9_./+=:@\-]{8,160})\b"
)
ACCOUNT_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:Google\s+Analytics|GA4|Meta\s+Pixel|Facebook\s+Pixel|Allegro|BaseLinker|Baselinker|Stripe|PayU|Przelewy24|P24|CRM|konto\s+reklamowe|identyfikator\s+klienta|ID\s+klienta|ID\s+konta|ID\s+kampanii)\s*(?:ID|nr\.?|numer|identyfikator)?\s*[:\-–— ]{0,12}(?P<id>(?:G-[A-Z0-9]{6,20}|UA-\d{4,12}-\d+|[A-Z]{2,10}[-_/]?[A-Z0-9][A-Z0-9._/\-]{3,80}|\d{5,30}))\b"
)
REPOSITORY_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:repozytorium|repozytorium\s+GitHub|GitHub|GitLab|Bitbucket)\s*[:\-–— ]{0,12}(?P<id>(?:https?://[^\s<>()]+|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))\b"
)
FINANCIAL_DOC_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:faktur(?:a|y|ze)?|proforma|nota\s+księgowa|nota\s+ksiegowa|ID\s+transakcji|identyfikator\s+płatności|identyfikator\s+platnosci|numer\s+płatności|numer\s+platnosci|terminal\s+nr|numer\s+terminala)\s*(?:VAT\s*)?(?:nr\.?|numer|ID)?\s*[:\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
VAT_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:VAT\s*UE|NIP\s*UE|EU\s*VAT|VAT\s*ID|nr\.?\s+VAT\s+UE|numer\s+VAT\s+UE)\s*[:#\-–— ]{0,12}(?P<id>[A-Z]{2}\s?[A-Z0-9]{8,12})\b"
)
MEDICAL_RECORD_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:nr\.?\s+historii\s+choroby|numer\s+historii\s+choroby|nr\.?\s+dokumentacji\s+medycznej|numer\s+dokumentacji\s+medycznej|ID\s+pacjenta|identyfikator\s+pacjenta|numer\s+pacjenta)\s*[:#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
EMPLOYEE_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:nr\.?\s+kadrowy|numer\s+kadrowy|identyfikator\s+pracownika|ID\s+pracownika|employee\s*ID|staff\s*ID)\s*[:#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
CUSTOMER_VENDOR_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:(?:numer|nr\.?|identyfikator|ID)\s+(?:klienta|kontrahenta|dostawcy|odbiorcy|customer|vendor)|(?:customer|vendor)\s*ID)\s*[:#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
# Public registers and business platforms often expose identifiers which are not
# classic Polish NIP/KRS/REGON values but still identify a specific business or
# transaction set: EORI, LEI, D-U-N-S, GLN and technical tenant/vendor ids.
BUSINESS_ID_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:EORI|LEI|D[-\s]?U[-\s]?N[-\s]?S|DUNS|GLN|tenant[_\s-]?id|vendor[_\s-]?id|supplier[_\s-]?id|merchant[_\s-]?id)\s*(?:nr\.?|numer|ID)?\s*[:=#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{4,80})\b"
)
PROCUREMENT_NOTICE_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:post[ęe]powanie|postepowanie|nr\.?\s+post[ęe]powania|numer\s+post[ęe]powania|og[łl]oszenie\s+(?:BZP|TED|TED/S)|nr\.?\s+og[łl]oszenia\s+(?:BZP|TED)|BZP|TED)\s*(?:nr\.?|numer|ID)?\s*[:#\-–— ]{0,12}(?P<id>(?:\d{4}/BZP\s*\d{5,12}/\d{2})|(?:\d{4}/S\s*\d{1,4}[-–—]\d{3,9})|(?:[A-ZĄĆĘŁŃÓŚŹŻ]{1,20}[./_\-]\d[A-Z0-9ĄĆĘŁŃÓŚŹŻ./_\-]{2,80}))\b"
)

# Polish bank account / IBAN / NRB in legal-financial clauses. This detector is
# deliberately context-anchored: test/fictitious bank accounts often fail IBAN
# checksum validation but should still be pseudonymized before sending a document
# to an AI system. It handles spaces, NBSP/narrow NBSP and dash-separated groups.
BANK_ACCOUNT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:rachunek(?:\s+(?:bankowy|płatniczy|platniczy|do\s+wpłat|do\s+wplat|do\s+przelewu))?|rachunku(?:\s+(?:bankowego|płatniczego|platniczego|do\s+wpłat|do\s+wplat|do\s+przelewu))?|nr\.?\s+rachunku|numer\s+rachunku|konto(?:\s+bankowe)?|nr\.?\s+konta|numer\s+konta|IBAN|NRB|przelew(?:u)?|do\s+przelewu|bank)\s*(?:nr\.?|numer)?\s*[:=\-–— ]{0,16}(?P<id>(?:PL[\s\u00A0\u202F\-–—]*)?(?:\d[\s\u00A0\u202F\-–—]*){26})(?!\d)"
)
# Bank account number separated from the label by an owner's name or role,
# e.g. "Rachunek bankowy Jana Nowaka: PL ...". The label anchors the
# match, while the captured value is only the account number. This avoids
# leaking bank identifiers in legal payment clauses even when the example
# number is fictional and fails a real checksum.
BANK_ACCOUNT_OWNER_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:rachunek(?:\s+(?:bankowy|płatniczy|platniczy|do\s+wpłat|do\s+wplat|do\s+przelewu))?|rachunku(?:\s+(?:bankowego|płatniczego|platniczego|do\s+wpłat|do\s+wplat|do\s+przelewu))?|nr\.?\s+rachunku|numer\s+rachunku|konto(?:\s+bankowe)?|nr\.?\s+konta|numer\s+konta|IBAN|NRB|przelew(?:u)?|do\s+przelewu|bank)\b[^\n\r\ue000]{0,120}?[:=\-–— ]{1,16}(?P<id>(?:PL[\s\u00A0\u202F\-–—]*)?(?:\d[\s\u00A0\u202F\-–—]*){26})(?!\d)"
)

# Role-based person detection for pleadings and legal exhibits. This extends
# generic contact detection to third parties who are not contract parties:
# attorney, witness, expert, notary, bailiff, trustee, curator, translator etc.
LEGAL_ROLE_PERSON_AFTER_PATTERN = re.compile(
    rf"(?i)\b(?:pełnomocni\w*|pelnomocni\w*|substytut\w*|świadk\w*|swiadk\w*|biegł\w*|biegl\w*|biegły\s+sądowy|biegly\s+sadowy|notariusz\w*|komorni\w*|syndyk\w*|nadzorca\s+sądow\w*|nadzorca\s+sadow\w*|kurator\w*|tłumacz\s+przysięgł\w*|tlumacz\s+przysiegl\w*|mediator\w*|prokurator\w*|oskarżyciel\w*|oskarzyciel\w*|podwykonawc\w*|przedstawiciel\s+ustawow\w*|opiekun\s+prawny\w*)\s*(?:[a-ząćęłńóśźż]{3,30}\s+){{0,3}}(?:był|była|jest|został|została|ustanowiono|w osobie)?\s*(?:{LEGAL_PROFESSIONAL_TITLE_PREFIX})?[:\-–—,]?\s*(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|;|\.|\)|—|–|-|PESEL\b|adres\b|tel\.?|e-mail|wniósł|wniosła|złożył|złożyła|ustanowiono|został|została|$))"
)
LEGAL_ROLE_PERSON_BEFORE_PATTERN = re.compile(
    # \w* catches Polish inflected forms: pełnomocnika (gen.), świadka, biegłego etc.
    rf"(?i)\b(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-)\s*(?:pełnomocni\w*|pelnomocni\w*|substytut\w*|świadk\w*|swiadk\w*|biegł\w*|biegl\w*|notariusz\w*|komorni\w*|syndyk\w*|nadzorca\s+sądow\w*|kurator\w*|tłumacz\w*\s+przysięgł\w*|mediator\w*|prokurator\w*|podwykonawc\w*|przedstawiciel\w*\s+ustawow\w*|opiekun\w*\s+prawny\w*)\b)"
)

# Context-aware person detector for legal tables and procedural documents. The
# label may be in the left table cell and the name in the right cell, separated
# by U+E000. The captured value is just the name, not the label.
PERSON_LEGAL_ROW_PATTERN = re.compile(
    rf"(?i)(?:\b(?:{LEGAL_PERSON_LABEL_RE})\b)[\s\ue000:;,.\-–—]*?(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-|\(|PESEL\b|ur\.|urodzon|Prezes|Członek|Czlonek|Kierownik|Dyrektor|adres\b|NIP\b|$))"
)
# Full name immediately followed by a legal/person identifier context, including
# placeholders produced in a previous pass ([PESEL_7], [DATE_1]). Useful when a
# paragraph says: "Bernadetta Worosz, PESEL [PESEL_7]".
PERSON_BEFORE_LEGAL_MARKER_PATTERN = re.compile(
    rf"(?i)\b(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-)?\s*(?:PESEL\b|\[PESEL_\d+\]|ur\.|urodzon|\[DATE_\d+\]|zamieszkał|zamieszkała|zamieszkały|będąc|bedac|będąca|bedaca))"
)
# Company codes embedded in contract numbers, e.g. NOVUS/OMNITEX/B2B/05/2026.
# In legal documents these often encode party names and should be masked, while
# B2B/B2C and numeric/date segments are ignored.
CONTRACT_NUMBER_COMPANY_TOKEN_PATTERN = re.compile(
    r"(?i)\b(?:numer\s+umowy|nr\s+umowy|umowa\s+nr)[\s\ue000]*[:\-]?[\s\ue000]*(?P<num>[A-ZĄĆĘŁŃÓŚŹŻ0-9][A-ZĄĆĘŁŃÓŚŹŻ0-9./\-]{5,120})"
)
ORG_CONTEXT_NAME_PATTERN = re.compile(
    rf"(?i)\b(?:klienta|kontrahenta|podmiotu|firmy|spółki|spolki|zamawiającego|zamawiajacego|wykonawcy|administratora\s+danych)\s+(?P<company>{ENTITY_SEQUENCE_LINE})(?=[\s\ue000]*(?:,|;|\.|\)|\ue000|$))"
)

DOCUMENT_TITLE_COMPANY_PATTERN = re.compile(
    rf"(?i)(?:^|[\n\r\ue000])\s*(?:umowa|kontrakt|projekt)\s+(?:z|zawarta\s+z|na\s+rzecz|dla)\s+(?P<company>{ENTITY_SEQUENCE_LINE}\s+(?:{COMPANY_SUFFIX}))(?=[\s\ue000]*(?:,|;|\.|\)|\ue000|$))"
)

# CEIDG / sole-proprietor business names often combine a trade name with the
# owner's personal name. In legal anonymization the whole firm line is
# identifying, and short trade names used later (AMZ, Omnitex) must also be
# masked. The pattern is intentionally label/context anchored.

# Legal/process party company names without explicit company suffix.
# Examples from pleadings: "w imieniu Klienta - OLIMP LABORATORIES" or
# "Powod: OLIMP LABORATORIES z siedziba ...". These are context-anchored
# so ordinary uppercase legal headings are not masked as companies.
PARTY_CONTEXT_COMPANY_PATTERN = re.compile(
    rf'(?i:\b(?:pow[oó]d\w*|pozwan\w*|wierzyciel\w*|d[łl]u[żz]nik\w*|klient\w*|kontrahent\w*|reprezentuj[ąa]c\w*|w\s+imieniu\s+(?:klienta|powoda|pozwanego|wierzyciela|d[łl]u[żz]nika))\b)[\s\ue000:;,.\-–—"„”\'=]{{0,40}}(?P<company>[A-ZĄĆĘŁŃÓŚŹŻ0-9][A-ZĄĆĘŁŃÓŚŹŻ0-9& ._\-]{{3,80}})(?=\s*["„”\']?\s*(?:,|;|\)|\.|z\s+siedzib|NIP\b|REGON\b|KRS\b|[a-ząćęłńóśźż]|$))'
)

# Uppercase legal party name after the procedural phrase "przeciwko".
# Kept separate from PARTY_CONTEXT_COMPANY_PATTERN so "Powód Jan Nowak wnosi
# pozew przeciwko OLIMP LABORATORIES" does not get swallowed from the word
# "Powód" up to the final dot.
AGAINST_CONTEXT_COMPANY_PATTERN = re.compile(
    rf'(?i:\bprzeciwko\b)[\s\ue000:;,.\-–—"„”\']{{0,20}}(?P<company>[A-ZĄĆĘŁŃÓŚŹŻ0-9][A-ZĄĆĘŁŃÓŚŹŻ0-9& ._\-]{{3,80}})(?=\s*["„”\']?\s*(?:,|;|\)|\.|z\s+siedzib|NIP\b|REGON\b|KRS\b|[a-ząćęłńóśźż]|$))'
)

CEIDG_BUSINESS_NAME_PATTERN = re.compile(
    rf"(?i)\b(?:firma\s+przedsiębiorcy(?:\s+po\s+zmianie)?|firma\s+przedsiebiorcy(?:\s+po\s+zmianie)?|pod\s+firmą|pod\s+firma|pod\s+nazwą|pod\s+nazwa|prowadzą(?:c(?:ym|a|y|ą))?\s+działalność(?:\s+gospodarczą)?\s+pod\s+(?:firmą|nazwą)|prowadz(?:ac(?:ym|a|y|aca))?\s+dzialalnosc(?:\s+gospodarcza)?\s+pod\s+(?:firma|nazwa))[\s\ue000:;,\-–—]{{0,20}}(?P<company>[A-ZĄĆĘŁŃÓŚŹŻ][^,.;\n\ue000]{{2,120}})"
)
# Party/contact labels in appendices and B2B tables. They may be followed by a
# table-cell separator instead of a colon.
PERSON_CONTACT_LABEL_ROW_PATTERN = re.compile(
    rf"(?i)\b(?:zamawiający\s*-\s*(?:reprezentacja|projekt|finanse|bezpieczeństwo)|zamawiajacy\s*-\s*(?:reprezentacja|projekt|finanse|bezpieczenstwo)|wykonawca\s*-\s*(?:osoba\s+główna|osoba\s+glowna|rozliczenia|zastępstwo\s+awaryjne|zastepstwo\s+awaryjne)|osoba\s+akceptująca\s+raport|osoba\s+akceptujaca\s+raport|osoba\s+kontaktowa\s+do\s+spraw\s+rozliczeń|osoba\s+kontaktowa\s+do\s+spraw\s+rozliczen)[\s\ue000:;,\-–—]{{0,40}}(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|—|–|-|PESEL\b|tel\.?|telefon|e-mail|email|$))"
)
# Generic but conservative multi-part person names: first + optional middle
# first names + surname. This catches Polish legal signatures like
# "Anna Maria Zielińska" and "Michał Adam Nowacki" without turning arbitrary
# Title Case phrases into persons, because validation still requires a known
# first name.
PERSON_MULTIPART_KNOWN_PATTERN = re.compile(
    rf"\b(?P<name>{PERSON_NAME_LOOSE})\b"
)
# DOCX table/cell extraction sometimes concatenates adjacent cells/runs without
# a space (e.g. "Prezes ZarząduAdam Nowak"). Detect a known person name that
# starts immediately after a lower-case letter; validation below restricts this
# to real first-name candidates.
PERSON_CONCATENATED_AFTER_TEXT_PATTERN = re.compile(
    rf"(?<=[a-ząćęłńóśźż])(?P<name>{PERSON_NAME_LOOSE})(?=\s*(?:,|;|\.|—|–|-|\ue000|\n|$))"
)
# Abbreviated forename + surname, e.g. "J. Kowalski", "A.-M. Nowak-Kowalska".
# This is gap C from the 2026-07-01 verification report. The initial is a single
# uppercase letter followed by a dot; the surname is a normal capitalised word
# with a lower-case tail (so acronym sequences and lowercase abbreviations such
# as "ul.", "nr", "art." — which are multi-letter — are not caught). Validation
# in the detector requires a plausible surname.
INITIAL_SURNAME_PATTERN = re.compile(
    rf"(?<![{LATIN_LETTERS}.])(?P<initial>[{LATIN_UPPER}]\.(?:[ \t ]*[{LATIN_UPPER}]\.)?)[ \t ]*"
    rf"(?P<surname>[{LATIN_UPPER}][{LATIN_LOWER}]+(?:-[{LATIN_UPPER}][{LATIN_LOWER}]+)?)"
    rf"(?![{LATIN_LETTERS}])"
)
# Parent-name rows contain first names only. These are still personal data in
# contracts/pleadings when attached to the label.
PARENT_FIRST_NAMES_ROW_PATTERN = re.compile(
    r"(?i)\b(?:imiona\s+rodziców|imiona\s+rodzicow)[\s\ue000:;,\-–—]{0,20}(?P<names>[A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]{2,}(?:\s+i\s+[A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]{2,})?)"
)
SURNAME_ONLY_LEGAL_ROW_PATTERN = re.compile(
    r"(?i)\b(?:nazwisko\s+rodowe|nazwisko\s+panieńskie|nazwisko\s+panienskie|poprzednie\s+nazwisko)[\s\ue000:;,\-–—]{0,20}(?P<surname>[A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]{2,})"
)

# Public-business and administrative-document rows (contract registers,
# SUDOP-like beneficiary search results, procurement appendices). These are not
# court judgments/forms; they mirror public B2B/legal documents where a party or
# beneficiary name sits directly after a label and may be a natural person, JDG,
# law office, association or company without a standard suffix.
CONTRACT_REGISTRY_PARTY_PATTERN = re.compile(
    rf"(?im)(?:^|[\n\r\ue000])\s*(?:\*\s*)?(?:kontrahent\s*/\s*nazwa|nazwa\s+kontrahenta|kontrahent\s*[-–—:]\s*nazwa|beneficjent\s*/\s*nazwa|beneficjent\s+pomocy|nazwa\s+beneficjenta|nazwa\s+przedsiębiorcy|nazwa\s+przedsiebiorcy|dane\s+beneficjenta(?:\s+pomocy)?|wykonawca\s*/\s*nazwa|zleceniobiorca\s*/\s*nazwa)\s*[:\-–—]\s*(?P<party>[^\n\r\ue000]{{2,220}})"
)
BUSINESS_NAME_LABEL_PATTERN = re.compile(
    rf"(?im)(?:^|[\n\r\ue000])\s*(?:nazwa\s+(?:skrócona|skrocona|pełna|pelna))\s*[:\-–—]\s*(?P<party>[^\n\r\ue000]{{2,180}})"
)

# Single-surname legal-context recognizers.  These cover procedural references
# such as "Powód Głąb wniósł pozew" or "Jedliński złożył oświadczenie".
# They are intentionally context- and surname-gazetteer/suffix-validated, so
# ordinary sentence-initial capitalized words are not anonymized.
PERSON_ROLE_SINGLE_SURNAME_PATTERN = re.compile(
    rf"(?i)\b(?:pow[oó]d(?:ka|em|owi|a)?|pozwan(?:y|a|ego|emu|ą|ej|ym)?|wnioskodawc(?:a|zyni|ę|y|ą)?|uczestni(?:k|czka|ka|kowi|kiem)|wierzyciel\w*|d[łl]u[żz]nik\w*|pracowni(?:k|ca|ka|cy)|pracodawc\w*|świad(?:ek|ka|kiem|kowi)|swiad(?:ek|ka|kiem|kowi)|spadkobierc\w*|poszkodowan\w*|pokrzywdzon\w*|pełnomocni\w*|pelnomocni\w*|prokurent\w*|prezes\w*|członek\s+zarządu|czlonek\s+zarzadu)\s+(?P<surname>{POLISH_CAP}(?:-{POLISH_CAP})?)(?=\s*(?:,|;|\.|\)|—|–|-|wni[oó]sł|wniosła|złożył|złożyła|zlozyl|zlozyla|podpisał|podpisała|podpisal|podpisala|wskazał|wskazała|wskazal|wskazala|oświadczył|oświadczyła|oswiadczyl|oswiadczyla|zeznał|zeznała|zeznal|zeznala|stawił|stawiła|stawil|stawila|jest|był|była|byl|byla|$))"
)

PERSON_ACTION_SINGLE_SURNAME_PATTERN = re.compile(
    rf"(?m)(?:^|(?<=[\n.;:!?]\s))(?P<surname>{POLISH_CAP}(?:-{POLISH_CAP})?)(?=\s+(?:wni[oó]sł|wniosła|złożył|złożyła|zlozyl|zlozyla|podpisał|podpisała|podpisal|podpisala|wskazał|wskazała|wskazal|wskazala|oświadczył|oświadczyła|oswiadczyl|oswiadczyla|zeznał|zeznała|zeznal|zeznala|stawił|stawiła|stawil|stawila|apelował|apelowała|apelowal|apelowala)\b)"
)
PO_BOX_ADDRESS_PATTERN = re.compile(
    rf"(?i)\bskrytka\s+pocztowa\s+\d+[A-Za-z]?(?:\s*,)?\s+\d{{2}}-\d{{3}}\s+{CITY_NAME}(?:\s+\d+)?\b"
)
BIRTH_DATE_VALUE = (
    rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}|"
    rf"\d{{4}}-\d{{2}}-\d{{2}}|"
    rf"\d{{1,2}}[ \t]+[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+[ \t]+\d{{4}})(?:[ \t]*[Rr]\.?)?"
)
BIRTH_DATA_ROW_PATTERN = re.compile(
    rf"(?i:\b(?:data\s+i\s+miejsce\s+urodzenia|data\s+urodzenia|miejsce\s+urodzenia|ur\.|urodzon[ay]?)[\s\ue000:;,\-–—]{{0,30}})(?P<birth>{BIRTH_DATE_VALUE}(?:[ \t]*(?:,|w|we)[ \t]*(?-i:{CITY_WORD}(?:[ \t]+{CITY_WORD}){{0,2}}))?)"
)
# Reverse-order address clauses, common in forms and e-mail footers:
# "00-001 Warszawa, ul. Prosta 1". The direct address detector catches the
# street-first variant; this contextual pattern masks the whole reverse span.
ADDRESS_REVERSE_FULL_PATTERN = re.compile(
    rf"\b\d{{2}}-\d{{3}}\s+{CITY_NAME}\s*,\s*{ADDRESS_STREET}\b"
)
# Reverse address rows in public registers and invoices often omit the street
# prefix or use village-style locality/building order after the postcode. These
# are label/context anchored to avoid masking ordinary city mentions.
ADDRESS_REVERSE_LABEL_PATTERN = re.compile(
    rf"(?i:\b(?:adres\s+korespondencyjny|adres\s+siedziby|miejsce\s+wykonywania\s+działalności|miejsce\s+wykonywania\s+dzialalnosci|siedziba|adres)\s*[:\-–—]\s*)"
    rf"(?P<addr>\d{{2}}-\d{{3}}\s+{CITY_NAME}\s*,\s*(?:(?i:{STREET_PREFIX})\s+)?{STREET_NAME}\s+{BUILDING_NUMBER}(?:\s*,?\s*(?:lok\.?|lokal|m\.?)\s*\d+[A-Za-z]?)?)\b"
)
PROPERTY_UNIT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:lokal\w*|miejsce\s+(?:postojowe|parkingowe)|garaż\w*|garaz\w*|komórk\w*\s+lokatorsk\w*|komork\w*\s+lokatorsk\w*|boks|box)\s*(?:nr\.?|numer|oznaczony\s+nr\.?)?\s*[:#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{0,20}\d[A-Z0-9./_\-]{0,20})\b"
)
NOTARIAL_ACT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:akt\s+notarialny|numer\s+aktu\s+notarialnego|nr\.?\s+aktu\s+notarialnego)\s*(?:nr\.?|numer|znak)?\s*[:#\-–— ]{0,12}(?P<id>[A-Z0-9][A-Z0-9./_\-]{3,80})\b"
)
# CEIDG / sole-proprietor labels without an explicit "pod firmą" phrase.
# A bare two-token person after the label remains a PERSON; a trade-name tail
# such as "Jan Kowalski Software" is treated as the identifying business line.
SOLE_PROPRIETOR_LABEL_PATTERN = re.compile(
    rf"(?i:\b(?:przedsiębiorca|przedsiebiorca|jednoosobowa\s+działalność\s+gospodarcza|jednoosobowa\s+dzialalnosc\s+gospodarcza|JDG|osoba\s+fizyczna\s+prowadząca\s+działalność\s+gospodarczą|osoba\s+fizyczna\s+prowadzaca\s+dzialalnosc\s+gospodarcza)\s*[:\-–—]{{0,20}}\s*)(?P<company>{PERSON_NAME_LOOSE}(?:[ \t]+[{LATIN_UPPER}][{LATIN_LETTERS}0-9&_.-]{{2,}}){{0,4}})(?=\s*(?:,|;|\)|NIP\b|REGON\b|KRS\b|PESEL\b|adres\b|ul\.|$))"
)
# Locality used in a residence clause without a full street address, e.g.
# "zamieszkały w Pustyni". City names alone should not generally be masked,
# but in residence/address contexts they are identifying location data.
ADDRESS_RESIDENCE_LOCALITY_PATTERN = re.compile(
    rf"(?i)\b(?:zam\.|zamieszkał(?:y|a)?|zamieszkaly|zamieszkala|zamieszkałego|zamieszkałej|zamieszkałym|zamieszkałą|adres\s+zamieszkania|miejsce\s+zamieszkania|według\s+oświadczenia\s+zamieszkał(?:y|a)?)\s+(?:w|we)\s+(?P<place>{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}})(?=\s*(?:,|\.|;|\)|przy\b|ul\.|adres\b|PESEL\b|$))"
)
PUBLIC_ADMIN_ORG_RE = re.compile(rf"(?i)\b(?:{LEGAL_PUBLIC_AUTHORITY_RE}|Rada\s+Gminy|Rady\s+Gminy|Gmina|Gminy|Powiat|Wojew[oó]dztwo|Urząd\s+(?:Miasta|Gminy|Marszałkowski)|Urzad\s+(?:Miasta|Gminy|Marszalkowski))\b")

# Single-word tails after document-title labels (for example "UMOWA SPRZEDAŻY")
# are usually legal document descriptors, not client entities. Multi-word,
# suffix-bearing or clearly context-anchored party names are handled by the
# dedicated party/company detectors below.
DOCUMENT_TITLE_TAIL_STOPWORDS = {
    "SPRZEDAZ", "SPRZEDAZY", "NAJEM", "NAJMU", "DZIERZAWA", "DZIERZAWY",
    "ZLECENIE", "ZLECENIA", "USLUG", "USLUGI", "USLUGOWA",
    "DOSTAW", "DOSTAWY", "ROBOT", "ROBÓT", "BUDOWLANYCH",
    "LICENCJA", "LICENCJI", "WDROZENIE", "WDROŻENIE", "WDROZENIA", "WDROŻENIA",
    "POUFNOSCI", "POUFNOŚCI", "RAMOWA", "RAMOWEJ", "PRZEDWSTEPNA", "PRZEDWSTĘPNA",
    "DEWELOPERSKA", "DEWELOPERSKIEJ", "UDZIALOW", "UDZIAŁÓW",
    "AKCJI", "KUPNA", "SPRZEDAZY", "SPRZEDAŻY",
}

def _looks_like_generic_document_title_tail(value: str) -> bool:
    cleaned = _clean_alias(value)
    if not cleaned:
        return True
    norm = deaccent_role(cleaned)
    tokens = [t for t in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŻŹąćęłńóśżź0-9]+", norm) if t]
    if not tokens:
        return True
    if len(tokens) == 1:
        token = tokens[0]
        # A single ordinary legal-title word after "umowa/kontrakt/projekt" is
        # not a company. Allow distinctive acronyms such as FENIX/OLIMP to pass.
        if token in DOCUMENT_TITLE_TAIL_STOPWORDS or token in {deaccent_role(x) for x in LEGAL_WORD_STOPLIST}:
            return True
        if len(token) <= 4 and token not in COMMON_UPPERCASE_STOPWORDS:
            return False
        return token.endswith(("Y", "U", "EJ", "OW"))
    if all(t in DOCUMENT_TITLE_TAIL_STOPWORDS or t in {deaccent_role(x) for x in LEGAL_WORD_STOPLIST} for t in tokens):
        return True
    return False


# Validators and shared legal lexicon are imported from validators.py and legal_lexicon.py.

CONFIDENTIAL_ALIAS_PATTERN = re.compile(
    r'(?i)(?:dalej\s+jako|zwany(?:a|e|mi|m|ch|j|i)?\s+dalej|określan(?:y|a|e)\s+dalej|okreslan(?:y|a|e)\s+dalej|dalej\s*:|w\s+dalszej\s+części\s+umowy\s+jako)\s*(?:[„"\']([^”"\'\n]{2,80})[”"\']|([^,. ;\n]{2,40}))'
)
CONTRACTOR_CONTEXT_PATTERN = re.compile(
    rf"(?i)\b(?:{ROLE_CONTEXT})\b\s*(?:[:\-–]|jest|oznacza|=)\s*([^\n.;]{{3,180}})"
)
CONTACT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:osob(?:a|ą)\s+do\s+kontaktu|kontakt|koordynator|opiekun|przedstawiciel|reprezentowan(?:y|a|e)\s+przez|w\s+imieniu|pełnomocnik|pelnomocnik|prokurent)\b[^\n.;:]{0,80}[:\-–]?\s*([^\n.;]{3,140})"
)
LEGAL_SUFFIX_RE = re.compile(rf"(?i)\s*(?:{COMPANY_SUFFIX})(?:\b|$).*$")
ORG_PREFIX_RE = re.compile(rf"(?i)^\s*(?:{ORG_PREFIX})\s+")
DOMAIN_FROM_EMAIL_RE = re.compile(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
TRAILING_CONTEXT_RE = re.compile(r"(?i)\s+(?:z\s+siedzibą|z\s+siedziba|wpisan(?:a|y|e)|NIP|REGON|KRS|reprezentowan(?:a|y|e)|dalej|zwany|zwana|zwane)\b.*$")

# Terms which may appear directly before a party name in headings or sentences.
# They are document descriptors, not part of the company name.
LEADING_COMPANY_NOISE_WORDS = {
    'umowa', 'umowy', 'umowie', 'umową', 'umowe', 'przedmiot', 'przedmiotem',
    'zlecenie', 'zlecenia', 'zleceniu', 'klient', 'klienta', 'strona', 'strony',
    'wykonawca', 'wykonawcy', 'zamawiający', 'zamawiajacy', 'usługodawca',
    'uslugodawca', 'usługobiorca', 'uslugobiorca', 'kontrahent', 'partner',
    'dostawca', 'odbiorca', 'zwany', 'zwana', 'zwane', 'dalej', 'jako',
    # Party labels are not part of the entity name. Without trimming,
    # "Pozwany Mucha sp. z o.o." becomes one COMPANY and the role label
    # disappears from the sentence after masking.
    'powód', 'powod', 'powoda', 'pozwany', 'pozwanego', 'wierzyciel',
    'wierzyciela', 'dłużnik', 'dluznik', 'dłużnika', 'dluznika',
}


@lru_cache(maxsize=131072)
def _clean_alias(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().strip(".,;:()[]{}„”\"'")
    return value


LEGAL_TITLE_STOP_PHRASES_NORM = frozenset(deaccent_role(x) for x in LEGAL_TITLE_STOP_PHRASES)
LEGAL_WORD_STOPLIST_NORM = frozenset(deaccent_role(x) for x in LEGAL_WORD_STOPLIST)
ROLE_ALIASES_NORM = frozenset(deaccent_role(r) for r in ROLE_ALIASES)
COMMON_UPPERCASE_STOPWORDS_NORM = frozenset(deaccent_role(x) for x in COMMON_UPPERCASE_STOPWORDS)
LEGAL_AND_UPPER_STOPWORDS_NORM = COMMON_UPPERCASE_STOPWORDS_NORM | LEGAL_WORD_STOPLIST_NORM


def _trim_trailing_url_punctuation(value: str, start: int) -> tuple[str, int]:
    """Trim punctuation that belongs to surrounding prose, not to the URL.

    The direct URL regex intentionally stays permissive, but Word/legal prose often
    writes URLs followed by a comma or full stop. Masking that punctuation changes
    the anonymized text unnecessarily and can make restore maps look suspicious.
    """
    trimmed = (value or "").rstrip(".,;:)]}”’\"")
    return trimmed, start


def _bank_account_digits(value: str) -> str:
    return only_digits(value or "")


def _looks_like_bank_account_number(value: str, *, require_checksum: bool = False) -> bool:
    """Validate a Polish bank account candidate without disclosing its value.

    Direct IBAN/NRB matches are checksum-validated. Context-anchored account
    numbers are accepted when they are 26 digits and not an obvious dummy run,
    because contracts and invoices often contain fictional/test accounts that
    still must not be sent to AI in clear text.
    """
    digits = _bank_account_digits(value)
    if len(digits) != 26:
        return False
    if len(set(digits)) <= 1:
        return False
    if require_checksum:
        return valid_pl_iban(value)
    return True


@lru_cache(maxsize=131072)
def _norm_legal(value: str) -> str:
    return deaccent_role(_clean_alias(value)).replace("  ", " ")


@lru_cache(maxsize=131072)
def _is_legal_term(value: str) -> bool:
    cleaned = _norm_legal(value)
    if not cleaned:
        return False
    if re.search(r"\bDOKUMENT(?:U|EM|Y|OW)?\s+TOZSAMOSCI\b", cleaned):
        return True
    if PUBLIC_ADMIN_ORG_RE.search(value or ""):
        return True
    if cleaned in LEGAL_TITLE_STOP_PHRASES_NORM:
        return True
    words = [w.strip(".,;:()[]{}") for w in cleaned.split() if w.strip(".,;:()[]{}")]
    if len(words) >= 2 and all(w in LEGAL_WORD_STOPLIST_NORM for w in words):
        return True
    return False


@lru_cache(maxsize=131072)
def _strip_person_title_prefix(value: str) -> str:
    cleaned = _clean_alias(value)
    title_re = re.compile(rf"^(?:{LEGAL_PROFESSIONAL_TITLE})(?:[ \t\u00A0]+(?:{LEGAL_PROFESSIONAL_TITLE})){{0,1}}[ \t\u00A0]+", re.IGNORECASE)
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = title_re.sub("", cleaned, count=1)
    return cleaned

@lru_cache(maxsize=131072)
def _looks_like_person_name(value: str) -> bool:
    cleaned = _strip_person_title_prefix(value)
    if _is_legal_term(cleaned):
        return False
    parts = cleaned.split()
    if len(parts) < 2:
        return False
    first = parts[0].strip(".,;:()[]{}")
    # CSM legal lexicon includes inflected forms and common diminutives, e.g.
    # Jana/Janem/Janek, Anny/Anią/Ania, Piotra/Piotrek, Kuba -> Jakub.
    return is_first_name_form(first)


@lru_cache(maxsize=131072)
def _is_role_alias(value: str) -> bool:
    cleaned = deaccent_role(_clean_alias(value)).strip(".,;:-–—()[]{}„”\"'")
    if not cleaned:
        return False
    if cleaned in ROLE_ALIASES_NORM:
        return True
    # Conservative fallback for common participle role families in Polish legal
    # contracts (sprzedający/kupujący/nabywający/zbywający in many cases).
    role_stems = (
        "SPRZEDAJAC", "KUPUJAC", "NABYWAJAC", "ZBYWAJAC",
        "WYNAJMUJAC", "WYDZIERZAWIAJAC",
    )
    if any(cleaned.startswith(stem) for stem in role_stems) and len(cleaned) <= 24:
        return True
    return False


@lru_cache(maxsize=131072)
def _is_probably_confidential_alias(value: str) -> bool:
    alias = _clean_alias(value)
    if len(alias) < 2 or len(alias) > 80:
        return False
    if _is_role_alias(alias) or _is_legal_term(alias):
        return False
    up = alias.upper().strip(".,;:-")
    if up in COMMON_UPPERCASE_STOPWORDS:
        return False
    # Accept quoted aliases, all-caps abbreviations, mixed-case names and names with digits.
    return bool(re.search(rf"[{LATIN_LETTERS}0-9]", alias))


@lru_cache(maxsize=4096)
def _literal_pattern(value: str) -> re.Pattern:
    return re.compile(rf"(?<![\w{LATIN_LETTERS}]){re.escape(value)}(?![\w{LATIN_LETTERS}])")


def _find_literal_occurrences(text: str, value: str, category: str) -> List[Finding]:
    value = _clean_alias(value)
    if not value:
        return []
    # The boundary pattern can only match where the literal substring occurs;
    # the C-level substring check is far cheaper than compiling and scanning.
    if value not in text:
        return []
    # Avoid matching inside longer tokens, but allow punctuation such as ABC-u.
    pattern = _literal_pattern(value)
    return [Finding(category, m.group(0), m.start(), m.end()) for m in pattern.finditer(text)]


_WORD_TOKEN_RE = re.compile(r"\w+")


def _literal_boundary_pattern(aliases: Iterable[str]) -> re.Pattern | None:
    unique = [a for a in dict.fromkeys(_clean_alias(a) for a in aliases) if a]
    if not unique:
        return None
    # Longest alternatives first mirrors the earlier remove-overlaps behaviour
    # and avoids matching "Kantorowski" before the full kancelaria name.
    unique.sort(key=lambda item: (-len(item), item.casefold()))
    body = "|".join(re.escape(item) for item in unique)
    return re.compile(rf"(?<![\w{LATIN_LETTERS}])(?:{body})(?![\w{LATIN_LETTERS}])")


def _find_many_literal_occurrences(text: str, requests: Iterable[Tuple[str, str]]) -> List[Finding]:
    """Find many exact aliases using a small number of regex passes.

    The earlier implementation scanned the full document once for every alias.
    Long contracts can produce hundreds of person/company/domain aliases, which
    makes runtime grow roughly with aliases x document length. This groups
    literal aliases into chunked alternation regexes, reducing scans while still
    preserving exact word-boundary matching and per-category findings.
    """
    alias_to_categories: Dict[str, Set[str]] = {}
    for category, alias in requests:
        cleaned = _clean_alias(alias)
        if not cleaned:
            continue
        alias_to_categories.setdefault(cleaned, set()).add(category)
    if not alias_to_categories or not text:
        return []
    # Person/company alias expansion generates many inflected variants that do
    # not occur in the document at all. Dropping them early keeps the
    # alternation patterns small without changing results: a boundary match
    # requires every word-character run of the alias to appear as a maximal
    # word-token of the text, and the alias itself to appear as a substring.
    text_tokens = set(_WORD_TOKEN_RE.findall(text))
    aliases = sorted(
        (
            alias
            for alias in alias_to_categories
            if all(tok in text_tokens for tok in _WORD_TOKEN_RE.findall(alias)) and alias in text
        ),
        key=lambda item: (-len(item), item.casefold()),
    )
    results: List[Finding] = []
    chunk: List[str] = []
    chunk_chars = 0
    # Keep regex compilation predictable on documents with many unique aliases.
    max_chunk_chars = 24000
    for alias in aliases:
        chunk.append(alias)
        chunk_chars += len(alias) + 1
        if chunk_chars >= max_chunk_chars:
            pattern = _literal_boundary_pattern(chunk)
            if pattern is not None:
                for m in pattern.finditer(text):
                    matched = m.group(0)
                    for category in alias_to_categories.get(matched, ()):
                        results.append(Finding(category, matched, m.start(), m.end()))
            chunk = []
            chunk_chars = 0
    if chunk:
        pattern = _literal_boundary_pattern(chunk)
        if pattern is not None:
            for m in pattern.finditer(text):
                matched = m.group(0)
                for category in alias_to_categories.get(matched, ()):
                    results.append(Finding(category, matched, m.start(), m.end()))
    return results


@lru_cache(maxsize=65536)
def _company_aliases(value: str) -> Set[str]:
    aliases: Set[str] = set()
    raw = _clean_alias(value)
    raw = _clean_alias(TRAILING_CONTEXT_RE.sub("", raw))
    if not raw:
        return aliases
    # Public administration units (e.g. Rady Gminy Przemyśl) should not seed
    # private-party aliases such as "Przemyśl". They are often public/legal
    # context, not client-side PII in CSM's contract workflow.
    if PUBLIC_ADMIN_ORG_RE.search(raw):
        return aliases
    aliases.add(raw)
    base = _clean_alias(LEGAL_SUFFIX_RE.sub("", raw))
    base = _clean_alias(ORG_PREFIX_RE.sub("", base))
    if base and len(base) >= 3 and not _is_role_alias(base):
        aliases.add(base)
        words = [w for w in base.split() if w]
        if len(words) > 1:
            first = _clean_alias(words[0])
            first_two = _clean_alias(" ".join(words[:2]))
            last = _clean_alias(words[-1])
            if len(first) >= 3 and first.upper() not in COMMON_UPPERCASE_STOPWORDS:
                aliases.add(first)
            if len(first_two) >= 5:
                aliases.add(first_two)
            # Avoid seeding broad one-word aliases from two-word company names.
            # Public contract registers often contain vendors such as "One Dynamics
            # Sp. z o.o." and later product names like "Dynamics 365". Masking the
            # generic last token as a company alias creates false positives. Keep
            # last-token aliases only for longer names or distinctive all-caps codes.
            if len(words) > 2 and len(last) >= 4 and last.upper() not in COMMON_UPPERCASE_STOPWORDS:
                aliases.add(last)
            elif last.isupper() and 3 <= len(last) <= 12 and last.upper() not in COMMON_UPPERCASE_STOPWORDS:
                aliases.add(last)
        acronym = "".join(w[0] for w in words if w and w[0].isalpha()).upper()
        if 3 <= len(acronym) <= 12 and acronym not in COMMON_UPPERCASE_STOPWORDS:
            aliases.add(acronym)
    for a in list(aliases):
        if re.fullmatch(rf"[{LATIN_UPPER}0-9&.-]{{2,14}}", a):
            for suffix in ("-u", "u", "owi", "-owi", "em", "-em", "ie", "-ie", "a", "-a"):
                aliases.add(a + suffix)
        if re.fullmatch(rf"[{LATIN_UPPER}][{LATIN_LETTERS}]{{3,}}", a):
            if a.endswith("a"):
                stem = a[:-1]
                aliases.update({stem + "y", stem + "ie", stem + "ą"})
            else:
                aliases.update({a + "u", a + "owi", a + "em", a + "ie", a + "a"})
    return {a for a in aliases if _is_probably_confidential_alias(a) and not _is_legal_term(a)}


@lru_cache(maxsize=65536)
def _firstname_variants(first: str) -> Set[str]:
    return lexicon_first_name_variants(first)


@lru_cache(maxsize=65536)
def _surname_variants(last: str) -> Set[str]:
    variants = {last}
    if len(last) < 4:
        return variants
    if last.endswith("ski") or last.endswith("cki") or last.endswith("dzki"):
        stem = last[:-1]  # sk/c/dzk + i -> sk/c/dzk
        variants.update({stem + "iego", stem + "iemu", stem + "im", stem + "im", stem + "iego", stem + "iem"})
    elif last.endswith("ska") or last.endswith("cka") or last.endswith("dzka"):
        stem = last[:-1]
        variants.update({stem + "iej", stem + "ą", stem + "a"})
    elif last.endswith("iem") and len(last) > 5:
        variants.add(last[:-3])
    elif last.endswith("ą") and len(last) > 4:
        variants.add(last[:-1] + "a")
    elif last.endswith("a"):
        stem = last[:-1]
        variants.update({stem + "y", stem + "ie", stem + "ą"})
    else:
        variants.update({last + "a", last + "owi", last + "em", last + "ie", last + "u"})
    return variants


@lru_cache(maxsize=65536)
def _person_parts(value: str) -> tuple[str, str] | None:
    cleaned = _strip_person_title_prefix(value)
    cleaned = _clean_alias(re.sub(r"(?i)^(powód|powod|powódka|powodka|pozwany|pozwana|wnioskodawca|wnioskodawczyni|uczestnik|uczestniczka|pracownik|pracodawca)\s+", "", cleaned))
    parts = cleaned.split()
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


@lru_cache(maxsize=65536)
def _first_name_key(first: str) -> str:
    return lexicon_first_name_key(first)


@lru_cache(maxsize=65536)
def _surname_key(last: str) -> str:
    """Return a canonical, inflection-tolerant uppercase key for a surname.

    Used to compare two surface forms (e.g. "Kowalskiego", "Kowalskim",
    "Kowalski") and decide whether they belong to the same family. Heuristic
    only — no exhaustive lexicon — but enough for the common Polish suffixes.
    """
    up = deaccent_role(last).upper()
    if len(up) < 4:
        return up
    # Adjectival surnames: Kowalski / Kowalska / Kowalskie family
    for suffix, base in (("IEGO", "I"), ("IEMU", "I"), ("IEJ", "A"), ("IM", "I")):
        if up.endswith(suffix) and len(up) > len(suffix) + 2:
            return up[:-len(suffix)] + base
    if up.endswith("SKĄ") or up.endswith("CKĄ") or up.endswith("DZKĄ"):
        return up[:-1] + "A"
    if up.endswith("SKA") or up.endswith("CKA") or up.endswith("DZKA"):
        return up
    if up.endswith("SKI") or up.endswith("CKI") or up.endswith("DZKI"):
        return up
    if up.endswith("SKIM") or up.endswith("CKIM") or up.endswith("DZKIM"):
        return up[:-1]
    # Genitive / dative / instrumental for short masculine surnames
    if up.endswith("IEM") and len(up) > 5:
        return up[:-3]
    if up.endswith("OWI") and len(up) > 5:
        return up[:-3]
    if up.endswith("EM") and len(up) > 4:
        return up[:-2]
    if up.endswith("IE") and len(up) > 5:
        return up[:-2]
    if up.endswith("A") and len(up) > 4 and not up.endswith("CKA") and not up.endswith("SKA") and not up.endswith("DZKA"):
        return up[:-1]
    return up


@lru_cache(maxsize=65536)
def _person_aliases(value: str, include_first: bool = False, include_surname: bool = True) -> Set[str]:
    cleaned = _strip_person_title_prefix(value)
    cleaned = _clean_alias(re.sub(r"(?i)^(powód|powod|powódka|powodka|pozwany|pozwana|wnioskodawca|wnioskodawczyni|uczestnik|uczestniczka|pracownik|pracodawca)\s+", "", cleaned))
    parts = cleaned.split()
    if len(parts) < 2:
        return {cleaned} if cleaned else set()
    given_parts = parts[:-1]
    first = parts[0]
    last = parts[-1]
    aliases: Set[str] = {cleaned}
    first_vars = _firstname_variants(first)
    last_vars = _surname_variants(last)
    # First-name + surname variants, useful when a later mention drops middle names.
    for f in first_vars:
        for l in last_vars:
            aliases.add(f"{f} {l}")
    # Full multi-given-name variants, e.g. "Michał Adam Nowacki" ->
    # "Michała Adama Nowackiego" or "Annie Marii Zielińskiej".
    if len(given_parts) > 1:
        for given_combo in expand_given_names_variants(given_parts, limit=96):
            for l in list(last_vars)[:16]:
                aliases.add(f"{given_combo} {l}")
    required_aliases: Set[str] = set()
    # Surname-only occurrences are only safely identifying when the surname
    # uniquely identifies one detected person in this document.
    if include_surname:
        surname_aliases = {v for v in last_vars if len(v) >= 5}
        aliases.update(surname_aliases)
        required_aliases.update(surname_aliases)
    # First-name-only occurrences are more ambiguous; add them only when the
    # caller knows this first name identifies exactly one detected person.
    if include_first:
        first_aliases = {v for v in first_vars if len(v) >= 3}
        aliases.update(first_aliases)
        required_aliases.update(first_aliases)
    # Keep the alias set bounded. Legal DOCX files are processed part-by-part and
    # each alias is searched literally; unbounded Polish inflection expansion can
    # make large contracts slow without materially improving safety. Preserve
    # required unique surname/first-name aliases before trimming.
    ordered = sorted(aliases - required_aliases, key=lambda x: (-len(x.split()), -len(x), x.casefold()))
    remaining = max(0, 60 - len(required_aliases))
    return set(ordered[:remaining]) | required_aliases


@lru_cache(maxsize=65536)
def _domain_variants(domain: str) -> Set[str]:
    d = domain.lower().strip().strip(".,;:)")
    if not d:
        return set()
    variants = {d}
    if d.startswith("www."):
        variants.add(d[4:])
    else:
        variants.add("www." + d)
    return variants


@lru_cache(maxsize=65536)
def _court_aliases(value: str) -> Set[str]:
    """Return common Polish court aliases for a detected full court name.

    Examples: "Sąd Okręgowy w Rzeszowie" -> "SO w Rzeszowie",
    "Sąd Rejonowy dla m.st. Warszawy" -> "SR dla m.st. Warszawy".
    Aliases are seeded only from an already detected full court name, so a bare
    abbreviation such as "SO" in ordinary text is not masked by itself.
    """
    raw = _clean_alias(value)
    if not raw:
        return set()
    # Accept both nominative and inflected court names (gap E from the 2026-07-01
    # verification report): "Sąd Rejonowy", "Sądem Rejonowym", "Sądowi
    # Rejonowemu", "Sądu Okręgowego" etc. The kind is matched by stem and mapped
    # back to the canonical abbreviation.
    m = re.match(
        rf"(?i)^S[ąa]d(?:em|owi|u|zie)?\s+(?P<kind>Rejonow|Okręgow|Okregow|Apelacyjn|Najwyższ|Najwyzsz)(?:ego|emu|ym|y|m)(?P<tail>.*)$",
        raw,
    )
    if not m:
        return set()
    kind = deaccent_role(m.group("kind"))
    prefix = {
        "REJONOW": "SR",
        "OKREGOW": "SO",
        "APELACYJN": "SA",
        "NAJWYZSZ": "SN",
    }.get(kind)
    if not prefix:
        return set()
    tail = _clean_alias(m.group("tail") or "")
    aliases = {raw}
    if tail:
        aliases.add(f"{prefix}{tail}")
        aliases.add(f"{prefix} {tail}")
    else:
        aliases.add(prefix)
    # Common non-breaking/spacing variants around "m.st." drafted in pleadings.
    expanded = set()
    for alias in aliases:
        expanded.add(alias)
        expanded.add(re.sub(r"(?i)m\.\s*st\.", "m.st.", alias))
        expanded.add(re.sub(r"(?i)m\.st\.", "m. st.", alias))
    return {a for a in expanded if len(a) >= 2 and not _is_legal_term(a)}


@lru_cache(maxsize=65536)
def _canonical_court_value(value: str) -> str:
    raw = _clean_alias(value)
    m_alias = re.match(r"(?i)^(SR|SO|SA|SN)\s*(?P<tail>.*)$", raw)
    if m_alias:
        prefix = m_alias.group(1).upper()
        full = {"SR": "Sąd Rejonowy", "SO": "Sąd Okręgowy", "SA": "Sąd Apelacyjny", "SN": "Sąd Najwyższy"}[prefix]
        raw = _clean_alias(full + " " + (m_alias.group("tail") or ""))
    # Fold inflected full forms ("Sądem Rejonowym w X", "Sądu Okręgowego w X")
    # onto the nominative so different case forms of the same court share one
    # canonical key (and therefore one placeholder). Gap E, 2026-07-01 report.
    m_full = re.match(
        r"(?i)^S[ąa]d(?:em|owi|u|zie)?\s+(?P<kind>Rejonow|Okręgow|Okregow|Apelacyjn|Najwyższ|Najwyzsz)(?:ego|emu|ym|y|m)(?P<tail>.*)$",
        raw,
    )
    if m_full:
        kind = deaccent_role(m_full.group("kind"))
        canon_kind = {
            "REJONOW": "Rejonowy",
            "OKREGOW": "Okręgowy",
            "APELACYJN": "Apelacyjny",
            "NAJWYZSZ": "Najwyższy",
        }.get(kind)
        if canon_kind:
            raw = _clean_alias(f"Sąd {canon_kind} {m_full.group('tail') or ''}")
    return deaccent_role(raw).casefold()


@lru_cache(maxsize=1)
def _contextual_person_stopset() -> frozenset:
    return frozenset(deaccent_role(x) for x in LEGAL_WORD_STOPLIST) | frozenset(
        deaccent_role(x) for x in COMMON_UPPERCASE_STOPWORDS
    )


@lru_cache(maxsize=8192)
def _is_contextual_person_candidate(value: str) -> bool:
    cleaned = _clean_alias(value)
    if not cleaned or _is_legal_term(cleaned) or _is_role_alias(cleaned):
        return False
    parts = [p.strip(".,;:()[]{}„”\"'") for p in cleaned.split() if p.strip(".,;:()[]{}„”\"'")]
    if len(parts) < 2 or len(parts) > 3:
        return False
    if len(parts) >= 3 and ("-" in parts[-1] or "–" in parts[-1] or "—" in parts[-1]):
        # Avoid swallowing brand names such as "Near-Perfect" as the last
        # segment of a person's name. True three-part person names normally have
        # a middle first name before the surname.
        if _first_name_key(parts[1]) not in {deaccent_role(x) for x in COMMON_POLISH_FIRST_NAMES}:
            return False
    norm_parts = [deaccent_role(p) for p in parts]
    stop = _contextual_person_stopset()
    if all(p in stop for p in norm_parts):
        return False
    # Reject obvious defined terms / headings even if they occur near punctuation.
    if any(p in {"UMOWA", "UMOWY", "STRONA", "STRONY", "KLIENT", "KLIENTA", "ZLECENIE", "ZLECENIA", "REPREZENTACJA", "DOKUMENT", "DOKUMENTU", "TOZSAMOSCI", "TOŻSAMOŚCI", "PREZYDENTA", "MIASTA", "GMINY", "RADY", "SADU", "SĄDU", "PREZES", "PREZESA", "ZARZAD", "ZARZĄD", "ZARZADU", "ZARZĄDU", "CZLONEK", "CZŁONEK", "DYREKTOR", "KIEROWNIK", "SPECJALISTA"} for p in norm_parts):
        return False
    # A legal-context person should contain real lower-case letters after the
    # initial capital. This filters acronym sequences like VAT KRS.
    if not all(re.match(rf"^[{LATIN_UPPER}][{LATIN_LETTERS}'’.-]{{2,}}$", p) for p in parts):
        return False
    return True



def _trim_person_candidate_tail(value: str, absolute_start: int) -> tuple[str, int]:
    """Trim false trailing words captured by case-insensitive context regexes.

    Some legal-context patterns are case-insensitive so labels like
    "pełnomocnik" match reliably. Without this guard they may also swallow
    lowercase words after a real name, e.g. "Piotrek Kowalski przesłał
    uwagi". A person candidate should be a short run of title-cased tokens.
    """
    raw = value or ""
    leading = len(raw) - len(raw.lstrip())
    start = absolute_start + leading
    raw = raw.lstrip()
    tokens = raw.split()
    kept: list[str] = []
    consumed = 0
    for token in tokens:
        bare = token.strip(".,;:()[]{}„”\"'")
        if not bare:
            consumed += len(token) + 1
            continue
        if not re.match(rf"^[{LATIN_UPPER}]", bare):
            break
        kept.append(token)
        consumed += len(token) + 1
        if len(kept) >= 3:
            break
    if len(kept) >= 2:
        return _clean_alias(" ".join(kept)), start
    return _clean_alias(value), absolute_start


_PERSON_LEADING_CONTEXT_WORDS = {
    "REPREZENTACJA", "REPREZENTANTA", "REPREZENTANT", "DANE", "OSOBA",
    "KONTAKTU", "DOKUMENT", "DOKUMENTU", "TOZSAMOSCI", "TOŻSAMOŚCI",
    "PREZYDENTA", "MIASTA", "GMINY", "RADY", "SADU", "SĄDU",
    "PAN", "PANA", "PANU", "PANEM", "PANI", "PANIĄ", "PANIA",
    "PELNOMOCNIK", "PEŁNOMOCNIK", "PELNOMOCNIKIEM", "PEŁNOMOCNIKIEM",
    "PELNOMOCNIKA", "PEŁNOMOCNIKA", "ADWOKAT", "ADW", "RADCA", "RADCĘ",
    "RADCE", "RADCY", "PRAWNY", "PRAWNEGO", "RPR", "R", "PR", "MEC", "MECENAS",
    "POWOD", "POWÓD", "POWODKA", "POWÓDKA", "POZWANY", "POZWANA",
    "WNIOSKODAWCA", "WNIOSKODAWCZYNI", "UCZESTNIK", "UCZESTNICZKA",
    "PRACOWNIK", "PRACOWNICA", "PRACODAWCA", "PACJENT", "PACJENTKA"
}

def _strip_leading_person_context_words(raw: str, absolute_start: int) -> tuple[str, int]:
    value = raw or ""
    offset = 0
    while True:
        m = re.match(rf"^\s*([{LATIN_UPPER}][{LATIN_LETTERS}.-]+)\s+", value)
        if not m:
            break
        if deaccent_role(m.group(1)) not in {deaccent_role(x) for x in _PERSON_LEADING_CONTEXT_WORDS}:
            break
        offset += m.end()
        value = value[m.end():]
    return _trim_person_candidate_tail(value, absolute_start + offset)

def _append_contextual_person_findings(text: str, findings: List[Finding]) -> None:
    patterns = (
        PERSON_CONTEXT_PREFIXED_PATTERN,
        PERSON_AFTER_RELATION_PATTERN,
        PERSON_RENAMED_PATTERN,
        PERSON_TITLE_CONTEXT_PATTERN,
        PERSON_TITLE_SINGLE_TOKEN_PATTERN,
        PERSON_BEFORE_ID_OR_BIRTH_PATTERN,
        PERSON_BEFORE_LEGAL_MARKER_PATTERN,
        PERSON_ROLE_SUFFIX_PATTERN,
        PERSON_LEGAL_ROW_PATTERN,
        PERSON_CONTACT_LABEL_ROW_PATTERN,
        PERSON_AFTER_REPRESENTED_BY_PATTERN,
        PERSON_AT_PARTY_ROW_PATTERN,
    )
    for pattern in patterns:
        for m in pattern.finditer(text or ""):
            raw = m.group("name") or ""
            raw_start = m.start("name") + (len(raw) - len(raw.lstrip()))
            value, start = _strip_leading_person_context_words(raw, raw_start)
            if pattern is PERSON_TITLE_SINGLE_TOKEN_PATTERN:
                if not value or _is_legal_term(value):
                    continue
            elif not _is_contextual_person_candidate(value):
                continue
            findings.append(Finding("PERSON", value, start, start + len(value)))
    for m in LOWERCASE_LEGAL_PERSON_PATTERN.finditer(text or ""):
        raw = m.group("name") or ""
        value = _clean_alias(raw)
        if value and _looks_like_person_name(value):
            findings.append(Finding("PERSON", raw, m.start("name"), m.end("name")))
    for pattern in (PERSON_ROLE_SINGLE_SURNAME_PATTERN, PERSON_ACTION_SINGLE_SURNAME_PATTERN):
        for m in pattern.finditer(text or ""):
            raw = m.group("surname") or ""
            value = _clean_alias(raw)
            if value and _looks_like_single_surname(value):
                findings.append(Finding("PERSON", raw, m.start("surname"), m.end("surname")))


def _trim_public_party_value(value: str) -> str:
    """Trim source-list party rows to the actual contractor/beneficiary name."""
    value = _clean_alias((value or "").replace("", " "))
    if not value:
        return ""
    value = re.split(r"(?i)\s+(?:data\s+zawarcia\s+umowy|przedmiot\s+umowy|wartość\s+umowy|wartosc\s+umowy|okres\s+obowiązywania|okres\s+obowiazywania|autor\s+informacji)\b", value)[0]
    value = re.split(r"(?i)\s*,?\s*(?:nazwa\s+(?:pełna|pelna|skrócona|skrocona)|NIP|REGON|KRS|PESEL)\b", value)[0]
    value = _clean_alias(value)
    return value.strip('•* -–—:;')


def _public_party_category(value: str) -> str | None:
    cleaned = _clean_alias(value)
    if not cleaned or _is_legal_term(cleaned):
        return None
    stripped = _strip_person_title_prefix(cleaned)
    norm = deaccent_role(cleaned)
    if re.search(r"\bPROWADZ\w*\s+DZIALALNOSC|\bPOD\s+FIRMA|\bPOD\s+NAZWA|KANCELARIA|ADWOKACKA|RADCOWSKA|NOTARIALNA|BIURO|FUNDACJA|STOWARZYSZENIE|SPOLKA|SP\.?\s*[ZJKA]\.?|S\.?A\.?|S\.?C\.?", norm):
        return "CONTRACTOR"
    if re.search(rf"(?i)\b(?:{COMPANY_SUFFIX})\b", cleaned):
        return "CONTRACTOR"
    # SUDOP/CEIDG-style rows sometimes hold a JDG/trade line without an explicit
    # "pod firmą" phrase, e.g. "Jan Kowalski Software". A pure two-token name
    # remains PERSON, but a person name plus a trade tail is a CONTRACTOR.
    parts = cleaned.split()
    if len(parts) >= 3 and _looks_like_person_name(" ".join(parts[:2])):
        return "CONTRACTOR"
    if _looks_like_person_name(cleaned) or _looks_like_person_name(stripped):
        return "PERSON"
    tokens = re.findall(rf"[{LATIN_LETTERS}0-9.&_\-]+", cleaned)
    if 1 <= len(tokens) <= 10 and any(any(ch.isupper() for ch in t) or "." in t or '-' in t or t.isupper() for t in tokens):
        if not _looks_like_generic_document_title_tail(cleaned):
            return "CONTRACTOR"
    return None


def _public_business_name_label_category(value: str) -> str | None:
    """Stricter classifier for generic 'nazwa pełna/skrócona' rows.

    These labels can describe a contractor, but also a product or document title.
    Require business-like evidence so 'Nazwa pełna: Regulamin sklepu' is not
    anonymized, while 'KXG Legal' and law-firm/company lines still are.
    """
    cleaned = _clean_alias(value)
    if not cleaned or _is_legal_term(cleaned):
        return None
    norm = deaccent_role(cleaned)
    if re.search(r"KANCELARIA|ADWOKACKA|RADCOWSKA|NOTARIALNA|BIURO|FUNDACJA|STOWARZYSZENIE|SPOLKA|SP\.?\s*[ZJKA]\.?|S\.?A\.?|S\.?C\.?", norm):
        return "CONTRACTOR"
    if re.search(rf"(?i)\b(?:{COMPANY_SUFFIX})\b", cleaned):
        return "CONTRACTOR"
    parts = cleaned.split()
    if len(parts) >= 3 and _looks_like_person_name(" ".join(parts[:2])):
        return "CONTRACTOR"
    if _looks_like_person_name(cleaned):
        return "PERSON"
    tokens = re.findall(rf"[{LATIN_LETTERS}0-9.&_\-]+", cleaned)
    distinctive = any(t.isupper() or "." in t or "-" in t or "&" in t or any(ch.isdigit() for ch in t) for t in tokens)
    return "CONTRACTOR" if distinctive and not _looks_like_generic_document_title_tail(cleaned) else None


def _extract_confidential_context_candidates(text: str) -> List[Finding]:
    findings: List[Finding] = []
    for m in CONTRACT_REGISTRY_PARTY_PATTERN.finditer(text or ""):
        raw = m.group("party") or ""
        value = _trim_public_party_value(raw)
        cat = _public_party_category(value)
        if cat:
            local_start = raw.find(value)
            start = m.start("party") + (local_start if local_start >= 0 else 0)
            findings.append(Finding(cat, value, start, start + len(value)))
    for m in BUSINESS_NAME_LABEL_PATTERN.finditer(text or ""):
        raw = m.group("party") or ""
        value = _trim_public_party_value(raw)
        cat = _public_business_name_label_category(value)
        if cat:
            local_start = raw.find(value)
            start = m.start("party") + (local_start if local_start >= 0 else 0)
            findings.append(Finding(cat, value, start, start + len(value)))
    _append_contextual_person_findings(text, findings)
    for m in KGL_LAW_FIRM_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw)
        if value:
            start = m.start("company") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("COMPANY", value, start, start + len(value)))
    for m in PERSON_MULTIPART_KNOWN_PATTERN.finditer(text or ""):
        raw = m.group("name") or ""
        value, start = _strip_leading_person_context_words(raw, m.start("name"))
        parts = value.split()
        second_is_name = len(parts) >= 3 and is_first_name_form(parts[1])
        if ((len(parts) == 2 and _looks_like_person_name(value)) or (len(parts) >= 3 and second_is_name and _looks_like_person_name(value))):
            findings.append(Finding("PERSON", value, start, start + len(value)))
    for m in PERSON_CONCATENATED_AFTER_TEXT_PATTERN.finditer(text or ""):
        raw = m.group("name") or ""
        value, start = _strip_leading_person_context_words(raw, m.start("name"))
        if _looks_like_person_name(value):
            findings.append(Finding("PERSON", value, start, start + len(value)))
    # Abbreviated forename + surname ("J. Kowalski"). The whole span is masked as
    # one PERSON. Guard against defined terms / role words used as the surname.
    for m in INITIAL_SURNAME_PATTERN.finditer(text or ""):
        surname = m.group("surname") or ""
        if not surname or _is_legal_term(surname) or _is_role_alias(surname):
            continue
        if deaccent_role(surname).upper() in COMMON_UPPERCASE_STOPWORDS:
            continue
        value = _clean_alias(m.group(0))
        findings.append(Finding("PERSON", value, m.start(), m.end()))
    for m in PROFESSIONAL_PARTNERSHIP_COMPANY_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw)
        if value and not PUBLIC_ADMIN_ORG_RE.search(value) and not _is_legal_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("COMPANY", value, start, start + len(value)))

    # Quick pre-filter: only run the expensive civil-partnership regex when the
    # text actually contains a civil-partnership suffix marker.  This avoids
    # catastrophic backtracking on long documents that have no s.c. / spółka cywilna.
    for m in (CIVIL_PARTNERSHIP_PATTERN.finditer(text) if _SC_MARKER_RE.search(text or "") else []):
        raw = m.group("company") or ""
        value = _clean_alias(raw)
        if value and not _is_legal_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("COMPANY", value, start, start + len(value)))

    for m in ORG_CONTEXT_NAME_PATTERN.finditer(text or ""):
        value = _clean_alias(m.group("company") or "")
        if value and not value[:1].islower() and not _is_legal_or_defined_term(value) and not PUBLIC_ADMIN_ORG_RE.search(value):
            findings.append(Finding("CONTRACTOR", value, m.start("company"), m.start("company") + len(m.group("company") or "")))
    for m in DOCUMENT_TITLE_COMPANY_PATTERN.finditer(text or ""):
        value = _clean_alias(m.group("company") or "")
        if (
            value
            and not value[:1].islower()
            and not _looks_like_generic_document_title_tail(value)
            and not _is_legal_or_defined_term(value)
            and not PUBLIC_ADMIN_ORG_RE.search(value)
        ):
            findings.append(Finding("CONTRACTOR", value, m.start("company"), m.start("company") + len(m.group("company") or "")))
    for m in PARTY_CONTEXT_COMPANY_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw.strip(" \"„”'"))
        # Require at least two tokens or a distinctive all-caps token. Avoid legal headings.
        meaningful = [t for t in re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ0-9]{2,}", value.upper()) if t not in {"VAT", "KRS", "NIP", "REGON", "PESEL"}]
        # The party-context detector is intentionally broad, but it must not
        # swallow ordinary prose after labels such as "Powód okazał dowód...".
        # Party names here should start like a proper name / company token;
        # lower-case verb phrases and identity-document prose are rejected.
        if value and value[:1].islower():
            continue
        if re.search(r"\.\s+[A-ZĄĆĘŁŃÓŚŹŻ]", value) or re.fullmatch(r"[A-Z0-9][A-Z0-9./_\-]{3,80}", value):
            continue
        # Party labels can introduce natural persons as well as companies
        # ("Powód Jan Nowak", "Pozwany Anna Kowalska"). Do not convert
        # a validated Polish personal name into a company/contractor.
        if value and _looks_like_person_name(value):
            continue
        if re.search(r"(?i)\b(?:dow[oó]d\s+osobisty|paszport|legitymuj)", value):
            continue
        if value and meaningful and not _all_meaningful_tokens_are_upper_stopwords(value) and not _is_legal_or_defined_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip(" \"„”'")))
            findings.append(Finding("CONTRACTOR", value, start, start + len(value)))
    for m in AGAINST_CONTEXT_COMPANY_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw.strip(" \"„”'"))
        meaningful = [t for t in re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ0-9]{2,}", value.upper()) if t not in {"VAT", "KRS", "NIP", "REGON", "PESEL"}]
        if value and meaningful and not _all_meaningful_tokens_are_upper_stopwords(value) and not _is_legal_or_defined_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip(" \"„”'")))
            findings.append(Finding("CONTRACTOR", value, start, start + len(value)))
    for m in CEIDG_BUSINESS_NAME_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw)
        if value and not _is_legal_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("CONTRACTOR", value, start, start + len(value)))
            # In CEIDG firm names, the short trade-name token is often reused in
            # contract numbers and later clauses (e.g. AMZ, Omnitex). Add it as a
            # confidential company code if it is not a legal stopword.
            for token_match in re.finditer(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ0-9&.-]{2,14}\b|\b[A-ZŁŚŻŹĆŃÓĘĄ][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9&.-]{3,}\b", value):
                token = token_match.group(0)
                if token.upper() in COMMON_UPPERCASE_STOPWORDS or _is_role_alias(token) or _is_legal_term(token):
                    continue
                # Prefer distinctive trade words/acronyms over common first/surnames.
                if _looks_like_person_name(value) and token == value.split()[0]:
                    continue
                findings.append(Finding("COMPANY_CODE_CONTEXT", token, start + token_match.start(), start + token_match.end()))
    for m in PARENT_FIRST_NAMES_ROW_PATTERN.finditer(text or ""):
        names = m.group("names") or ""
        base = m.start("names")
        for nm in re.finditer(r"[A-ZŁŚŻŹĆŃÓĘĄ][a-złśżźćńóęą]{2,}", names):
            findings.append(Finding("PERSON_ALIAS", nm.group(0), base + nm.start(), base + nm.end()))
    for m in SURNAME_ONLY_LEGAL_ROW_PATTERN.finditer(text or ""):
        value = _clean_alias(m.group("surname") or "")
        if value and not _is_legal_term(value):
            findings.append(Finding("PERSON_ALIAS", value, m.start("surname"), m.start("surname") + len(value)))
    for m in PO_BOX_ADDRESS_PATTERN.finditer(text or ""):
        findings.append(Finding("ADDRESS_FULL", m.group(0), m.start(), m.end()))
    for m in BIRTH_DATA_ROW_PATTERN.finditer(text or ""):
        raw = m.group("birth") or ""
        value = _clean_alias(raw)
        if value:
            start = m.start("birth") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("BIRTH_DATA", value, start, start + len(value)))
    for m in ADDRESS_REVERSE_FULL_PATTERN.finditer(text or ""):
        findings.append(Finding("ADDRESS_FULL", m.group(0), m.start(), m.end()))
    for m in ADDRESS_REVERSE_LABEL_PATTERN.finditer(text or ""):
        raw = m.group("addr") or ""
        value = _clean_alias(raw)
        if value:
            findings.append(Finding("ADDRESS_FULL", value, m.start("addr"), m.start("addr") + len(raw)))
    for m in SOLE_PROPRIETOR_LABEL_PATTERN.finditer(text or ""):
        raw = m.group("company") or ""
        value = _clean_alias(raw)
        if value and not (len(value.split()) <= 2 and _looks_like_person_name(value)) and not _is_legal_term(value):
            start = m.start("company") + (len(raw) - len(raw.lstrip()))
            findings.append(Finding("CONTRACTOR", value, start, start + len(value)))
    for m in ADDRESS_RESIDENCE_LOCALITY_PATTERN.finditer(text or ""):
        raw = m.group("place") or ""
        value = _clean_alias(raw)
        if value and not PUBLIC_ADMIN_ORG_RE.search(value) and not _is_legal_term(value):
            findings.append(Finding("ADDRESS", value, m.start("place"), m.start("place") + len(raw)))
    for pattern in (IDCARD_PL_CONTEXT_PATTERN, IDCARD_PL_LEGAL_CONTEXT_PATTERN):
        for m in pattern.finditer(text or ""):
            value = _clean_alias((m.group("id") or "").replace("", " "))
            if value:
                cat = "IDCARD_PL" if valid_idcard_pl(value) else "IDCARD_PL_CONTEXT"
                findings.append(Finding(cat, value, m.start("id"), m.start("id") + len(m.group("id") or "")))
    contextual_id_patterns = (
        ("BDO", BDO_CONTEXT_PATTERN),
        ("CEIDG_ID", CEIDG_ID_CONTEXT_PATTERN),
        ("CASE_REF", CASE_REF_CONTEXT_PATTERN),
        ("PERMIT_ID", PERMIT_LICENSE_CONTEXT_PATTERN),
        ("VEHICLE_ID", VEHICLE_VIN_PATTERN),
        ("VEHICLE_ID", VEHICLE_REG_CONTEXT_PATTERN),
        ("VEHICLE_ID", VEHICLE_ENGINE_BODY_CONTEXT_PATTERN),
        ("PASSPORT_CONTEXT", PASSPORT_CONTEXT_PATTERN),
        ("RESIDENCE_CARD", RESIDENCE_CARD_CONTEXT_PATTERN),
        ("DRIVING_LICENSE", DRIVING_LICENSE_CONTEXT_PATTERN),
        ("PROF_LICENSE", PROF_LICENSE_CONTEXT_PATTERN),
        ("PROPERTY_ID", PROPERTY_ID_CONTEXT_PATTERN),
        ("EDELIVERY_ID", EDELIVERY_EPUAP_CONTEXT_PATTERN),
        ("POLICY_CLAIM_ID", POLICY_CLAIM_CONTEXT_PATTERN),
        ("SHIPMENT_ID", SHIPMENT_CONTEXT_PATTERN),
        ("PROJECT_ID", PROJECT_ORDER_CONTEXT_PATTERN),
        ("DOMAIN", DOMAIN_CONTEXT_PATTERN),
        ("LOGIN", LOGIN_CONTEXT_PATTERN),
        ("SECRET", API_SECRET_CONTEXT_PATTERN),
        ("ACCOUNT_ID", ACCOUNT_ID_CONTEXT_PATTERN),
        ("REPOSITORY", REPOSITORY_CONTEXT_PATTERN),
        ("FINANCIAL_DOC_ID", FINANCIAL_DOC_CONTEXT_PATTERN),
        ("VAT_ID", VAT_ID_CONTEXT_PATTERN),
        ("MEDICAL_RECORD_ID", MEDICAL_RECORD_CONTEXT_PATTERN),
        ("EMPLOYEE_ID", EMPLOYEE_ID_CONTEXT_PATTERN),
        ("CUSTOMER_ID", CUSTOMER_VENDOR_ID_CONTEXT_PATTERN),
        ("BUSINESS_ID", BUSINESS_ID_CONTEXT_PATTERN),
        ("PROJECT_ID", PROCUREMENT_NOTICE_CONTEXT_PATTERN),
        ("PROPERTY_UNIT_ID", PROPERTY_UNIT_CONTEXT_PATTERN),
        ("REPERTORIUM", NOTARIAL_ACT_CONTEXT_PATTERN),
        ("BANK_ACCOUNT", BANK_ACCOUNT_CONTEXT_PATTERN),
        ("BANK_ACCOUNT", BANK_ACCOUNT_OWNER_CONTEXT_PATTERN),
    )
    for cat, pattern in contextual_id_patterns:
        for m in pattern.finditer(text or ""):
            raw = m.group("id") or ""
            value = _clean_alias(raw.replace("", " "))
            if value:
                if cat == "PROJECT_ID" and not category_ok("PROJECT_ID", value):
                    continue
                findings.append(Finding(cat, value, m.start("id"), m.start("id") + len(raw)))
    for m in CONTRACT_NUMBER_COMPANY_TOKEN_PATTERN.finditer(text or ""):
        block = m.group("num") or ""
        base_start = m.start("num")
        for tm in re.finditer(r"[A-ZĄĆĘŁŃÓŚŹŻ]{3,}(?=/|$)", block):
            token = tm.group(0)
            if token in COMMON_UPPERCASE_STOPWORDS or token in {"B2B", "B2C", "FIK", "VAT", "KRS", "NIP", "REGON"}:
                continue
            findings.append(Finding("COMPANY_CODE_CONTEXT", token, base_start + tm.start(), base_start + tm.end()))
    for pattern in (LEGAL_ROLE_PERSON_AFTER_PATTERN, LEGAL_ROLE_PERSON_BEFORE_PATTERN):
        for m in pattern.finditer(text or ""):
            raw = m.group("name") or ""
            value, start = _strip_leading_person_context_words(raw, m.start("name"))
            if value and _looks_like_person_name(value):
                findings.append(Finding("PERSON", value, start, start + len(value)))
    for m in CONTRACTOR_CONTEXT_PATTERN.finditer(text):
        block = _clean_alias(m.group(1))
        if not block:
            continue
        if re.match(r"(?i)^(?:reprezentacja|dane\s+reprezentanta|projekt|finanse|bezpieczeństwo|bezpieczenstwo|osoba\s+główna|osoba\s+glowna|rozliczenia|zastępstwo|zastepstwo)\b", block):
            continue
        block = _clean_alias(TRAILING_CONTEXT_RE.sub("", block))
        block = re.split(r"(?i),?\s*(?:kontakt|osoba do kontaktu|reprezentowan(?:a|y|e)|e-mail|email|tel\.?|telefon|NIP|REGON|KRS)\b", block)[0]
        block = re.split(r"\s+[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", block)[0]
        block = _clean_alias(block)
        if re.fullmatch(r"[A-Z0-9][A-Z0-9./_\-]{3,80}", block):
            continue
        if _is_probably_confidential_alias(block):
            start = m.start(1)
            end = start + len(block)
            if end > start:
                findings.append(Finding("CONTRACTOR", text[start:end], start, end))
    person_re = re.compile(rf"{PERSON_NAME_LOOSE}")
    for m in CONTACT_CONTEXT_PATTERN.finditer(text):
        block = m.group(1)
        for pm in person_re.finditer(block):
            start = m.start(1) + pm.start()
            end = m.start(1) + pm.end()
            value = text[start:end]
            if _is_contextual_person_candidate(value):
                findings.append(Finding("PERSON", value, start, end))
    return findings


def collect_contextual_findings(text: str, base_findings: List[Finding]) -> List[Finding]:
    contextual: List[Finding] = []
    literal_requests: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def company_aliases_cached(value: str) -> Set[str]:
        cleaned = _clean_alias(value)
        if not cleaned:
            return set()
        return _company_aliases(cleaned)

    def extend_literal_once(value: str, category: str) -> None:
        cleaned = _clean_alias(value)
        if not cleaned:
            return
        key = (category, cleaned.casefold())
        if key in literal_requests:
            return
        literal_requests[key] = (category, cleaned)

    contextual.extend(_extract_confidential_context_candidates(text))
    # Contextual company/code detections (for example tokens embedded in
    # contract numbers) should seed later literal occurrences, but without
    # returning to global string replacement. Add those later occurrences as
    # explicit findings so span-based masking remains precise. Cache literal
    # scans per unique alias/category: long contracts often repeat the same
    # party hundreds of times, and rescanning the full document for every
    # repeated finding made runtime grow superlinearly.
    for cf in list(contextual):
        if cf.category in {"COMPANY", "COMPANY_CODE", "COMPANY_CODE_CONTEXT", "CONTRACTOR", "PROJECT"}:
            base_value = _clean_alias(cf.value)
            for alias in company_aliases_cached(cf.value) or {base_value}:
                if alias:
                    alias_category = cf.category if alias == base_value else (f"{cf.category}_ALIAS" if cf.category != "COMPANY_CODE" else "COMPANY_ALIAS")
                    extend_literal_once(alias, alias_category)
            # For partnerships ("i Wspólnicy"), extract each partner surname and add
            # it to the literal scan so standalone references ("Pan Głąb", "Kantorowski
            # podpisał") are also masked.
            # NOTE: do NOT check is_surname() here — rare Polish surnames like "Głąb"
            # or "Kantorowski" are NOT in the PESEL gazetteer but are definitively
            # surnames when they appear as named partners in a firm.
            if cf.category == "COMPANY" and re.search(r"[Ii]\s+[Ww]sp[oó]lni", cf.value):
                for tok_m in _PARTNER_TOKEN_RE.finditer(cf.value):
                    tok = tok_m.group(1)
                    if tok in _PARTNER_SKIP_WORDS:
                        continue
                    extend_literal_once(tok, "PERSON_ALIAS")
    # First-name- and surname-only mentions are masked only when they are
    # unambiguous in this document. Otherwise a bare "Kowalski" between two
    # distinct people called Kowalski would be misattributed at restore time.
    first_name_to_people: Dict[str, Set[str]] = {}
    surname_to_people: Dict[str, Set[str]] = {}
    for pf in base_findings:
        if pf.category == "PERSON":
            parts = _person_parts(pf.value)
            if parts:
                identity = _canonical_person_value(pf.value)
                first_name_to_people.setdefault(_first_name_key(parts[0]), set()).add(identity)
                surname_to_people.setdefault(_surname_key(parts[-1]), set()).add(identity)
    for m in CONFIDENTIAL_ALIAS_PATTERN.finditer(text):
        alias = _clean_alias(m.group(1) or m.group(2) or "")
        if _is_probably_confidential_alias(alias):
            extend_literal_once(alias, "ALIAS")
            for alias_variant in company_aliases_cached(alias):
                extend_literal_once(alias_variant, "ALIAS")
    for f in base_findings:
        if f.category == "EMAIL":
            dm = DOMAIN_FROM_EMAIL_RE.search(f.value)
            if dm:
                for domain in _domain_variants(dm.group(1)):
                    extend_literal_once(domain, "DOMAIN_ALIAS")
        elif f.category == "URL":
            host = re.sub(r"(?i)^https?://", "", f.value).split("/")[0]
            for domain in _domain_variants(host):
                extend_literal_once(domain, "DOMAIN_ALIAS")
        elif f.category in {"COMPANY", "COMPANY_CODE", "COMPANY_CODE_CONTEXT", "CONTRACTOR", "PROJECT"}:
            for alias in company_aliases_cached(f.value):
                if alias != f.value:
                    extend_literal_once(alias, f"{f.category}_ALIAS" if f.category != "COMPANY_CODE" else "COMPANY_ALIAS")
        elif f.category == "COURT":
            for alias in _court_aliases(f.value):
                if alias != f.value:
                    extend_literal_once(alias, "COURT_ALIAS")
        elif f.category == "PERSON":
            parts = _person_parts(f.value)
            include_first = False
            include_surname = True
            if parts:
                include_first = len(first_name_to_people.get(_first_name_key(parts[0]), set())) == 1
                include_surname = len(surname_to_people.get(_surname_key(parts[-1]), set())) == 1
            for alias in _person_aliases(f.value, include_first=include_first, include_surname=include_surname):
                if alias != f.value:
                    extend_literal_once(alias, "PERSON_ALIAS")
    if literal_requests:
        contextual.extend(_find_many_literal_occurrences(text, literal_requests.values()))
    return contextual


_GLINER_MODEL = None
_GLINER_ATTEMPTED = False


def _gliner_enabled() -> bool:
    return os.environ.get("CSMW_ENABLE_GLINER", "0").strip().lower() in {"1", "true", "yes", "on"}


def _load_gliner_model():
    """Load an optional local GLiNER model for residual PII scanning.

    This is deliberately opt-in and best-effort. The base CSM runtime does not
    depend on GLiNER; when the package/model is absent the scanner silently falls
    back to deterministic residual-risk regexes.
    """
    global _GLINER_MODEL, _GLINER_ATTEMPTED
    if _GLINER_ATTEMPTED:
        return _GLINER_MODEL
    _GLINER_ATTEMPTED = True
    if not _gliner_enabled():
        return None
    try:
        from gliner import GLiNER  # type: ignore
        model_name = os.environ.get("CSMW_GLINER_MODEL", "urchade/gliner_multi_pii-v1").strip()
        _GLINER_MODEL = GLiNER.from_pretrained(model_name)
        return _GLINER_MODEL
    except Exception:
        return None


def collect_gliner_residual_findings(text: str, threshold: float = 0.45) -> List[Finding]:
    model = _load_gliner_model()
    if model is None or not text:
        return []
    labels = [
        "person", "organization", "company", "address", "location", "bank account",
        "tax identification number", "national identification number", "passport number",
        "case number", "contract number", "email", "phone number", "website",
    ]
    try:
        entities = model.predict_entities(text, labels, threshold=threshold)
    except Exception:
        return []
    out: List[Finding] = []
    for ent in entities or []:
        try:
            value = _clean_alias(str(ent.get("text") or ""))
            start = int(ent.get("start"))
            end = int(ent.get("end"))
            label = str(ent.get("label") or "").lower()
        except Exception:
            continue
        if not value or value.startswith("[") or start < 0 or end <= start:
            continue
        if "person" in label:
            category = "PERSON_NLP"
        elif "org" in label or "company" in label:
            category = "COMPANY_NLP"
        elif "address" in label or "location" in label:
            category = "ADDRESS_NLP"
        else:
            category = "GLINER_PII"
        out.append(Finding(category, value, start, end))
    return out


def find_residual_risks(text: str, limit: int = 25) -> List[str]:
    """Return non-disclosing residual-risk messages after masking.

    The panel should not repeat exact suspected values. It reports risk classes/counts
    for manual review before Claude is used.
    """
    risk_patterns = {
        "możliwe imię i nazwisko": re.compile(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{1,}(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{1,})?\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,}(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,})?\b"),
        "możliwy skrót/nazwa własna": re.compile(r"\b[A-ZĄĆĘŁŃÓŚŹŻ0-9&.-]{3,14}\b"),
        "możliwy e-mail": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "możliwy rachunek bankowy": re.compile(r"(?i)(?:rachunek|rachunku|konto|IBAN|NRB|przelew|bank)[^\n]{0,40}(?:PL[\s\u00A0\u202F\-–—]*)?(?:\d[\s\u00A0\u202F\-–—]*){26}(?!\d)"),
        "możliwa domena": re.compile(r"\b(?:www\.)?[A-Za-z0-9\-]+\.(?:pl|com|eu|org|net|io|ai|dev|biz|info)\b", re.IGNORECASE),
        "możliwa nazwa projektu/systemu": re.compile(rf"\b(?i:(?:{PROJECT_KEYWORDS}))\s+[A-ZŁŚŻŹĆŃÓĘĄ0-9][A-Za-zŁŚŻŹĆŃÓĘĄłśżźćńóęą0-9&\-]+"),
    }
    counts: Dict[str, int] = {}
    for label, pattern in risk_patterns.items():
        seen_values: Set[str] = set()
        for m in pattern.finditer(text):
            value = _clean_alias(m.group(0))
            up = value.upper()
            if not value or value.startswith("[") or up in COMMON_UPPERCASE_STOPWORDS or _is_role_alias(value):
                continue
            if re.fullmatch(r"(?:PERSON|PERSON_ALIAS|COMPANY|COMPANY_ALIAS|COMPANY_CODE|COMPANY_CODE_CONTEXT|ALIAS|EMAIL|PHONE|PESEL|NIP|REGON|KRS|BDO|CEIDG_ID|IBAN|BANK_ACCOUNT|KW|LAND_REGISTER|CASE_REF|PERMIT_ID|VEHICLE_ID|PASSPORT_CONTEXT|RESIDENCE_CARD|DRIVING_LICENSE|PROF_LICENSE|PROPERTY_ID|PROPERTY_UNIT_ID|EDELIVERY_ID|POLICY_CLAIM_ID|SHIPMENT_ID|PROJECT_ID|ACCOUNT_ID|LOGIN|REPOSITORY|FINANCIAL_DOC_ID|VAT_ID|MEDICAL_RECORD_ID|EMPLOYEE_ID|CUSTOMER_ID|BUSINESS_ID|IP_ADDRESS|URL|SYGNATURA|COURT|COURT_ALIAS|ADDRESS|DOMAIN|DOMAIN_ALIAS|CONTRACTOR|CONTRACTOR_ALIAS|PROJECT|PROJECT_ALIAS|SECRET|IDCARD_PL|IDCARD_PL_CONTEXT|PASSPORT_PL|POSTCODE_PL|BIRTH_DATA)_\d+", up):
                continue
            seen_values.add(value)
        if seen_values:
            counts[label] = len(seen_values)
    gliner_findings = collect_gliner_residual_findings(text)
    if gliner_findings:
        by_category: Dict[str, int] = {}
        for f in gliner_findings:
            by_category[f.category] = by_category.get(f.category, 0) + 1
        for category, count in sorted(by_category.items()):
            counts[f"możliwe PII wg GLiNER ({category})"] = count
    risks = [f"{label}: {count} potencjalne wystąpienie/a" for label, count in sorted(counts.items())]
    return risks[:limit]



def _replacement_original_and_category(replacement: Any) -> tuple[str, str]:
    """Return (original, category) from either a Replacement or a dict payload."""
    if isinstance(replacement, dict):
        return str(replacement.get("original") or ""), str(replacement.get("category") or "UNKNOWN")
    return str(getattr(replacement, "original", "") or ""), str(getattr(replacement, "category", "UNKNOWN") or "UNKNOWN")


def _contains_original_value(text: str, original: str) -> bool:
    value = unicodedata.normalize("NFC", _clean_alias(original))
    if not value or value.startswith("["):
        return False
    haystack = unicodedata.normalize("NFC", text or "")
    if not haystack:
        return False
    # Word-boundary matching for simple tokens/phrases prevents short values from
    # firing inside unrelated words, while punctuation-rich identifiers (emails,
    # account numbers, case refs) are safer with literal containment.
    if re.fullmatch(r"[\wĄĆĘŁŃÓŚŹŻąćęłńóśźż .\-]+", value, flags=re.UNICODE):
        pattern = r"(?<![\wĄĆĘŁŃÓŚŹŻąćęłńóśźż])" + re.escape(value) + r"(?![\wĄĆĘŁŃÓŚŹŻąćęłńóśźż])"
        return bool(re.search(pattern, haystack))
    return value in haystack


def find_unmasked_original_residuals(masked_text: str, replacements: Iterable[Any], limit: int = 20) -> List[str]:
    """Report exact originals from the map that still survive after masking.

    This is the post-mask safety gate inspired by the Matematic residual-PII
    pattern: it compares the produced text against the local re-identification
    map and reports only category/count information. It never echoes source
    values, so the warning itself is safe to show in the UI or audit-adjacent
    reports.
    """
    by_category: Dict[str, int] = {}
    seen_values: Set[tuple[str, str]] = set()
    for replacement in replacements or []:
        original, category = _replacement_original_and_category(replacement)
        cleaned = _clean_alias(original)
        if len(cleaned) < 4:
            continue
        key = (category, cleaned.casefold())
        if key in seen_values:
            continue
        seen_values.add(key)
        if _contains_original_value(masked_text, cleaned):
            by_category[category] = by_category.get(category, 0) + 1
    warnings = [
        f"bramka residual PII: {category}: {count} oryginalne wartości nadal widoczne — sprawdź dokument przed użyciem AI"
        for category, count in sorted(by_category.items())
    ]
    return warnings[:limit]


def find_quality_gate_warnings(masked_text: str, replacements: Iterable[Any], limit: int = 30) -> List[str]:
    """Combined non-disclosing post-mask QA warnings."""
    out: List[str] = []
    out.extend(find_residual_risks(masked_text, limit=limit))
    remaining = max(0, limit - len(out))
    if remaining:
        out.extend(find_unmasked_original_residuals(masked_text, replacements, limit=remaining))
    return out[:limit]


REVIEW_MODES = {"standard", "light", "bielik"}


def normalize_review_mode(mode: str | None = None) -> str:
    value = (mode or "standard").strip().lower()
    aliases = {
        "fast": "standard",
        "quick": "standard",
        "szybki": "standard",
        "dokladny": "light",
        "dokładny": "light",
        "dokladniejszy": "light",
        "dokładniejszy": "light",
        "ai": "bielik",
    }
    value = aliases.get(value, value)
    if value not in REVIEW_MODES:
        raise ValueError(f"Unsupported review_mode: {mode}")
    return value


def collect_light_residual_review_findings(masked_text: str, replacements: Iterable[Any], limit: int = 30) -> List[str]:
    """Light post-mask review, reported without source values.

    This layer is deliberately separate from collect_findings(): it runs after
    masking and produces category/count warnings only. It may use optional local
    deterministic or NLP scanners, but it never requires Bielik.
    """
    return find_quality_gate_warnings(masked_text, replacements, limit=limit)


def _finding_overlaps_placeholder(text: str, finding: Finding) -> bool:
    if not text or finding.start < 0 or finding.end <= finding.start:
        return False
    window = text[max(0, finding.start - 64): min(len(text), finding.end + 64)]
    for match in PLACEHOLDER_RE.finditer(window):
        abs_start = max(0, finding.start - 64) + match.start()
        abs_end = max(0, finding.start - 64) + match.end()
        if finding.start < abs_end and finding.end > abs_start:
            return True
    return False


def _looks_like_form_label(value: str) -> bool:
    cleaned = _clean_alias(value).lower()
    if not cleaned:
        return True
    if cleaned in _GLOBAL_LABEL_STOPLIST:
        return True
    words = cleaned.split()
    if 1 <= len(words) <= 4 and all(deaccent_role(w) in {deaccent_role(x) for x in LEGAL_WORD_STOPLIST} for w in words):
        return True
    return False


def score_residual_candidate(text: str, finding: Finding, replacements: Iterable[Any]) -> float:
    """Score a post-mask residual-review candidate without exposing its value."""
    value = _clean_alias(finding.value)
    if not value:
        return 0.0
    score = 0.0
    high_risk = {"EMAIL", "PESEL", "NIP", "BANK_ACCOUNT", "IBAN", "SECRET", "URL", "DOMAIN"}
    if _canonical_entity_category(finding.category) in high_risk or finding.category in high_risk:
        score += 0.4

    start = max(0, int(finding.start or 0))
    end = max(start, int(finding.end or start))
    context = text[max(0, start - 80): min(len(text or ""), end + 80)]
    has_context = bool(re.search(
        r"(?i)\b(umow|stron|klient|kontrahent|spółk|firma|adres|siedzib|pesel|nip|regon|krs|rachun|konto|bank|pełnomocnik|reprezent|sekret|token|klucz|hasł)",
        context,
    ))
    if has_context:
        score += 0.3
    if category_ok(finding.category, value):
        score += 0.2
    if value and (text or "").count(value) > 1:
        score += 0.2
    if _is_legal_or_defined_term(value) or _looks_like_form_label(value):
        score -= 0.5
    if _looks_like_form_label(value):
        score -= 0.4
    if not has_context:
        score -= 0.3
    if _finding_overlaps_placeholder(text or "", finding):
        score -= 1.0
    for replacement in replacements or []:
        original, _category = _replacement_original_and_category(replacement)
        if original and original.casefold() == value.casefold():
            score += 0.2
            break
    return max(-1.0, min(1.0, score))


def collect_bielik_deep_review_findings(masked_text: str, replacements: Iterable[Any] = (), min_score: float = 0.45) -> List[Finding]:
    """Run Bielik as optional review-only detector after masking."""
    findings: List[Finding] = []
    for f in collect_bielik_findings(masked_text or ""):
        if not category_ok(f.category, f.value):
            continue
        if score_residual_candidate(masked_text or "", f, replacements) < min_score:
            continue
        findings.append(f)
    return remove_overlaps(findings)


# ── Uncertain-value reviewer (local, opt-in remasking) ────────────────────────
# This is intentionally *not* another aggressive anonymizer.  It produces a
# short, local-only list of doubtful values that the user may explicitly add to
# manual controls.  The normal masking/restore map remains the source of truth.
_UNCERTAIN_LABEL_RE = re.compile(
    r"(?im)^(?P<label>\s*(?:nazwa\s+(?:robocza|skrócona|pelna|pełna)(?:\s+(?:projektu|systemu|usługi|uslugi|platformy|aplikacji))?|projekt|system|usługa|beneficjent(?:\s+pomocy)?|kontrahent(?:/nazwa)?|wykonawca|dostawca|podwykonawca|osoba\s+kontaktowa|kontakt|administrator|użytkownik|uzytkownik|login|identyfikator(?:\s+(?:klienta|kontrahenta|użytkownika|uzytkownika))?|nr\s+klienta|numer\s+klienta|vendor[_\s-]?id|tenant[_\s-]?id|client[_\s-]?id|project[_\s-]?id)\s*[:\-–—]\s*)(?P<value>[^\r\n;]{3,120})"
)
_UNCERTAIN_REVERSE_ADDRESS_RE = re.compile(
    r"\b\d{2}-\d{3}\s+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ.-]{2,}(?:,\s*(?:ul\.\s*)?[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ.-]{2,}\s+\d+[A-Za-z]?(?:\s*(?:lok\.?|m\.?|apt\.?)\s*\d+[A-Za-z]?)?)"
)
_UNCERTAIN_PROJECT_RE = re.compile(
    r"(?i)\b(?:projekt|system|wdrożenie|wdrozenie|platforma|aplikacja|serwis)\s+(?:pod\s+)?(?:nazwą|nazwa|roboczo)?\s*[\"„]?([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ0-9][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9-]+){1,5})[\"”]?"
)
_UNCERTAIN_COMPANY_PHRASE_RE = re.compile(
    r"(?i)\b(?:wykonawca|dostawca|podwykonawca|partner|kontrahent)\s+(?:to|jest|będzie|bedzie|występuje\s+jako|wystepuje\s+jako)\s+([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ&.-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ0-9][\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9&.-]+){1,5})"
)
_UNCERTAIN_VALUE_CLEAN_RE = re.compile(r"\s*(?:,\s*(?:tel\.?|telefon|e-mail|email|adres|NIP|REGON|KRS)\b.*)$", re.I)

_UNCERTAIN_CATEGORY_BY_LABEL = [
    (re.compile(r"(?i)login|użytkownik|uzytkownik"), "LOGIN"),
    (re.compile(r"(?i)vendor|tenant|client|identyfikator|nr\s+klienta|numer\s+klienta|project"), "ACCOUNT_ID"),
    (re.compile(r"(?i)adres"), "ADDRESS"),
    (re.compile(r"(?i)projekt|system|usługa|platforma|aplikacja|serwis"), "PROJECT"),
    (re.compile(r"(?i)beneficjent|kontrahent|wykonawca|dostawca|podwykonawca|nazwa"), "CONTRACTOR"),
    (re.compile(r"(?i)osoba\s+kontaktowa|kontakt|administrator"), "PERSON"),
]


def _replacement_original_set(replacements: Iterable[Any]) -> Set[str]:
    out: Set[str] = set()
    for replacement in replacements or []:
        original, _category = _replacement_original_and_category(replacement)
        cleaned = _clean_alias(original)
        if cleaned:
            out.add(cleaned.casefold())
    return out


def _uncertain_category_from_label(label: str, fallback: str = "MANUAL") -> str:
    for pattern, category in _UNCERTAIN_CATEGORY_BY_LABEL:
        if pattern.search(label or ""):
            return category
    return fallback


def _clean_uncertain_value(value: str) -> str:
    cleaned = _clean_alias(_UNCERTAIN_VALUE_CLEAN_RE.sub("", value or ""))
    cleaned = re.split(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])", cleaned, maxsplit=1)[0]
    cleaned = cleaned.strip(" .,:;–—-()[]{}<>\"'„”")
    # Avoid swallowing a whole explanatory sentence.  The reviewer needs a short
    # candidate that can safely be added to manual controls.
    cleaned = re.split(r"\s+(?:zgodnie|dalej|zwany|zwana|zwane|któr[ayego]|ktory|która|ktore|oraz|w\s+ramach)\b", cleaned, maxsplit=1, flags=re.I)[0].strip(" .,:;–—-()[]{}<>\"'„”")
    return cleaned[:120]


def _looks_like_uncertain_candidate(value: str) -> bool:
    cleaned = _clean_alias(value)
    if len(cleaned) < 4 or PLACEHOLDER_RE.search(cleaned):
        return False
    if _looks_like_form_label(cleaned) or _is_legal_or_defined_term(cleaned):
        return False
    if re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{1,3}", cleaned):
        return False
    if re.fullmatch(r"\d+[.,]?\d*", cleaned):
        return False
    tokens = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9_-]+", cleaned)
    if len(tokens) > 8:
        return False
    # Must look like a name/entity/id/address, not a generic prose fragment.
    if re.search(r"\d{2}-\d{3}|[A-Z]{2,}[-_/]\d|[_/@]|\d", cleaned):
        return True
    titled = [t for t in tokens if re.match(r"^[A-ZĄĆĘŁŃÓŚŹŻ]", t)]
    return len(titled) >= 2


def _uncertain_context(text: str, start: int, end: int, radius: int = 54) -> str:
    raw = (text or "")[max(0, start - radius): min(len(text or ""), end + radius)]
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:180]


def collect_uncertain_review_candidates(text: str, replacements: Iterable[Any] = (), limit: int = 25) -> List[Dict[str, Any]]:
    """Return local-only doubtful values that a user may add to manual controls.

    The result intentionally contains raw text values, so it must only be shown in
    the local Word taskpane/modal and must not be copied into audit logs or normal
    non-disclosing reports.  The function is conservative: candidates are not
    masked automatically; the user explicitly selects them.
    """
    source = text or ""
    already = _replacement_original_set(replacements)
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def add_candidate(value: str, category: str, reason: str, start: int, end: int, confidence: str = "medium") -> None:
        cleaned = _clean_uncertain_value(value)
        if not _looks_like_uncertain_candidate(cleaned):
            return
        key = cleaned.casefold()
        if key in seen or key in already:
            return
        # Also skip if the candidate is contained entirely in an already-masked original.
        if any(key and key in original for original in already):
            return
        seen.add(key)
        out.append({
            "value": cleaned,
            "category": _canonical_entity_category(category),
            "suggested_category": _canonical_entity_category(category),
            "reason": reason,
            "confidence": confidence,
            "context": _uncertain_context(source, max(0, start), max(0, end)),
        })

    for match in _UNCERTAIN_LABEL_RE.finditer(source):
        label = match.group("label") or ""
        value = match.group("value") or ""
        add_candidate(value, _uncertain_category_from_label(label), "wartość po etykiecie biznesowej/technicznej", match.start("value"), match.end("value"), "medium")
        if len(out) >= limit:
            return out[:limit]

    for match in _UNCERTAIN_REVERSE_ADDRESS_RE.finditer(source):
        add_candidate(match.group(0), "ADDRESS", "adres w nietypowym układzie", match.start(), match.end(), "medium")
        if len(out) >= limit:
            return out[:limit]

    for match in _UNCERTAIN_PROJECT_RE.finditer(source):
        add_candidate(match.group(1), "PROJECT", "nazwa projektu/systemu w opisie", match.start(1), match.end(1), "low")
        if len(out) >= limit:
            return out[:limit]

    for match in _UNCERTAIN_COMPANY_PHRASE_RE.finditer(source):
        add_candidate(match.group(1), "CONTRACTOR", "nazwa kontrahenta w zdaniu opisowym", match.start(1), match.end(1), "low")
        if len(out) >= limit:
            return out[:limit]

    return out[:limit]

def collect_ambiguous_person_warnings(replacements: Iterable[Replacement]) -> List[str]:
    """Non-disclosing warnings about person identities sharing surname / first name.

    When two or more distinct people in the same document share a surname (or
    first name), the IdentityLedger refuses to register surname-only (or
    first-name-only) aliases — bare-name mentions are left visible in the
    document and must be reviewed manually. This helper reports such groups
    by count only; it never echoes the actual names.
    """
    surname_to_people: Dict[str, Set[str]] = {}
    first_name_to_people: Dict[str, Set[str]] = {}
    for r in replacements:
        if r.category not in {"PERSON", "PERSON_NLP"}:
            continue
        parts = _person_parts(r.original)
        if not parts:
            continue
        identity = _canonical_person_value(r.original)
        surname_to_people.setdefault(_surname_key(parts[-1]), set()).add(identity)
        first_name_to_people.setdefault(_first_name_key(parts[0]), set()).add(identity)

    warnings: List[str] = []
    ambig_surnames = sum(1 for people in surname_to_people.values() if len(people) > 1)
    ambig_firsts = sum(1 for people in first_name_to_people.values() if len(people) > 1)
    if ambig_surnames:
        warnings.append(
            f"niejednoznaczne nazwiska: {ambig_surnames} grup(y) osób o wspólnym nazwisku — wzmianki samego nazwiska pozostały widoczne i wymagają ręcznej rewizji przed wysłaniem do Claude"
        )
    if ambig_firsts:
        warnings.append(
            f"niejednoznaczne imiona: {ambig_firsts} grup(y) osób o wspólnym imieniu — wzmianki samego imienia pozostały widoczne i wymagają ręcznej rewizji"
        )
    return warnings



def _all_meaningful_tokens_are_upper_stopwords(value: str) -> bool:
    """Return True for runs such as 'AC PPK ... SA' or 'CRM ERP CMS SLA'.

    These are common legal/business abbreviations, not a company/project name.
    This prevents broad regexes from swallowing long acronym lists.
    """
    tokens = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9]+", value or "")
    normalized = [deaccent_role(t) for t in tokens if t]
    if len(normalized) < 2:
        return False
    # Ignore pure legal suffix connector tokens in company forms.
    suffix_noise = {"SP", "Z", "O", "OO", "SA", "S", "A", "P", "K", "C"}
    meaningful = [t for t in normalized if t not in suffix_noise]
    if len(meaningful) < 2:
        return False
    return all(t in LEGAL_AND_UPPER_STOPWORDS_NORM for t in meaningful)

def category_ok(category: str, value: str) -> bool:
    if _is_legal_term(value):
        return False
    if category == "PERSON":
        # Do not treat legal headings / defined terms such as "Ogólne Warunki" or
        # "Kodeks Cywilny" as persons merely because they are title-cased.
        return _looks_like_person_name(value)
    if category == "PERSON_ALIAS":
        cleaned = _clean_alias(value)
        if len(cleaned) < 3 or _is_legal_term(cleaned) or _is_role_alias(cleaned):
            return False
        if deaccent_role(cleaned) in LEGAL_WORD_STOPLIST_NORM:
            return False
        return True
    if category == "COMPANY":
        if PUBLIC_ADMIN_ORG_RE.search(value or ""):
            return False
        if _all_meaningful_tokens_are_upper_stopwords(value):
            return False
    if category == "COMPANY_CODE":
        # Free-standing uppercase tokens create too many false positives in legal
        # headings, e.g. "UMOWA NAJMU LOKALU MIESZKALNEGO". Company codes are
        # still masked when derived from an actual company or a "dalej jako" alias.
        return False
    if category == "COMPANY_CODE_CONTEXT":
        token = _clean_alias(value).upper()
        return bool(re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ]{3,20}", token)) and token not in COMMON_UPPERCASE_STOPWORDS and token not in {"B2B", "B2C", "FIK"}
    if category in {"PERSON_NLP", "COMPANY_NLP", "ADDRESS_NLP"}:
        return len(_clean_alias(value)) >= 3
    if category == "BIELIK_PII":
        cleaned = _clean_alias(value)
        if len(cleaned) < 4 or _is_legal_term(cleaned):
            return False
        return any(ch.isupper() or ch.isdigit() for ch in cleaned) or any(ch in "@./:-" for ch in cleaned)
    if category == "PROJECT":
        cleaned = _clean_alias(value)
        if _is_legal_or_defined_term(cleaned):
            return False
        project_tokens = {deaccent_role(t) for t in re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9]+", cleaned)}
        if project_tokens and project_tokens <= {"SYSTEM", "CRM", "ERP", "SAAS", "CMS", "API", "PANEL"}:
            return False
        if _all_meaningful_tokens_are_upper_stopwords(cleaned):
            return False
        norm = deaccent_role(cleaned)
        # Do not mask generic legal phrases such as "projekt Zlecenia" or
        # "projekt Umowy". They are document artifacts, not client identifiers.
        if re.fullmatch(r"PROJEKT(?:U|EM|OWI|ACH|Y)?\s+(?:ZLECENIA|UMOWY|ANEKSU|DOKUMENTU|RAPORTU|PISMA|ODPOWIEDZI)", norm):
            return False
        words = [deaccent_role(w.strip(".,;:()[]{}")) for w in cleaned.split() if w.strip(".,;:()[]{}")]
        if len(words) >= 2:
            tail = words[1:]
            legal_tail = {deaccent_role(x) for x in LEGAL_WORD_STOPLIST} | {"ANEKSU", "DOKUMENTU", "RAPORTU", "PISMA", "ODPOWIEDZI"}
            if words[0].startswith("PROJEKT") and all(w in legal_tail for w in tail):
                return False
        # Avoid masking generic legal headings or contractual phrases where the
        # keyword is not followed by a true proper project/system name.
        return len(cleaned.split()) >= 2 and cleaned.upper() not in COMMON_UPPERCASE_STOPWORDS
    if category == "PESEL":
        return len(only_digits(value)) == 11
    if category == "NIP":
        return len(only_digits(value)) == 10
    if category == "REGON":
        return len(only_digits(value)) in (9, 14)
    if category == "IBAN":
        # Polish NRB (26 digits, checksum) OR any ISO 13616 foreign IBAN
        # (2-letter country + 2 check digits + mod-97). This is gap D from the
        # 2026-07-01 verification report: foreign IBANs (e.g. German DE...) were
        # previously never masked.
        return _looks_like_bank_account_number(value, require_checksum=True) or valid_iban(value)
    if category == "BANK_ACCOUNT":
        return _looks_like_bank_account_number(value, require_checksum=False)
    if category == "KRS":
        return len(only_digits(value)) == 10
    if category == "PHONE":
        d = only_digits(value)
        if d.startswith("48"):
            d = d[2:]
        return len(d) == 9
    if category == "IDCARD_PL":
        # Format check + Polish ID checksum (weights [7,3,1] groups, position 4 is the control digit).
        # Without checksum, random AAA000000-style sequences in test contracts would be misclassified.
        return valid_idcard_pl(value)
    if category == "IDCARD_PL_CONTEXT":
        return bool(re.fullmatch(r"[A-Z]{3}\s?\d{6}", _clean_alias(value)))
    if category == "PASSPORT_PL":
        # Format check + Polish passport checksum.
        return valid_passport_pl(value)
    if category == "PASSPORT_CONTEXT":
        return bool(re.fullmatch(r"[A-Z0-9]{1,3}\s?[A-Z0-9]{6,9}", _clean_alias(value)))
    if category == "BDO":
        return len(only_digits(value)) == 9
    if category == "CEIDG_ID":
        return bool(re.fullmatch(r"(?i)[A-Z0-9][A-Z0-9./_\-]{5,80}", _clean_alias(value)))
    if category == "CASE_REF":
        v = _clean_alias(value)
        return len(v) >= 3 and bool(re.search(r"\d", v)) and not re.fullmatch(r"\d+[./-]?\d*", v)
    if category == "IP_ADDRESS":
        parts = (value or "").split(".")
        return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    if category == "DOMAIN":
        v = _clean_alias(value).lower()
        return "." in v
    if category == "LOGIN":
        v = _clean_alias(value)
        return len(v) >= 3 and not _is_legal_term(v)
    if category == "ACCOUNT_ID":
        return len(_clean_alias(value)) >= 4
    if category == "REPOSITORY":
        v = _clean_alias(value)
        return "/" in v and len(v) >= 5
    if category == "FINANCIAL_DOC_ID":
        v = _clean_alias(value)
        return len(v) >= 4 and bool(re.search(r"\d", v))
    if category == "PROJECT_ID":
        v = _clean_alias(value)
        # Contract numbers such as NOVUS/OMNITEX/B2B/05/2026/FIK encode party
        # codes. Existing logic masks NOVUS/OMNITEX while intentionally keeping
        # neutral B2B/date/FIK segments visible. Do not replace the whole value.
        if "/" in v and re.search(r"(?i)/(?:B2B|B2C|FIK)(?:/|$)", v):
            return False
        return len(v) >= 3
    if category in {"PERMIT_ID", "VEHICLE_ID", "RESIDENCE_CARD", "DRIVING_LICENSE", "PROF_LICENSE", "PROPERTY_ID", "PROPERTY_UNIT_ID", "EDELIVERY_ID", "POLICY_CLAIM_ID", "SHIPMENT_ID", "VAT_ID", "MEDICAL_RECORD_ID", "EMPLOYEE_ID", "CUSTOMER_ID", "BUSINESS_ID"}:
        return len(_clean_alias(value)) >= 3
    return True


PRIORITY = {
    "SECRET": 110, "EMAIL": 105, "URL": 100, "IP_ADDRESS": 99, "DOMAIN": 98, "DOMAIN_ALIAS": 97,
    "IBAN": 96, "BANK_ACCOUNT": 95, "IDCARD_PL_CONTEXT": 93, "IDCARD_PL": 92, "PASSPORT_PL": 91, "PESEL": 90,
    "BUSINESS_ID": 89, "BDO": 88, "VAT_ID": 87, "KRS": 86, "NIP": 85, "REGON": 80, "CEIDG_ID": 78, "BIRTH_DATA": 73,
    "LAND_REGISTER": 72, "KW": 72, "REPERTORIUM": 71, "CASE_REF": 70, "PERMIT_ID": 69, "DECYZJA_ADM": 68, "SYGNATURA": 65,
    "VEHICLE_ID": 64, "PASSPORT_CONTEXT": 63, "RESIDENCE_CARD": 62, "DRIVING_LICENSE": 62, "PROF_LICENSE": 61,
    "PROPERTY_ID": 60, "PROPERTY_UNIT_ID": 60, "EDELIVERY_ID": 60, "POLICY_CLAIM_ID": 59, "SHIPMENT_ID": 58, "PROJECT_ID": 57, "ACCOUNT_ID": 57, "LOGIN": 57, "REPOSITORY": 57, "FINANCIAL_DOC_ID": 57, "MEDICAL_RECORD_ID": 57, "EMPLOYEE_ID": 57, "CUSTOMER_ID": 57,
    "PHONE": 56, "COURT": 50, "COURT_ALIAS": 49, "ADDRESS_FULL": 55, "ADDRESS_RURAL": 54, "ADDRESS_SIEDZIBA": 53, "COMPANY": 48, "CONTRACTOR": 47, "PROJECT": 46,
    "COMPANY_CODE_CONTEXT": 46, "COMPANY_CODE": 45, "COMPANY_ALIAS": 44, "CONTRACTOR_ALIAS": 43,
    "PROJECT_ALIAS": 42, "ALIAS": 41, "ADDRESS": 40, "POSTCODE_PL": 39,
    "PERSON_NLP": 39, "PERSON": 38, "PERSON_ALIAS": 37, "COMPANY_NLP": 49, "ADDRESS_NLP": 41,
    "BIELIK_PII": 36,
    # Manual "always" rules without an entity category. Tie-break only: a manual
    # finding at the same start/length as an automatic one wins the overlap.
    "MANUAL": 58,
}


_PL_PLACEHOLDER_FAMILY = {
    "PERSON": "OSOBA",
    "PERSON_NLP": "OSOBA",
    "COMPANY": "FIRMA",
    "COMPANY_NLP": "FIRMA",
    "CONTRACTOR": "FIRMA",
    "COMPANY_CODE": "FIRMA",
    "COMPANY_CODE_CONTEXT": "FIRMA",
    "ADDRESS": "ADRES",
    "ADDRESS_FULL": "ADRES",
    "ADDRESS_RURAL": "ADRES",
    "ADDRESS_NLP": "ADRES",
    "ADDRESS_SIEDZIBA": "SIEDZIBA",
    "POSTCODE_PL": "KOD_POCZTOWY",
    "BANK_ACCOUNT": "RACHUNEK_BANKOWY",
    "IBAN": "RACHUNEK_BANKOWY",
    "COURT": "SAD",
    "SYGNATURA": "SYGNATURA",
    "CASE_REF": "SPRAWA",
    "IDCARD_PL": "DOWOD_OSOBISTY",
    "IDCARD_PL_CONTEXT": "DOWOD_OSOBISTY",
    "PASSPORT_PL": "PASZPORT",
    "PASSPORT_CONTEXT": "PASZPORT",
    "PASSPORT": "PASZPORT",
    "PHONE": "TELEFON",
    "DOMAIN": "DOMENA",
    "IP_ADDRESS": "IP",
    "SECRET": "SEKRET",
    "BIRTH_DATA": "DATA_URODZENIA",
    "VEHICLE_ID": "NR_REJESTRACYJNY",
    "LAND_REGISTER": "KSIEGA_WIECZYSTA",
    "KW": "KSIEGA_WIECZYSTA",
    "PROPERTY_ID": "NR_DZIALKI",
    "PROPERTY_UNIT_ID": "NR_LOKALU",
    "PERMIT_ID": "NR_ZEZWOLENIA",
    "RESIDENCE_CARD": "KARTA_POBYTU",
    "DRIVING_LICENSE": "PRAWO_JAZDY",
    "PROF_LICENSE": "UPRAWNIENIA_ZAWODOWE",
    "EDELIVERY_ID": "NR_EDORECZENIA",
    "POLICY_CLAIM_ID": "NR_POLISY",
    "SHIPMENT_ID": "NR_PRZESYLKI",
    "PROJECT_ID": "NR_PROJEKTU",
    "ACCOUNT_ID": "NR_KONTA",
    "REPOSITORY": "REPOZYTORIUM",
    "FINANCIAL_DOC_ID": "DOKUMENT_FINANSOWY",
    "MEDICAL_RECORD_ID": "DOKUMENTACJA_MEDYCZNA",
    "EMPLOYEE_ID": "NR_PRACOWNIKA",
    "CUSTOMER_ID": "NR_KLIENTA",
    "BUSINESS_ID": "ID_BIZNESOWY",
    "VAT_ID": "NR_VAT_UE",
    "CEIDG_ID": "NR_CEIDG",
    "PROJECT": "PROJEKT",
    # Kategorie zachowane bez zmian — już polskie/uniwersalne skróty:
    # PESEL, NIP, KRS, REGON, BDO, EMAIL, URL, LOGIN, DECYZJA_ADM, REPERTORIUM, ALIAS, BIELIK_PII
}


def _pl_placeholder_family(category: str) -> str:
    """Translate an internal (English) detector category into the Polish
    ASCII token used in the placeholder text shown in the document.
    Falls back to the original category unchanged if not mapped, so an
    unmapped/future category never crashes placeholder generation."""
    return _PL_PLACEHOLDER_FAMILY.get(category, category)


def _trim_leading_person_from_company(value: str, absolute_start: int) -> tuple[str, int]:
    """Avoid COMPANY regex swallowing words before the actual party name.

    Examples:
    - 'Jan Kowalski ABC sp. z o.o.' -> 'ABC sp. z o.o.'
    - 'Umowa FENIX sp. z o.o.' -> 'FENIX sp. z o.o.'
    - 'Klient FENIX sp. z o.o.' -> 'FENIX sp. z o.o.'

    This is intentionally conservative: it only trims when the remaining tail
    still contains a legal suffix/prefix and therefore remains a company.
    """
    original = value
    cleaned = value.strip()

    def valid_tail(tail: str) -> bool:
        return bool(re.search(rf"(?i)(?:{COMPANY_SUFFIX}|{ORG_PREFIX})", tail))

    # Trim a leading natural-person name accidentally swallowed before company.
    # Only trim when the leading two-word token is actually a recognised person name
    # (i.e. the first word is a known given name). This prevents stripping brand-name
    # prefixes like "Meble New" from "Meble New Concept Sp. z o.o.".
    m = re.match(rf"^({POLISH_CAP}\s+{POLISH_CAP}(?:-{POLISH_CAP})?)\s+(.+?(?i:(?:{COMPANY_SUFFIX}))(?:\b|$).*)$", cleaned)
    if m and valid_tail(m.group(2).strip()) and _looks_like_person_name(m.group(1)):
        rest = m.group(2).strip()
        offset = original.find(rest)
        return rest, absolute_start + max(0, offset)

    # Trim document/role descriptors before company name, e.g. 'Umowa FENIX sp. z o.o.'.
    tokens = cleaned.split()
    drop = 0
    leading_company_noise_norm = frozenset(deaccent_role(x) for x in LEADING_COMPANY_NOISE_WORDS)
    for tok in tokens[:-1]:
        norm = deaccent_role(tok.strip('.,;:()[]{}„”"\''))
        if norm in leading_company_noise_norm or norm in LEGAL_WORD_STOPLIST_NORM:
            drop += 1
            continue
        break
    if drop:
        rest = ' '.join(tokens[drop:]).strip()
        if valid_tail(rest):
            offset = original.find(rest)
            return rest, absolute_start + max(0, offset)

    return value, absolute_start



def _contextual_numeric_identifier_category(category: str, text: str, start: int, value: str = "") -> str:
    """Avoid classifying ordinary pleading exhibit numbers as NIP.

    A bare 10-digit value can be a NIP, but in litigation pleadings it can also
    be an invoice/order number. If the local context says "faktura ... numer" or
    "zlecenie numer" and does not say NIP, preserve the label and mask the value
    as a document/order identifier instead of [NIP_n].

    For PESEL the same context window resolves the opposite ambiguity: an
    11-digit number is a PESEL when its checksum is valid or when the preceding
    text labels it as PESEL (documents with typos must still be masked). A bare
    11-digit value that fails both checks is an order/reference number, not a
    PESEL — return "" so the caller drops the finding.
    """
    if category == "PESEL":
        if valid_pesel(value):
            return category
        before = (text[max(0, start - 90):start] or "").lower()
        if "pesel" in before[-55:]:
            return category
        return ""
    if category != "NIP":
        return category
    before = (text[max(0, start - 90):start] or "").lower()
    near = before[-55:]
    if "nip" in near:
        return category
    if re.search(r"(?:faktura|proforma|nota\s+księgowa|nota\s+ksiegowa)[^\n]{0,45}(?:nr\.?|numer)?\s*[:\-–— ]*$", before):
        return "FINANCIAL_DOC_ID"
    if re.search(r"(?:zlecenie|zamówienie|zamowienie|zgłoszenie|zgloszenie)[^\n]{0,45}(?:nr\.?|numer)?\s*[:\-–— ]*$", before):
        return "PROJECT_ID"
    return category

class RegexDetector:
    """Small scrubadub-inspired detector wrapper around one compiled pattern.

    The engine keeps detectors explicit and composable instead of hiding all
    logic in one procedural regex loop. This makes it easier to add Presidio-like
    recognizers later without changing the Word integration layer.
    """
    def __init__(self, category: str, pattern: re.Pattern):
        self.category = category
        self.pattern = pattern

    def find(self, text: str) -> List[Finding]:
        results: List[Finding] = []
        for m in self.pattern.finditer(text):
            category = self.category
            if "id" in m.groupdict() and m.group("id"):
                raw_value = m.group("id")
                start = m.start("id")
            else:
                raw_value = m.group(0)
                start = m.start()
            value = raw_value.strip()
            if category == "COMPANY":
                value, start = _trim_leading_person_from_company(value, start + (len(raw_value) - len(raw_value.lstrip())))
            elif category == "URL":
                value, start = _trim_trailing_url_punctuation(value, start + (len(raw_value) - len(raw_value.lstrip())))
            elif category == "PERSON":
                value, start = _strip_leading_person_context_words(value, start + (len(raw_value) - len(raw_value.lstrip())))
            elif category == "KRS":
                digit_match = re.search(r"\d{10}", raw_value)
                if digit_match:
                    value = digit_match.group(0)
                    start = m.start() + digit_match.start()
                else:
                    start = start + (len(raw_value) - len(raw_value.lstrip()))
            else:
                start = start + (len(raw_value) - len(raw_value.lstrip()))
            category = _contextual_numeric_identifier_category(category, text, start, value)
            if not category or not value or not category_ok(category, value):
                continue
            results.append(Finding(category, value, start, start + len(value)))
        return results


REGEX_DETECTORS: List[RegexDetector] = [RegexDetector(category, pattern) for category, pattern in PATTERNS.items()]


# ---------- Optional local NLP layer ----------
# This detector is intentionally optional. The default installation remains light
# and deterministic, but if spaCy with a Polish model is installed locally, the
# engine can add NER-based PERSON/COMPANY/ADDRESS candidates. No data leaves the
# user's computer.
_SPACY_NLP = None
_SPACY_ATTEMPTED = False


def _spacy_enabled() -> bool:
    return os.environ.get("CSMW_ENABLE_SPACY", "0").strip().lower() in {"1", "true", "yes", "on"}


def _load_spacy_model():
    global _SPACY_NLP, _SPACY_ATTEMPTED
    if _SPACY_ATTEMPTED:
        return _SPACY_NLP
    _SPACY_ATTEMPTED = True
    if not _spacy_enabled():
        return None
    try:
        import spacy  # type: ignore
        for model in ("pl_core_news_lg", "pl_core_news_md", "pl_core_news_sm"):
            try:
                _SPACY_NLP = spacy.load(model)
                return _SPACY_NLP
            except Exception:
                continue
    except Exception:
        return None
    return None


def collect_nlp_findings(text: str) -> List[Finding]:
    nlp = _load_spacy_model()
    if nlp is None:
        return []
    findings: List[Finding] = []
    try:
        doc = nlp(text)
    except Exception:
        return []
    for ent in getattr(doc, "ents", []):
        label = str(getattr(ent, "label_", "") or "").lower()
        value = str(getattr(ent, "text", "") or "").strip()
        if not value or len(value) < 3:
            continue
        if label in {"persname", "person", "per"}:
            findings.append(Finding("PERSON_NLP", value, int(ent.start_char), int(ent.end_char)))
        elif label in {"orgname", "org", "organisation", "organization"}:
            findings.append(Finding("COMPANY_NLP", value, int(ent.start_char), int(ent.end_char)))
        elif label in {"placename", "geogname", "loc", "gpe"}:
            findings.append(Finding("ADDRESS_NLP", value, int(ent.start_char), int(ent.end_char)))
    return findings


def collect_base_findings(text: str) -> List[Finding]:
    findings: List[Finding] = []
    for detector in REGEX_DETECTORS:
        findings.extend(detector.find(text))
    findings.extend(collect_overlapping_person_findings(text))
    return findings


def collect_overlapping_person_findings(text: str) -> List[Finding]:
    results: List[Finding] = []
    for m in PERSON_OVERLAP_PATTERN.finditer(text or ""):
        raw_value = (m.group(1) or "")
        raw_start = m.start(1) + (len(raw_value) - len(raw_value.lstrip()))
        value, start = _strip_leading_person_context_words(raw_value, raw_start)
        if not value or not category_ok("PERSON", value):
            continue
        results.append(Finding("PERSON", value, start, start + len(value)))
    return results


def _canonical_entity_category(category: str) -> str:
    if category in {"COMPANY", "COMPANY_NLP", "COMPANY_ALIAS", "COMPANY_CODE", "COMPANY_CODE_CONTEXT", "CONTRACTOR", "CONTRACTOR_ALIAS", "ALIAS"}:
        return "COMPANY"
    if category == "IDCARD_PL_CONTEXT":
        return "IDCARD_PL"
    if category == "KW":
        return "LAND_REGISTER"
    if category == "PASSPORT_CONTEXT":
        return "PASSPORT"
    if category in {"PERSON", "PERSON_NLP", "PERSON_ALIAS"}:
        return "PERSON"
    if category in {"DOMAIN", "DOMAIN_ALIAS", "URL"}:
        return "DOMAIN"
    if category in {"PROJECT", "PROJECT_ALIAS"}:
        return "PROJECT"
    if category == "COURT_ALIAS":
        return "COURT"
    return category


@lru_cache(maxsize=65536)
def _canonical_company_value(value: str) -> str:
    cleaned = _clean_alias(TRAILING_CONTEXT_RE.sub("", value))
    cleaned = _clean_alias(LEGAL_SUFFIX_RE.sub("", cleaned))
    cleaned = _clean_alias(ORG_PREFIX_RE.sub("", cleaned))
    return cleaned.casefold() or _clean_alias(value).casefold()


@lru_cache(maxsize=65536)
def _canonical_person_value(value: str) -> str:
    """Identity key for a person mention.

    Returns "<first_key>|<surname_key>" for full-name mentions so that two
    distinct people sharing a surname (e.g. "Jan Kowalski" and "Anna
    Kowalski") get separate identities. Single-token mentions (bare
    surname / first name) fall back to the surname key only — the
    IdentityLedger decides whether such a fragment should be linked to a
    full-name canonical based on per-document ambiguity analysis.
    """
    cleaned = _clean_alias(re.sub(r"(?i)^(Pan|Pani|Mec\.|radca prawny|adw\.|adwokat|pełnomocnik|pelnomocnik|prokurent)\s+", "", value))
    parts = cleaned.split()
    if not parts:
        return cleaned.casefold()
    if len(parts) >= 2:
        first_key = _first_name_key(parts[0])
        surname_key = _surname_key(parts[-1])
        return f"{first_key}|{surname_key}".casefold()
    return _surname_key(parts[0]).casefold()


@lru_cache(maxsize=65536)
def _canonical_domain_value(value: str) -> str:
    v = value.strip().lower()
    v = re.sub(r"(?i)^https?://", "", v).split("/")[0]
    if "@" in v:
        v = v.rsplit("@", 1)[-1]
    if v.startswith("www."):
        v = v[4:]
    return v.strip(".,;:)")


class IdentityLedger:
    """pii-anon-inspired identity ledger.

    It clusters full names, aliases, domains and inflected forms into stable
    placeholder families so related mentions are less likely to receive random
    placeholder IDs.
    """
    def __init__(self, findings: Iterable[Finding]):
        self.findings = list(findings)
        self.alias_to_key: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._build()

    def _add_alias(self, category: str, alias: str, canonical: Tuple[str, str]) -> None:
        cleaned = _clean_alias(alias)
        if not cleaned:
            return
        key = (_canonical_entity_category(category), cleaned.casefold())
        existing = self.alias_to_key.get(key)
        if existing and existing != canonical:
            # Keep the first stable alias mapping from the document. Later
            # mentions in comments/metadata can be close to a different party and
            # would otherwise remap short codes such as "ZXCV" incorrectly.
            return
        self.alias_to_key[key] = canonical

    def _nearest_company_canonical(self, finding: Finding) -> Tuple[str, str] | None:
        preceding = [
            f for f in self.findings
            if f.end <= finding.start
            and finding.start - f.end <= 300
            and _canonical_entity_category(f.category) == "COMPANY"
            and f.category not in {"ALIAS", "COMPANY_ALIAS", "COMPANY_CODE"}
        ]
        if not preceding:
            return None
        nearest = max(preceding, key=lambda item: item.end)
        return ("COMPANY", _canonical_company_value(nearest.value))

    def _build(self) -> None:
        # First pass: collect per-document person ambiguity so that bare
        # surname / first-name aliases are only registered when they
        # uniquely point at one detected person.
        first_name_to_people: Dict[str, Set[str]] = {}
        surname_to_people: Dict[str, Set[str]] = {}
        for f in self.findings:
            if _canonical_entity_category(f.category) != "PERSON":
                continue
            if f.category == "PERSON_ALIAS":
                continue
            parts = _person_parts(f.value)
            if not parts:
                continue
            identity = _canonical_person_value(f.value)
            first_name_to_people.setdefault(_first_name_key(parts[0]), set()).add(identity)
            surname_to_people.setdefault(_surname_key(parts[-1]), set()).add(identity)

        for f in self.findings:
            cat = _canonical_entity_category(f.category)
            if cat == "COMPANY":
                if f.category in {"ALIAS", "COMPANY_ALIAS"}:
                    canonical = self._nearest_company_canonical(f) or ("COMPANY", _canonical_company_value(f.value))
                else:
                    canonical = ("COMPANY", _canonical_company_value(f.value))
                self._add_alias(f.category, f.value, canonical)
                for alias in _company_aliases(f.value):
                    self._add_alias(f.category, alias, canonical)
            elif cat == "PERSON":
                # PERSON_ALIAS findings are generated from full PERSON findings and
                # should not overwrite the alias mapping with their own short value.
                if f.category == "PERSON_ALIAS":
                    continue
                canonical = ("PERSON", _canonical_person_value(f.value))
                self._add_alias(f.category, f.value, canonical)
                parts = _person_parts(f.value)
                include_first = True
                include_surname = True
                if parts:
                    include_first = len(first_name_to_people.get(_first_name_key(parts[0]), set())) == 1
                    include_surname = len(surname_to_people.get(_surname_key(parts[-1]), set())) == 1
                for alias in _person_aliases(f.value, include_first=include_first, include_surname=include_surname):
                    self._add_alias(f.category, alias, canonical)
            elif cat == "DOMAIN":
                canonical = ("DOMAIN", _canonical_domain_value(f.value))
                self._add_alias(f.category, f.value, canonical)
                for alias in _domain_variants(_canonical_domain_value(f.value)):
                    self._add_alias(f.category, alias, canonical)
            elif cat == "PROJECT":
                canonical = ("PROJECT", _clean_alias(f.value).casefold())
                self._add_alias(f.category, f.value, canonical)
            elif cat == "COURT":
                canonical = ("COURT", _canonical_court_value(f.value))
                self._add_alias(f.category, f.value, canonical)
                for alias in _court_aliases(f.value):
                    self._add_alias(f.category, alias, canonical)

    def key_for(self, finding: Finding) -> Tuple[str, str]:
        cat = _canonical_entity_category(finding.category)
        lookup = (cat, _clean_alias(finding.value).casefold())
        if lookup in self.alias_to_key:
            return self.alias_to_key[lookup]
        if cat == "COMPANY":
            return ("COMPANY", _canonical_company_value(finding.value))
        if cat == "PERSON":
            return ("PERSON", _canonical_person_value(finding.value))
        if cat == "DOMAIN":
            return ("DOMAIN", _canonical_domain_value(finding.value))
        if cat == "PROJECT":
            return ("PROJECT", _clean_alias(finding.value).casefold())
        if cat == "COURT":
            return ("COURT", _canonical_court_value(finding.value))
        return (cat, finding.value)

    def export_summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.findings:
            category = _canonical_entity_category(f.category)
            counts[category] = counts.get(category, 0) + 1
        return counts




# ---------- user controls ----------
# Lightweight local controls for "review before sending to AI". These controls
# are intentionally rule-based and deterministic: users can force specific
# strings to be anonymized, exclude false positives, and override categories.
# They are applied only inside the local CSM process and are saved with session
# artifacts, never sent to Claude.

def _control_items(controls, key: str):
    if not controls:
        return []
    if isinstance(controls, dict):
        value = controls.get(key, [])
    else:
        value = getattr(controls, key, [])
    return value if isinstance(value, list) else []


def _control_text(value) -> str:
    if isinstance(value, dict):
        raw = value.get('value') or value.get('text') or value.get('original') or ''
    else:
        raw = value
    return _clean_alias(str(raw or ''))


def _control_category(value, default: str = 'MANUAL') -> str:
    if isinstance(value, dict):
        raw = value.get('category') or default
    else:
        raw = default
    cat = re.sub(r'[^A-Z0-9_]', '_', str(raw or default).upper()).strip('_') or default
    return cat[:40]


def _literal_spans(text: str, needle: str):
    if not text or not needle:
        return []
    spans = []
    start = 0
    hay = text.casefold()
    ndl = needle.casefold()
    while True:
        idx = hay.find(ndl, start)
        if idx < 0:
            break
        spans.append((idx, idx + len(needle)))
        start = idx + max(1, len(needle))
    return spans


def _overlaps_any(start: int, end: int, spans) -> bool:
    return any(not (end <= s or start >= e) for s, e in spans)


def _control_force(value) -> bool:
    if isinstance(value, dict):
        return bool(value.get('force') or value.get('confirmed'))
    return False


# Rule categories a user may type (Polish or English) that map onto canonical
# engine entity categories. A manual rule with one of these categories inherits
# the engine's inflection variants and identity-ledger clustering, so the same
# person/company gets one placeholder family instead of a separate [MANUAL_n].
_CONTROL_ENGINE_CATEGORY = {
    'OSOBA': 'PERSON', 'PERSON': 'PERSON',
    'FIRMA': 'COMPANY', 'COMPANY': 'COMPANY', 'KONTRAHENT': 'COMPANY', 'CONTRACTOR': 'COMPANY',
    'SAD': 'COURT', 'COURT': 'COURT',
    'PROJEKT': 'PROJECT', 'PROJECT': 'PROJECT',
    'DOMENA': 'DOMAIN', 'DOMAIN': 'DOMAIN',
    'ADRES': 'ADDRESS', 'ADDRESS': 'ADDRESS',
}

# Findings validated by checksum or document structure. A "never" rule must be
# explicitly confirmed (force=true on the rule) to suppress these; otherwise a
# short phrase could silently expose e.g. a valid PESEL that it happens to cover.
_CONTROL_HARD_CATEGORIES = frozenset({
    'PESEL', 'NIP', 'REGON', 'IBAN', 'BANK_ACCOUNT',
    'IDCARD_PL', 'IDCARD_PL_CONTEXT', 'PASSPORT_PL', 'PASSPORT_CONTEXT',
})


def _control_boundary_spans(text: str, needle: str) -> List[Tuple[int, int]]:
    """Word-boundary, case-insensitive occurrences of a manual-rule phrase.

    Manual rules used raw substring matching before v1.6, which masked word
    fragments ("Ala" inside "otrzymała") and let a short "never" phrase
    suppress detections it merely touched. Boundary matching mirrors the
    alias engine (_literal_boundary_pattern).
    """
    cleaned = _clean_alias(needle)
    if not cleaned or not text:
        return []
    pattern = re.compile(
        rf"(?<![\w{LATIN_LETTERS}]){re.escape(cleaned)}(?![\w{LATIN_LETTERS}])",
        re.IGNORECASE,
    )
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def _control_always_variants(value: str, engine_category: str | None) -> Set[str]:
    """Inflected/alias variants for an "always" rule with an entity category."""
    variants = {value}
    if engine_category == 'PERSON':
        variants |= _person_aliases(value, include_first=False, include_surname=True)
    elif engine_category == 'COMPANY':
        variants |= _company_aliases(value)
    elif engine_category == 'COURT':
        variants |= _court_aliases(value)
    return {v for v in (_clean_alias(x) for x in variants) if v}


def _control_never_variants(value: str) -> Set[str]:
    """Conservative variants for a "never" rule.

    Only same-token-count inflections of a capitalised multi-word phrase (a
    person-like name) are added. Shorter aliases (bare surname, company base
    name) are intentionally excluded: a "never" rule must not silently expand
    to other mentions the user did not type.
    """
    variants = {value}
    parts = value.split()
    if len(parts) >= 2 and all(p[:1].isupper() for p in parts if p):
        for v in _person_aliases(value, include_first=False, include_surname=False):
            if len(v.split()) == len(parts):
                variants.add(v)
    return {v for v in (_clean_alias(x) for x in variants) if v}


def _control_context_snippet(text: str, start: int, end: int, radius: int = 30) -> str:
    snippet = text[max(0, start - radius):min(len(text), end + radius)]
    # DOCX part separators (private-use plane) and control chars would leak into
    # the panel display; collapse them to plain spaces.
    snippet = ''.join(' ' if (ord(ch) >= 0xE000 and ord(ch) <= 0xF8FF) or unicodedata.category(ch).startswith('C') else ch for ch in snippet)
    return ' '.join(snippet.split())


def collect_findings_with_controls_report(text: str, controls=None) -> Tuple[List[Finding], Dict[str, Any]]:
    """Apply user controls on top of automatic findings and report per-rule effects.

    The report is local-only (shown in the CSM panel and written to the session
    folder). Context snippets contain fragments of the source document, the same
    data the local map preview already exposes; they must not leave the machine.
    """
    text = text or ''
    findings = collect_findings(text)

    never_rules: List[Dict[str, Any]] = []
    for item in _control_items(controls, 'never') + _control_items(controls, 'never_anonymize'):
        value = _control_text(item)
        if not value:
            continue
        variants = _control_never_variants(value)
        spans: List[Tuple[int, int]] = []
        for variant in variants:
            spans.extend(_control_boundary_spans(text, variant))
        never_rules.append({
            'value': value,
            'force': _control_force(item),
            'variants': {v.casefold() for v in variants},
            'spans': spans,
            'suppressed': 0,
            'blocked_hard': {},
            'examples': [],
        })

    def matching_never_rule(f: Finding):
        fv = _clean_alias(f.value).casefold()
        for rule in never_rules:
            if fv in rule['variants']:
                return rule
            for s, e in rule['spans']:
                # Full cover only: touching a detection is not enough to unmask it.
                if s <= f.start and e >= f.end:
                    return rule
        return None

    if never_rules:
        kept: List[Finding] = []
        for f in findings:
            rule = matching_never_rule(f)
            if rule is None:
                kept.append(f)
                continue
            if f.category in _CONTROL_HARD_CATEGORIES and not rule['force']:
                rule['blocked_hard'][f.category] = rule['blocked_hard'].get(f.category, 0) + 1
                kept.append(f)
                continue
            rule['suppressed'] += 1
            if len(rule['examples']) < 5:
                rule['examples'].append({'category': f.category, 'context': _control_context_snippet(text, f.start, f.end)})
        findings = kept

    never_spans = [span for rule in never_rules for span in rule['spans']]

    always_rules: List[Dict[str, Any]] = []
    for item in _control_items(controls, 'always') + _control_items(controls, 'always_anonymize'):
        value = _control_text(item)
        if not value:
            continue
        raw_category = _control_category(item, 'MANUAL')
        engine_category = _CONTROL_ENGINE_CATEGORY.get(raw_category)
        rule = {
            'value': value,
            'category': raw_category,
            'engine_category': engine_category or raw_category,
            'matches': 0,
            'variant_matches': 0,
            'examples': [],
        }
        base_casefold = _clean_alias(value).casefold()
        for variant in sorted(_control_always_variants(value, engine_category), key=len, reverse=True):
            for start, end in _control_boundary_spans(text, variant):
                if never_spans and _overlaps_any(start, end, never_spans):
                    continue
                findings.append(Finding(engine_category or raw_category, text[start:end], start, end))
                if variant.casefold() == base_casefold:
                    rule['matches'] += 1
                else:
                    rule['variant_matches'] += 1
                if len(rule['examples']) < 3:
                    rule['examples'].append({'context': _control_context_snippet(text, start, end)})
        always_rules.append(rule)

    overrides = {}
    if isinstance(controls, dict) and isinstance(controls.get('category_overrides'), dict):
        overrides = {str(k).casefold(): _control_category({'category': v}, 'MANUAL') for k, v in controls.get('category_overrides', {}).items()}
    elif isinstance(controls, dict):
        pairs = controls.get('category_changes') or []
        if isinstance(pairs, list):
            for item in pairs:
                if isinstance(item, dict):
                    key = _control_text(item)
                    cat = _control_category(item, 'MANUAL')
                    if key:
                        overrides[key.casefold()] = cat
    if overrides:
        changed=[]
        for f in findings:
            cat = overrides.get(_clean_alias(f.value).casefold())
            changed.append(Finding(cat or f.category, f.value, f.start, f.end))
        findings = changed

    warnings: List[str] = []
    for rule in never_rules:
        if rule['blocked_hard']:
            cats = ', '.join(sorted(rule['blocked_hard']))
            warnings.append(
                f"Reguła „nie ukrywaj: {rule['value']}” objęłaby wykrycia zweryfikowane sumą kontrolną ({cats}). "
                "CSM pozostawił je ukryte. Aby je odsłonić, potwierdź regułę jako wymuszoną w panelu."
            )
        if rule['value'].isdigit() and len(rule['value']) < 6:
            warnings.append(
                f"Reguła „nie ukrywaj: {rule['value']}” to krótki numer — sprawdź w podglądzie reguł, co dokładnie wyłącza."
            )

    dead_rules = [r['value'] for r in always_rules if not r['matches'] and not r['variant_matches']]
    dead_rules += [r['value'] for r in never_rules if not r['suppressed'] and not r['blocked_hard']]

    report: Dict[str, Any] = {
        'always': always_rules,
        'never': [{k: v for k, v in r.items() if k not in {'spans', 'variants'}} for r in never_rules],
        'dead_rules': dead_rules,
        'warnings': warnings,
    }
    return remove_overlaps(findings), report


def collect_findings_with_controls(text: str, controls=None) -> List[Finding]:
    findings, _ = collect_findings_with_controls_report(text, controls)
    return findings


# Matches an opening quote char immediately before a [PLACEHOLDER] token.
# Used to clean up orphaned quotes left when a COMPANY regex match consumed
# the closing quote but not the corresponding opening quote.
# Character class covers: ASCII ", ASCII ', „ (U+201E), " (U+201C), « (U+00AB), ‹ (U+2039)
_ORPHAN_OPENING_QUOTE_RE = re.compile(
    "[\"’„“«‹']" + r"(\[[A-Z][A-Z0-9_]{1,40}\])"
)


def make_replacements_with_controls(text: str, controls=None) -> Tuple[str, List[Replacement]]:
    findings = collect_findings_with_controls(text, controls)
    seen, counts = build_replacement_plan(findings, _existing_placeholders(text))

    # Replace only accepted finding spans, not every literal occurrence of the
    # same string in the whole document. This matters in Polish legal documents
    # where a surname can also be an ordinary word or a place name (e.g. Mucha,
    # Pustynia). Global str.replace() would over-mask unrelated prose once a
    # single contextual occurrence was detected. Literal alias detectors already
    # add intended repeated occurrences as findings, so span replacement keeps
    # recall while reducing false positives.
    # Build the masked string in one forward pass. Repeated slicing of the full
    # document is O(k*n) and was a major cost on long contracts with many parties,
    # identifiers and addresses. Findings are already non-overlapping.
    pieces: List[str] = []
    cursor = 0
    for f in sorted(findings, key=lambda item: item.start):
        placeholder = seen.get((f.category, f.value))
        if not placeholder:
            continue
        if text[f.start:f.end] != f.value:
            # Defensive fallback for rare whitespace normalization differences.
            # Do not perform a global replacement here; skip rather than risk
            # changing unrelated content.
            continue
        pieces.append(text[cursor:f.start])
        pieces.append(placeholder)
        cursor = f.end
    pieces.append(text[cursor:])
    return "".join(pieces), replacements_from_plan(seen, counts)


# ── Gazetteer-based person detection ─────────────────────────────────────────
# Uses PESEL registry first names / surnames (CC0, dane.gov.pl) to confirm
# two-token sequences as person names even without surrounding legal context
# (e.g. in signatory lists, table cells, contract party declarations).
# Also handles the most common Polish case inflections so that genitive/dative
# forms like "Jana Kowalskiego" are caught alongside nominative "Jan Kowalski".

# Normalization rules: (suffix_to_strip, replacement)
# Applied longest-first; result checked against gazetteer.
_NAME_NORM_RULES: List[Tuple[str, str]] = [
    # -ski/-cki family (most common Polish surnames)
    ("skiego", "ski"),    # Kowalskiego → Kowalski
    ("ckiego", "cki"),    # Nowickiego  → Nowicki
    ("skiemu", "ski"),    # Kowalskiemu → Kowalski
    ("ckiemu", "cki"),
    ("skim",   "ski"),    # Kowalskim   → Kowalski
    ("ckim",   "cki"),
    ("skiej",  "ska"),    # Kowalskiej  → Kowalska
    ("ckiej",  "cka"),
    ("ską",    "ska"),    # Kowalską    → Kowalska
    ("cką",    "cka"),
    # Dative -owi (very common)
    ("owi",    ""),       # Janowi / Nowakowi → Jan / Nowak
    # Feminine genitive/instrumental
    ("ny",     "na"),     # Anny → Anna
    ("ry",     "ra"),     # Barbary → Barbara
    ("ty",     "ta"),     # Doroty → Dorota
    ("ę",      "a"),      # Annę / Marię → Anna / Maria
    ("ą",      "a"),      # Anną / Kowalską (already covered above) → Anna
    ("nie",    "na"),     # Annie → Anna
    # Simple genitive masculine: strip -a
    ("a",      ""),       # Jana → Jan, Piotra → Piotr, Nowaka → Nowak
]

_GAZETTEER_TOKEN_RE = re.compile(
    r"\b([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?)\b"
)

# Generic two-word labels that look like Name+Surname but are document headings
# or form fields.  These must never be emitted as PERSON/COMPANY findings by the
# gazetteer, regardless of what the gazetteer tables say.
#
# Rules for this list:
#   - Include only two-token phrases (exactly the patterns the gazetteer matches).
#   - Both tokens must be capitalised as in real documents (not ALL-CAPS headings).
#   - Token pairs are stored as (token1_lower, token2_lower) for case-insensitive
#     lookup after lower().
_GAZETTEER_LABEL_STOPLIST: frozenset = frozenset({
    # Common contract / form section headers
    ("dane", "klienta"),
    ("dane", "strony"),
    ("dane", "kontrahenta"),
    ("dane", "zamawiającego"),
    ("dane", "wykonawcy"),
    ("dane", "osobowe"),
    ("dane", "rejestrowe"),
    ("dane", "podmiotu"),
    ("dane", "firmy"),
    ("dane", "spółki"),
    ("dane", "sprzedawcy"),
    ("dane", "nabywcy"),
    ("dane", "kupującego"),
    # Headings with "Nazwa"
    ("nazwa", "spółki"),
    ("nazwa", "firmy"),
    ("nazwa", "podmiotu"),
    ("nazwa", "skrócona"),
    ("nazwa", "pełna"),
    # Headings with "Adres"
    ("adres", "siedziby"),
    ("adres", "zamieszkania"),
    ("adres", "rejestrowy"),
    ("adres", "korespondencyjny"),
    ("adres", "dostawy"),
    # Headings with "Numer" / "Numer" variants
    ("numer", "umowy"),
    ("numer", "zamówienia"),
    ("numer", "faktury"),
    ("numer", "rejestracyjny"),
    # Document metadata labels
    ("data", "umowy"),
    ("data", "zawarcia"),
    ("data", "podpisania"),
    ("data", "wystawienia"),
    ("miejsce", "zawarcia"),
    ("miejsce", "podpisania"),
    ("miejsce", "zamieszkania"),
    # Generic clause headings
    ("postanowienia", "końcowe"),
    ("postanowienia", "ogólne"),
    ("warunki", "płatności"),
    ("warunki", "gwarancji"),
    ("warunki", "dostawy"),
    ("przedmiot", "umowy"),
    ("strony", "umowy"),
    ("forma", "prawna"),
    # Party-declaration fragments
    ("reprezentowany", "przez"),
    ("reprezentowana", "przez"),
    ("działający", "przez"),
    ("działająca", "przez"),
})


def _normalize_name_candidates(token: str) -> List[str]:
    """Return [token] + possible nominative base forms after suffix normalization."""
    candidates = [token]
    tl = token.lower()
    for suffix, replacement in _NAME_NORM_RULES:
        if tl.endswith(suffix) and len(token) - len(suffix) + len(replacement) >= 3:
            base_lower = tl[: len(tl) - len(suffix)] + replacement
            # Restore initial capital
            base = base_lower[0].upper() + base_lower[1:]
            if base not in candidates:
                candidates.append(base)
    return candidates


def _looks_like_surname_suffix(token: str) -> bool:
    """Heuristic: common Polish surname suffixes not requiring a gazetteer."""
    t = token.lower()
    return any(t.endswith(s) for s in (
        "ski", "ska", "cki", "cka", "dzki", "dzka",
        "wski", "wska", "owski", "owska", "ewski", "ewska",
        "iński", "ińska", "yński", "yńska",
        "wicz", "owicz", "ewicz",
        "czyk", "niak", "enko",
    ))


def _looks_like_single_surname(token: str) -> bool:
    """Conservative validation for one-token surnames in strong legal context."""
    cleaned = _clean_alias(token).strip(".,;:()[]{}„”\"'")
    if not cleaned or " " in cleaned or len(cleaned) < 4:
        return False
    if not re.fullmatch(rf"[{LATIN_UPPER}][{LATIN_LETTERS}'’.-]{{2,}}(?:-[{LATIN_UPPER}][{LATIN_LETTERS}'’.-]{{2,}})?", cleaned):
        return False
    if _is_legal_term(cleaned) or _is_role_alias(cleaned):
        return False
    if deaccent_role(cleaned).upper() in COMMON_UPPERCASE_STOPWORDS:
        return False
    is_fn, is_sn, _is_loc = _load_gazetteers()
    candidates = []
    for part in cleaned.split("-"):
        candidates.extend(_normalize_name_candidates(part))
    if is_sn is not None and any(is_sn(c) for c in candidates):
        return True
    return _looks_like_surname_suffix(cleaned)


# Module-level lazy cache for gazetteers
_GAZ_CACHE: dict = {}

def _load_gazetteers() -> tuple:
    """Lazily import pl_gazetteers; return (is_first_name, is_surname, is_locality) or Nones."""
    if "loaded" not in _GAZ_CACHE:
        try:
            from pl_gazetteers import is_first_name, is_surname, is_locality
            _GAZ_CACHE["loaded"] = True
            _GAZ_CACHE["fns"] = (is_first_name, is_surname, is_locality)
        except ImportError:
            _GAZ_CACHE["loaded"] = False
            _GAZ_CACHE["fns"] = (None, None, None)
    return _GAZ_CACHE["fns"]


def collect_gazetteer_findings(text: str) -> List[Finding]:
    """Detect FIRST_NAME + SURNAME pairs using PESEL registry gazetteers.

    Fires even without surrounding legal context (signatory lists, table rows,
    contract party declarations). Handles the most common Polish inflections.
    Returns findings with category PERSON; overlaps resolved by remove_overlaps.
    """
    is_fn, is_sn, is_loc = _load_gazetteers()
    if is_fn is None:
        return []

    findings: List[Finding] = []

    # Collect all capitalized tokens with positions
    tokens = [
        (m.group(1), m.start(), m.end())
        for m in _GAZETTEER_TOKEN_RE.finditer(text)
    ]

    i = 0
    while i < len(tokens) - 1:
        w1, s1, e1 = tokens[i]
        w2, s2, e2 = tokens[i + 1]

        # Tokens must be adjacent (only whitespace / non-breaking space between them)
        gap = text[e1:s2]
        if not re.fullmatch(r"[\s ​]+", gap):
            i += 1
            continue

        # Check against generic label stoplist BEFORE hitting the gazetteer.
        # Two-word document headers (e.g. "Dane Klienta", "Nazwa Spółki") look
        # like <word1> <word2> with capitals but are not person names.
        if (w1.lower(), w2.lower()) in _GAZETTEER_LABEL_STOPLIST:
            i += 1
            continue

        # Normalize both tokens and check gazetteers
        cands1 = _normalize_name_candidates(w1)
        cands2 = _normalize_name_candidates(w2)

        first_name_hit = any(is_fn(c) for c in cands1)
        surname_hit    = (any(is_sn(c) for c in cands2)
                          or _looks_like_surname_suffix(w2))

        if not (first_name_hit and surname_hit):
            i += 1
            continue

        # Avoid false positives: skip if the "surname" is primarily a locality
        # and doesn't look like a surname suffix (e.g. "Pustynia" alone should
        # stay ADDRESS, but "Jan Pustynia" is a real edge case — we keep it as
        # PERSON since it has a confirmed first name in front).
        # The overlap resolver will prefer the longer / higher-priority finding
        # if a dedicated ADDRESS detector already caught it.

        span_start = s1
        span_end   = e2

        # Try to extend to a 3-token name (double first name or middle name).
        # The gap must NOT span newlines: attr_plain separates attribute values
        # with \n\n, so a newline gap would incorrectly merge two separate values
        # (e.g. "Anna Nowak\n\nPiotr") into a value that doesn't exist in any
        # XML node, causing the w:author attribute replace to silently fail.
        if i + 2 < len(tokens):
            w3, s3, e3 = tokens[i + 2]
            gap2 = text[e2:s3]
            if re.fullmatch(r"[ 	 ​]+", gap2):
                cands3 = _normalize_name_candidates(w3)
                if any(is_fn(c) for c in cands3) or any(is_sn(c) for c in cands3) or _looks_like_surname_suffix(w3):
                    span_end = e3

        value = text[span_start:span_end].strip()
        if len(value) >= 5:
            findings.append(Finding("PERSON", value, span_start, span_start + len(value)))

        i += 2  # advance past the consumed pair

    return findings


_OPENING_QUOTE_CHARS = frozenset('"„\'"\'«‹')
_CLOSING_QUOTE_CHARS = frozenset('"\'"\'»›')


def _absorb_orphaned_opening_quotes(text: str, findings: List[Finding]) -> List[Finding]:
    """Extend COMPANY finding spans to include an opening quote that precedes
    the match when the match itself consumed the matching closing quote.

    Example (issue observed in rc17/NUTRIFARM):
        Input:  Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.
        Regex match starts at N: value = 'NUTRIFARM" sp. z o.o.'
          — the closing '"' is consumed but the opening '"' is outside the span.
        After this function: start moves back by 1, value = '"NUTRIFARM" sp. z o.o.'
        Result: the full quoted form is replaced → Klienta = [COMPANY_1] …
        Restore: [COMPANY_1] → '"NUTRIFARM" sp. z o.o.'  (correct, balanced)

    Fires when ALL of:
      1. The character immediately before f.start is an opening-quote character.
      2. The finding value itself contains at least one closing-quote character
         (confirming the regex captured the matching closing quote inside the span).
    """
    result: List[Finding] = []
    for f in findings:
        if (f.start > 0
                and text[f.start - 1] in _OPENING_QUOTE_CHARS
                and any(c in f.value for c in _CLOSING_QUOTE_CHARS)):
            new_start = f.start - 1
            new_value = text[new_start:f.end]
            result.append(Finding(f.category, new_value, new_start, f.end))
        else:
            result.append(f)
    return result


# Global stoplist for generic document label phrases.
# Applied after ALL detectors to prevent section headers, form-field labels and
# boilerplate headings from being mistaken for PII entities.
# Values are normalised to lower-case; Polish accented characters are preserved
# so the lookup works after str.lower() on the candidate value.
# Two-token phrases are also covered by _GAZETTEER_LABEL_STOPLIST (applied
# earlier, before gazetteer gazetteer lookup).  This list is the last safety net
# and covers values from ALL detectors (base, contextual, gazetteer, NLP).
_GLOBAL_LABEL_STOPLIST: frozenset = frozenset({
    # ── Dane … labels ────────────────────────────────────────────────────────
    "dane klienta", "dane strony", "dane kontrahenta",
    "dane zamawiającego", "dane zamawiajacego",
    "dane wykonawcy", "dane osobowe", "dane rejestrowe",
    "dane podmiotu", "dane firmy", "dane spółki", "dane spolki",
    "dane sprzedawcy", "dane nabywcy", "dane kupującego", "dane kupujacego",
    # ── Nazwa … labels ───────────────────────────────────────────────────────
    "nazwa spółki", "nazwa spolki",
    "nazwa firmy", "nazwa podmiotu",
    "nazwa skrócona", "nazwa skrocona",
    "nazwa pełna", "nazwa pelna",
    # ── Adres … labels ───────────────────────────────────────────────────────
    "adres siedziby", "adres zamieszkania",
    "adres rejestrowy", "adres korespondencyjny", "adres dostawy",
    # ── Numer … labels ───────────────────────────────────────────────────────
    "numer umowy", "numer zamówienia", "numer zamowienia",
    "numer faktury", "numer rejestracyjny",
    # ── Data / Miejsce … labels ──────────────────────────────────────────────
    "data umowy", "data zawarcia", "data podpisania", "data wystawienia",
    "miejsce zawarcia", "miejsce podpisania", "miejsce zamieszkania",
    # ── Clause headings ──────────────────────────────────────────────────────
    "postanowienia końcowe", "postanowienia koncowe",
    "postanowienia ogólne", "postanowienia ogolne",
    "warunki płatności", "warunki platnosci",
    "warunki gwarancji", "warunki dostawy",
    "przedmiot umowy", "strony umowy", "forma prawna",
})


def _filter_label_stoplist(findings: List[Finding]) -> List[Finding]:
    """Remove findings whose normalised value is a generic document label."""
    result = []
    for f in findings:
        if f.value.lower() in _GLOBAL_LABEL_STOPLIST:
            continue
        result.append(f)
    return result


def collect_standard_findings(text: str) -> List[Finding]:
    # Normalise to NFC so that decomposed Polish characters from macOS (e.g.
    # NFD "a" + combining ogonek) match the NFC forms used in gazetteers and
    # regex patterns.  NFC is idempotent for documents already in NFC (Windows).
    text = unicodedata.normalize("NFC", text)
    base_findings: List[Finding] = collect_base_findings(text) + collect_nlp_findings(text)
    contextual_findings = collect_contextual_findings(text, base_findings)
    gazetteer_findings = collect_gazetteer_findings(text)
    all_findings = remove_overlaps(base_findings + contextual_findings + gazetteer_findings)
    all_findings = _filter_label_stoplist(all_findings)
    return _absorb_orphaned_opening_quotes(text, all_findings)


def collect_findings(text: str, mode: str = "standard") -> List[Finding]:
    # Bielik is not part of automatic masking. review_mode is handled after
    # masking by collect_bielik_deep_review_findings().
    normalize_review_mode(mode)
    return collect_standard_findings(text)


def remove_overlaps(findings: List[Finding]) -> List[Finding]:
    ordered = sorted(
        findings,
        key=lambda f: (f.start, -(f.end - f.start), -PRIORITY.get(f.category, 0)),
    )
    accepted: List[Finding] = []
    # Because ``ordered`` is sorted by increasing start offset, accepted spans are
    # also accepted in document order. A new span can only overlap the last
    # accepted span (tracked by max_occupied_end), so the old O(n^2) scan over all
    # occupied spans is unnecessary and became visible on long DOCX files with
    # thousands of findings.
    max_occupied_end = -1
    for f in ordered:
        if f.start < max_occupied_end:
            continue
        accepted.append(f)
        if f.end > max_occupied_end:
            max_occupied_end = f.end
    return accepted



PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9_]{1,60}\]")


def _existing_placeholders(text: str) -> Set[str]:
    """Literal placeholder-like strings already present in the source document.

    Generated placeholders must avoid these values so restore does not rewrite a
    user-authored literal such as [COMPANY_1].
    """
    return set(PLACEHOLDER_RE.findall(text or ""))


def _unique_placeholder(candidate: str, reserved: Set[str]) -> str:
    if candidate not in reserved:
        reserved.add(candidate)
        return candidate
    # Prefer normal placeholder shapes over technical suffixes.
    # [COMPANY_1] -> [COMPANY_2], [COMPANY_1_ALIAS_1] -> [COMPANY_1_ALIAS_2]
    m_alias = re.fullmatch(r"\[([A-Z]+_\d+_ALIAS_)(\d+)\]", candidate)
    if m_alias:
        prefix, num = m_alias.group(1), int(m_alias.group(2))
        i = num + 1
        while True:
            alt = f"[{prefix}{i}]"
            if alt not in reserved:
                reserved.add(alt)
                return alt
            i += 1
    m_simple = re.fullmatch(r"\[([A-Z]+_)(\d+)\]", candidate)
    if m_simple:
        prefix, num = m_simple.group(1), int(m_simple.group(2))
        i = num + 1
        while True:
            alt = f"[{prefix}{i}]"
            if alt not in reserved:
                reserved.add(alt)
                return alt
            i += 1
    base = candidate[:-1] if candidate.endswith("]") else candidate
    i = 2
    while True:
        alt = f"{base}_X{i}]"
        if alt not in reserved:
            reserved.add(alt)
            return alt
        i += 1

def build_replacement_plan(findings: Iterable[Finding], reserved_placeholders: Set[str] | None = None) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], int]]:
    findings_list = list(findings)
    ledger = IdentityLedger(findings_list)
    family_counters: Dict[str, int] = {}
    entity_to_family: Dict[Tuple[str, str], str] = {}
    entity_surface_counters: Dict[Tuple[str, str], int] = {}
    entity_primary_surface: Dict[Tuple[str, str], Tuple[str, str]] = {}
    seen: Dict[Tuple[str, str], str] = {}
    counts: Dict[Tuple[str, str], int] = {}
    reserved = set(reserved_placeholders or set())

    for f in findings_list:
        original_key = (f.category, f.value)
        entity_key = ledger.key_for(f)
        family_category = entity_key[0]

        if entity_key not in entity_to_family:
            family_counters[family_category] = family_counters.get(family_category, 0) + 1
            entity_to_family[entity_key] = f"{_pl_placeholder_family(family_category)}_{family_counters[family_category]}"
            entity_primary_surface[entity_key] = original_key
            entity_surface_counters[entity_key] = 0
        else:
            # Prefer a full explicit entity over a short alias as the primary surface.
            current_primary = entity_primary_surface.get(entity_key)
            if current_primary and family_category == "COMPANY" and f.category == "COMPANY" and current_primary[0] in {"COMPANY_CODE", "ALIAS", "COMPANY_ALIAS", "CONTRACTOR_ALIAS"}:
                entity_primary_surface[entity_key] = original_key
            if current_primary and family_category == "PERSON" and f.category == "PERSON" and current_primary[0] == "PERSON_ALIAS":
                entity_primary_surface[entity_key] = original_key

        family = entity_to_family[entity_key]
        if original_key not in seen:
            primary = entity_primary_surface[entity_key]
            alias_like = (
                original_key != primary
                or f.category in {"ALIAS", "COMPANY_ALIAS", "CONTRACTOR_ALIAS", "PROJECT_ALIAS", "PERSON_ALIAS", "DOMAIN_ALIAS", "COURT_ALIAS", "COMPANY_CODE"}
            )
            if alias_like and family_category in {"COMPANY", "PERSON", "DOMAIN", "PROJECT", "COURT"}:
                entity_surface_counters[entity_key] = entity_surface_counters.get(entity_key, 0) + 1
                seen[original_key] = _unique_placeholder(f"[{family}_ALIAS_{entity_surface_counters[entity_key]}]", reserved)
            else:
                seen[original_key] = _unique_placeholder(f"[{family}]", reserved)
            counts[original_key] = 0
        counts[original_key] += 1
    return seen, counts


def replacements_from_plan(seen: Dict[Tuple[str, str], str], counts: Dict[Tuple[str, str], int]) -> List[Replacement]:
    replacements = [
        Replacement(category=category, original=original, placeholder=placeholder, count=counts[(category, original)])
        for (category, original), placeholder in seen.items()
    ]
    replacements.sort(key=lambda r: (r.category, r.placeholder))
    return replacements


def make_replacements(text: str) -> Tuple[str, List[Replacement]]:
    return make_replacements_with_controls(text, None)




# ---------- Local map protection ----------
# On Windows, maps are protected with DPAPI current-user encryption. This means
# that the JSON map can be read back by the same Windows user but is not stored
# as plaintext on disk. On non-Windows systems the engine falls back to a plain
# envelope so tests and development still work; the UI/documentation treats
# Windows DPAPI as the production path.

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.c_void_p)]


def _bytes_to_blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob._buffer = buf  # keep alive
    return blob


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    if not blob.pbData or not blob.cbData:
        return b""
    data = ctypes.string_at(blob.pbData, blob.cbData)
    try:
        ctypes.windll.kernel32.LocalFree(blob.pbData)
    except Exception:
        pass
    return data


def _dpapi_encrypt(data: bytes) -> bytes | None:
    if platform.system().lower() != "windows":
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        in_blob = _bytes_to_blob(data)
        out_blob = _DATA_BLOB()
        ok = crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return None
        return _blob_to_bytes(out_blob)
    except Exception:
        return None


def _dpapi_decrypt(data: bytes) -> bytes | None:
    if platform.system().lower() != "windows":
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        in_blob = _bytes_to_blob(data)
        out_blob = _DATA_BLOB()
        ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return None
        return _blob_to_bytes(out_blob)
    except Exception:
        return None


def _protect_payload(payload: dict) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    encrypted = _dpapi_encrypt(raw)
    if encrypted:
        return {
            "format": "claude-safe-mode-map-v2",
            "encrypted": True,
            "method": "windows-dpapi-current-user",
            "ciphertext": base64.b64encode(encrypted).decode("ascii"),
        }
    return {
        "format": "claude-safe-mode-map-v2",
        "encrypted": False,
        "method": "plain-dev-fallback",
        "payload": payload,
    }


def _unprotect_payload(envelope: dict) -> dict:
    if envelope.get("format") != "claude-safe-mode-map-v2":
        # Backward compatibility with maps created by v0.2.0 and earlier.
        return envelope
    if envelope.get("encrypted"):
        data = base64.b64decode(envelope.get("ciphertext", ""))
        raw = _dpapi_decrypt(data)
        if raw is None:
            raise ValueError("Could not decrypt local map with Windows DPAPI for current user")
        return json.loads(raw.decode("utf-8"))
    return envelope.get("payload", {})


# ---------- Install-folder emergency backups ----------
# These backups are deliberately stored under the installation root, e.g. C:\CSM\backups
# (the installation folder) because the user asked for a recovery location that
# remains easy to find even if document settings or the encrypted user map are
# unavailable. They may contain original client data and should be treated as
# highly confidential.

def _safe_map_id(map_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "", map_id or "")


def _backup_dir_for(map_id: str) -> Path:
    safe = _safe_map_id(map_id)
    return INSTALL_BACKUPS_DIR / safe


BACKUP_PAYLOAD_FILENAME = "backup_payload.csmmap"
LEGACY_BACKUP_FILENAMES = (
    "original_visible_text.txt",
    "original_ooxml_parts.json",
    "original_ooxml.xml",
    "original_docx_base64.txt",
    "original_document.docx",
)


def _backup_payload_file(bdir: Path) -> Path:
    return bdir / BACKUP_PAYLOAD_FILENAME


def _backup_method_for_envelope(envelope: dict) -> str:
    if envelope.get("encrypted"):
        return str(envelope.get("method") or "encrypted")
    return str(envelope.get("method") or "plain-dev-fallback")


def write_install_backup(payload: dict) -> None:
    map_id = payload.get("map_id")
    if not map_id:
        return
    bdir = _backup_dir_for(map_id)
    bdir.mkdir(parents=True, exist_ok=True)

    # The emergency backup contains the "additional information" needed for
    # re-identification. Store it in the same protected envelope as the normal
    # map instead of writing plaintext copies of the original DOCX/XML/text. On
    # Windows this uses DPAPI for the current user. Legacy plaintext backup
    # filenames are removed on successful write to reduce disclosure risk during
    # upgrades from older CSM builds.
    envelope = _protect_payload(payload)
    payload_path = _backup_payload_file(bdir)
    payload_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    for legacy_name in LEGACY_BACKUP_FILENAMES:
        try:
            (bdir / legacy_name).unlink(missing_ok=True)
        except Exception:
            pass

    metadata = {
        "map_id": map_id,
        "created_at": payload.get("created_at"),
        "engine_version": payload.get("engine_version"),
        "source_hash_sha256": payload.get("source_hash_sha256"),
        "has_original_text": bool(payload.get("original_text")),
        "has_original_ooxml": bool(payload.get("original_ooxml")),
        "has_original_docx": bool(payload.get("original_docx_base64")),
        "protected_payload": True,
        "payload_file": BACKUP_PAYLOAD_FILENAME,
        "protection_method": _backup_method_for_envelope(envelope),
        "warning": "This folder contains re-identification information. Keep it separate and confidential.",
    }
    (bdir / "backup_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (bdir / "WARNING.txt").write_text(
        "UWAGA: Ten folder zawiera dodatkowe informacje potrzebne do odwrócenia pseudonimizacji. "
        "Traktuj go jak dane poufne. W Windows zawartość jest chroniona przez konto użytkownika; "
        "nie kopiuj folderu osobom nieuprawnionym i usuń kopie, gdy nie są już potrzebne.\n",
        encoding="utf-8",
    )


def _load_legacy_install_backup(bdir: Path, map_id: str) -> dict:
    payload: dict[str, object] = {"map_id": _safe_map_id(map_id), "legacy_plaintext_backup": True}
    if (bdir / "original_visible_text.txt").exists():
        payload["original_text"] = (bdir / "original_visible_text.txt").read_text(encoding="utf-8")
    if (bdir / "original_ooxml_parts.json").exists():
        payload["original_ooxml"] = (bdir / "original_ooxml_parts.json").read_text(encoding="utf-8")
    elif (bdir / "original_ooxml.xml").exists():
        payload["original_ooxml"] = (bdir / "original_ooxml.xml").read_text(encoding="utf-8")
    if (bdir / "original_docx_base64.txt").exists():
        payload["original_docx_base64"] = (bdir / "original_docx_base64.txt").read_text(encoding="utf-8")
    elif (bdir / "original_document.docx").exists():
        payload["original_docx_base64"] = base64.b64encode((bdir / "original_document.docx").read_bytes()).decode("ascii")
    return payload


def load_install_backup(map_id: str) -> dict:
    bdir = _backup_dir_for(map_id)
    if not bdir.exists():
        raise FileNotFoundError(f"Install backup not found: {map_id}")
    manifest: dict[str, object] = {}
    if (bdir / "backup_manifest.json").exists():
        try:
            manifest = json.loads((bdir / "backup_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    payload_path = _backup_payload_file(bdir)
    if payload_path.exists():
        envelope = json.loads(payload_path.read_text(encoding="utf-8"))
        payload = _unprotect_payload(envelope)
    else:
        payload = _load_legacy_install_backup(bdir, map_id)
    if manifest:
        payload["manifest"] = manifest
    return payload


def latest_install_backup_id() -> str | None:
    candidates = []
    if not INSTALL_BACKUPS_DIR.exists():
        return None
    for child in INSTALL_BACKUPS_DIR.iterdir():
        if child.is_dir() and (child / "backup_manifest.json").exists():
            candidates.append(child)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0].name


def list_install_backups() -> list[dict]:
    items = []
    if not INSTALL_BACKUPS_DIR.exists():
        return items
    for child in sorted([c for c in INSTALL_BACKUPS_DIR.iterdir() if c.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        manifest_path = child / "backup_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {"map_id": child.name}
        meta["folder"] = str(child)
        items.append(meta)
    return items


def save_map(replacements: List[Replacement], source_hash: str | None = None, original_ooxml: str | None = None, original_text: str | None = None, original_docx_base64: str | None = None, require_install_backup: bool = False, extra_payload: Dict[str, Any] | None = None) -> str:
    map_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    created_at_dt = datetime.now()
    try:
        retention_days = int(load_config().get("map_retention_days", 30) or 30)
    except Exception:
        retention_days = 30
    payload = {
        "map_id": map_id,
        "created_at": created_at_dt.isoformat(timespec="seconds"),
        "expires_at": (created_at_dt + timedelta(days=max(1, retention_days))).isoformat(timespec="seconds"),
        "retention_days": max(1, retention_days),
        "engine_version": "0.2.48-rc19-pl-gazetteers",
        "source_hash_sha256": source_hash,
        "replacements": [asdict(r) for r in replacements],
        # Safety net: keep the original body payload locally so the user can recover
        # the pre-Claude document even if placeholders are accidentally edited. This
        # is not returned to Claude during normal masking.
        "original_ooxml": original_ooxml,
        "original_text": original_text,
        "original_docx_base64": original_docx_base64,
    }
    if extra_payload:
        payload.update(extra_payload)
    envelope = _protect_payload(payload)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    path = MAPS_DIR / f"{map_id}.json"
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    if require_install_backup:
        try:
            write_install_backup(payload)
            loaded_backup = load_install_backup(map_id)
            if original_docx_base64 and not loaded_backup.get("original_docx_base64"):
                raise RuntimeError("Install-folder backup was written without original DOCX data")
        except Exception as exc:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"Could not create required install-folder backup in {INSTALL_BACKUPS_DIR}: {exc}") from exc
    else:
        try:
            write_install_backup(payload)
        except Exception:
            # Backup failure must not block older/diagnostic modes, but emergency recovery will be weaker.
            pass
    return map_id


def load_map(map_id: str) -> dict:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "", map_id)
    path = MAPS_DIR / f"{safe}.json"
    if not path.exists():
        raise FileNotFoundError(f"Map not found: {map_id}")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    return _unprotect_payload(envelope)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- OOXML-aware replacement ----------
# Word search sometimes misses values split across formatting runs. The OOXML path works on
# all w:t text nodes in the document body returned by Word and can replace text spanning
# multiple runs while preserving most formatting.

def _is_text_node(el: ET.Element) -> bool:
    return el.tag.endswith("}t") or el.tag == "t" or el.tag.endswith("}delText") or el.tag.endswith("}instrText")


def _xml_local_name(tag: str) -> str:
    return str(tag).split('}', 1)[-1]


def _collect_text_nodes(root: ET.Element) -> Tuple[List[Tuple[ET.Element, int, int]], str]:
    nodes: List[Tuple[ET.Element, int, int]] = []
    parts: List[str] = []
    pos = 0
    sep = "\ue000"
    last_context: Tuple[str, ...] | None = None
    text_seen = False
    revision_tags = {"ins", "del", "moveFrom", "moveTo"}
    block_tags = {"p", "tbl", "tr", "tc", "footnote", "endnote", "comment"}

    def add_separator() -> None:
        nonlocal pos
        if parts and parts[-1] != sep:
            parts.append(sep)
            pos += len(sep)

    def walk(el: ET.Element, context: Tuple[str, ...]) -> None:
        nonlocal pos, last_context, text_seen
        lname = _xml_local_name(el.tag)
        child_context = context
        if lname in block_tags and text_seen:
            child_context = context + (f"block:{id(el)}",)
            add_separator()
        if lname in revision_tags:
            child_context = context + (f"revision:{lname}:{el.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id', id(el))}",)
            if text_seen:
                add_separator()
        if _is_text_node(el):
            txt = el.text or ""
            if txt:
                if last_context is not None and child_context != last_context:
                    add_separator()
                start = pos
                pos += len(txt)
                nodes.append((el, start, pos))
                parts.append(txt)
                last_context = child_context
                text_seen = True
        for child in list(el):
            walk(child, child_context)

    walk(root, tuple())
    return nodes, "".join(parts)


def _node_end_index(nodes: List[Tuple[ET.Element, int, int]]) -> List[int]:
    return [n_end for _el, _n_start, n_end in nodes]


def _replace_range_in_nodes(
    nodes: List[Tuple[ET.Element, int, int]],
    start: int,
    end: int,
    replacement: str,
    node_ends: List[int] | None = None,
) -> None:
    first_done = False
    ends = node_ends if node_ends is not None else _node_end_index(nodes)
    i = bisect.bisect_right(ends, start)
    while i < len(nodes):
        el, n_start, n_end = nodes[i]
        if n_start >= end:
            break
        if n_end <= start:
            i += 1
            continue
        txt = el.text or ""
        local_start = max(start - n_start, 0)
        local_end = min(end - n_start, len(txt))
        before = txt[:local_start]
        after = txt[local_end:]
        if not first_done:
            el.text = before + replacement + (after if end <= n_end else "")
            first_done = True
        else:
            el.text = after if end <= n_end else ""
        i += 1


def _serialize_xml(root: ET.Element) -> str:
    return ET.tostring(root, encoding="unicode")


def mask_ooxml(ooxml: str) -> Tuple[str, List[Replacement]]:
    root = _parse_xml_text(ooxml)
    nodes, plain_text = _collect_text_nodes(root)
    findings = collect_findings(plain_text)
    seen, counts = build_replacement_plan(findings, _existing_placeholders(plain_text))
    # Apply from the end so global offsets stay valid. The node-end index avoids
    # rescanning every Word run for every finding in long files.
    node_ends = _node_end_index(nodes)
    for f in sorted(findings, key=lambda item: item.start, reverse=True):
        placeholder = seen[(f.category, f.value)]
        _replace_range_in_nodes(nodes, f.start, f.end, placeholder, node_ends)
    return _serialize_xml(root), replacements_from_plan(seen, counts)




def _placeholder_lookup(replacements_payload: List[dict]) -> Dict[str, str]:
    return {
        str(r.get("placeholder") or ""): str(r.get("original") or "")
        for r in replacements_payload
        if r.get("placeholder")
    }


def _placeholder_alternation(lookup: Dict[str, str]) -> re.Pattern | None:
    placeholders = sorted(lookup, key=lambda item: (-len(item), item))
    if not placeholders:
        return None
    return re.compile("|".join(re.escape(ph) for ph in placeholders))


def _find_placeholder_spans(text: str, replacements_payload: List[dict]) -> List[Tuple[int, int, str]]:
    lookup = _placeholder_lookup(replacements_payload)
    pattern = _placeholder_alternation(lookup)
    if pattern is None or not text:
        return []
    return [(m.start(), m.end(), lookup[m.group(0)]) for m in pattern.finditer(text)]


def placeholder_report(text: str, replacements_payload: List[dict]) -> Dict[str, Any]:
    expected = [r.get("placeholder", "") for r in replacements_payload if r.get("placeholder")]
    unique_expected = sorted(set(expected))
    counts: Dict[str, int] = {ph: text.count(ph) for ph in unique_expected}
    found = {ph: count for ph, count in counts.items() if count > 0}
    missing = [ph for ph, count in counts.items() if count == 0]
    unknown = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]{1,40}\]", text)) - set(unique_expected))
    return {
        "expected_total": len(unique_expected),
        "found_total": len(found),
        "missing_total": len(missing),
        "unknown_total": len(unknown),
        "missing_placeholders": missing[:50],
        "unknown_placeholders": unknown[:50],
        "all_found": len(missing) == 0,
    }


def _restore_text_value(text: str, replacements_payload: List[dict]) -> Tuple[str, Dict[str, Any]]:
    before = placeholder_report(text, replacements_payload)
    lookup = _placeholder_lookup(replacements_payload)
    pattern = _placeholder_alternation(lookup)
    restored_count = 0
    if pattern is None:
        restored = text
    else:
        def repl(match: re.Match) -> str:
            nonlocal restored_count
            restored_count += 1
            return lookup.get(match.group(0), match.group(0))
        restored = pattern.sub(repl, text)
    after_unknown = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]{1,40}\]", restored)))
    before["restored_occurrences"] = restored_count
    before["leftover_placeholders_after_restore"] = after_unknown[:50]
    before["leftover_total_after_restore"] = len(after_unknown)
    return restored, before

def _plain_with_sensitive_attributes(root: ET.Element, plain_text: str) -> str:
    attr_plain = _collect_sensitive_attributes_as_text(root)
    if attr_plain:
        return plain_text + "\n\n" + attr_plain
    return plain_text


def _restore_placeholders_in_xml_string(xml: str, replacements_payload: List[dict]) -> Tuple[str, int]:
    lookup = _placeholder_lookup(replacements_payload)
    pattern = _placeholder_alternation(lookup)
    if pattern is None or not xml:
        return xml, 0
    restored_count = 0

    def repl(match: re.Match) -> str:
        nonlocal restored_count
        restored_count += 1
        return _xml_escape_attr(lookup.get(match.group(0), match.group(0)))

    out = pattern.sub(repl, xml)
    try:
        _parse_xml_text(out)
    except Exception:
        return xml, 0
    return out, restored_count

def restore_ooxml_with_report(ooxml: str, replacements_payload: List[dict]) -> Tuple[str, Dict[str, Any]]:
    root = _parse_xml_text(ooxml)
    nodes, plain_text = _collect_text_nodes(root)
    report = placeholder_report(_plain_with_sensitive_attributes(root, plain_text), replacements_payload)
    spans = _find_placeholder_spans(plain_text, replacements_payload)
    node_ends = _node_end_index(nodes)
    for start, end, original in sorted(spans, key=lambda item: item[0], reverse=True):
        _replace_range_in_nodes(nodes, start, end, original, node_ends)
    restored = _serialize_xml(root)
    restored, attr_restored = _restore_placeholders_in_xml_string(restored, replacements_payload)
    report["restored_occurrences"] = len(spans) + attr_restored
    leftover = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]{1,40}\]", restored)))
    report["leftover_placeholders_after_restore"] = leftover[:50]
    report["leftover_total_after_restore"] = len(leftover)
    return restored, report


def restore_ooxml(ooxml: str, replacements_payload: List[dict]) -> str:
    restored, _ = restore_ooxml_with_report(ooxml, replacements_payload)
    return restored


def restore_xml_part_with_report(xml: str, replacements_payload: List[dict], part_name: str = "") -> Tuple[str, Dict[str, Any]]:
    root, nodes, plain_text = _extract_xml_part_text(xml, part_name)
    report = placeholder_report(_plain_with_sensitive_attributes(root, plain_text), replacements_payload)
    spans = _find_placeholder_spans(plain_text, replacements_payload)
    node_ends = _node_end_index(nodes)
    for start, end, original in sorted(spans, key=lambda item: item[0], reverse=True):
        _replace_range_in_nodes(nodes, start, end, original, node_ends)
    restored = _serialize_xml(root)
    restored, attr_restored = _restore_placeholders_in_xml_string(restored, replacements_payload)
    report["restored_occurrences"] = len(spans) + attr_restored
    leftover = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]{1,40}\]", restored)))
    report["leftover_placeholders_after_restore"] = leftover[:50]
    report["leftover_total_after_restore"] = len(leftover)
    return restored, report




# ---------- Multi-part OOXML support ----------
# Word add-ins can access the main body and, on some Office builds, headers and
# footers. These helpers let the API mask all supplied OOXML parts with a single
# replacement plan so aliases/placeholders remain consistent across the document.


def mask_ooxml_parts(parts: Dict[str, str]) -> Tuple[Dict[str, str], List[Replacement]]:
    parsed: Dict[str, Tuple[ET.Element, List[Tuple[ET.Element, int, int]], str, str, int]] = {}
    all_text_parts: List[str] = []
    offset = 0
    separator = "\ue000CSM_PART_BOUNDARY\ue001"
    for name, xml in parts.items():
        if not xml:
            continue
        try:
            root = _parse_xml_text(xml)
            nodes, visible_plain = _collect_text_nodes(root)
            attr_plain = _collect_sensitive_attributes_as_text(root)
            search_plain = visible_plain + (separator + attr_plain if attr_plain else "")
        except XmlSecurityError:
            raise
        except Exception:
            continue
        parsed[name] = (root, nodes, visible_plain, search_plain, offset)
        all_text_parts.append(search_plain)
        offset += len(search_plain) + len(separator)
    combined = separator.join(all_text_parts)
    findings = collect_findings(combined)
    seen, counts = build_replacement_plan(findings, _existing_placeholders(combined))
    for name, (root, nodes, visible_plain, search_plain, part_offset) in parsed.items():
        part_start = part_offset
        visible_end = part_offset + len(visible_plain)
        part_findings = [
            Finding(f.category, f.value, f.start - part_start, f.end - part_start)
            for f in findings
            if f.start >= part_start and f.end <= visible_end
        ]
        node_ends = _node_end_index(nodes)
        for f in sorted(part_findings, key=lambda item: item.start, reverse=True):
            placeholder = seen[(f.category, f.value)]
            _replace_range_in_nodes(nodes, f.start, f.end, placeholder, node_ends)
    out_parts: Dict[str, str] = {}
    for name, (root, nodes, visible_plain, search_plain, off) in parsed.items():
        _apply_seen_to_sensitive_attributes(root, seen)
        try:
            _strip_unmapped_revision_author_attributes(root)
        except Exception:
            pass
        out_parts[name] = _serialize_xml(root)
    return out_parts, replacements_from_plan(seen, counts)


def restore_ooxml_parts(parts: Dict[str, str], replacements_payload: List[dict]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    restored: Dict[str, str] = {}
    aggregate: Dict[str, Any] = {
        "expected_total": 0,
        "found_total": 0,
        "missing_total": 0,
        "unknown_total": 0,
        "missing_placeholders": [],
        "unknown_placeholders": [],
        "restored_occurrences": 0,
        "leftover_placeholders_after_restore": [],
        "leftover_total_after_restore": 0,
        "parts": {},
    }
    missing_set: Set[str] = set()
    unknown_set: Set[str] = set()
    leftover_set: Set[str] = set()
    expected_set = {r.get("placeholder", "") for r in replacements_payload if r.get("placeholder")}
    found_set: Set[str] = set()
    for name, xml in parts.items():
        try:
            out, report = restore_ooxml_with_report(xml, replacements_payload)
            restored[name] = out
        except Exception:
            restored[name] = xml
            report = {"error": "restore failed for this OOXML part"}
        aggregate["parts"][name] = report
        aggregate["restored_occurrences"] += int(report.get("restored_occurrences", 0) or 0)
        for ph in report.get("missing_placeholders", []) or []:
            missing_set.add(ph)
        for ph in report.get("unknown_placeholders", []) or []:
            unknown_set.add(ph)
        for ph in report.get("leftover_placeholders_after_restore", []) or []:
            leftover_set.add(ph)
        if "expected_total" in report:
            part_missing = set(report.get("missing_placeholders", []) or [])
            for ph in expected_set:
                if ph not in part_missing:
                    found_set.add(ph)
    aggregate["expected_total"] = len(expected_set)
    aggregate["found_total"] = len(found_set)
    aggregate["missing_placeholders"] = sorted(expected_set - found_set)[:50]
    aggregate["missing_total"] = len(expected_set - found_set)
    aggregate["unknown_placeholders"] = sorted(unknown_set)[:50]
    aggregate["unknown_total"] = len(unknown_set)
    aggregate["leftover_placeholders_after_restore"] = sorted(leftover_set)[:50]
    aggregate["leftover_total_after_restore"] = len(leftover_set)
    aggregate["all_found"] = aggregate["missing_total"] == 0
    return restored, aggregate


def ooxml_parts_to_text(parts: Dict[str, str]) -> str:
    values: List[str] = []
    for xml in parts.values():
        try:
            values.append(ooxml_to_text(xml))
        except Exception:
            continue
    return "\n\n".join(values)

def ooxml_to_text(ooxml: str) -> str:
    """Extract concatenated visible text from Word OOXML for residual-risk scanning."""
    root = _parse_xml_text(ooxml)
    _, plain_text = _collect_text_nodes(root)
    return plain_text




# ---------- XML attribute scrubbing and tracked-change hardening ----------
# Comments and tracked-change balloons store author names and some deleted/inserted
# text outside normal w:t nodes. We apply the same replacement plan to serialized
# XML attributes and optionally flatten revision wrappers in the Claude-safe view.

_ATTR_SENSITIVE_NAME_RE = re.compile(r"(?:^|})(?:author|initials|creator|lastModifiedBy|title|subject|description|keywords|category|company|manager|descr|tooltip|alt|name)$", re.I)


def _xml_escape_attr(value: str) -> str:
    return (value.replace("&", "&amp;")
                 .replace('"', "&quot;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))


def _apply_seen_to_xml_string(xml: str, seen: Dict[Tuple[str, str], str]) -> str:
    out = xml
    for (_category, original), placeholder in sorted(seen.items(), key=lambda item: len(item[0][1]), reverse=True):
        if not original:
            continue
        out = out.replace(_xml_escape_attr(original), placeholder)
        out = out.replace(original, placeholder)
    try:
        _parse_xml_text(out)
    except Exception:
        return xml
    return out


def _apply_seen_to_sensitive_attributes(root: ET.Element, seen: Dict[Tuple[str, str], str]) -> int:
    """Replace mapped values only inside sensitive XML attributes.

    Older code serialized each XML part and ran ``str.replace`` for every mapped
    value over the entire document XML. That is safe but expensive for long Word
    files. Attribute values are already available through ElementTree, so we only
    touch attributes that may contain user/client identifiers (author, title, alt
    text, company, etc.).
    """
    changed = 0
    replacements = sorted(
        ((original, placeholder) for (_category, original), placeholder in seen.items() if original),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    if not replacements:
        return 0
    for el in root.iter():
        for key in list(el.attrib.keys()):
            if not _ATTR_SENSITIVE_NAME_RE.search(key):
                continue
            value = str(el.attrib.get(key, ""))
            new_value = value
            for original, placeholder in replacements:
                if original in new_value:
                    new_value = new_value.replace(original, placeholder)
            if new_value != value:
                el.attrib[key] = new_value
                changed += 1
    return changed


def _collect_sensitive_attributes_as_text(root: ET.Element) -> str:
    vals: List[str] = []
    for el in root.iter():
        for key, val in el.attrib.items():
            if val and _ATTR_SENSITIVE_NAME_RE.search(key):
                vals.append(str(val))
    return "\n\n".join(vals)


PLACEHOLDER_VALUE_RE = re.compile(r"^\[[A-Z][A-Z0-9_]{1,40}\]$")


def _strip_unmapped_revision_author_attributes(root: ET.Element) -> None:
    for el in root.iter():
        for key in list(el.attrib.keys()):
            value = str(el.attrib.get(key, ""))
            if PLACEHOLDER_VALUE_RE.match(value):
                continue
            if key.endswith('}author') or key == 'author':
                # Do not leak user identity in Word revision/comment balloons. If the
                # value was mapped, it is already a placeholder and remains restorable.
                el.attrib[key] = "anonimowy"
            if key.endswith('}initials') or key == 'initials':
                el.attrib[key] = "an."


# ---------- Full DOCX package support (best effort) ----------
# This mode processes the raw .docx ZIP package, not only the main body OOXML
# exposed by Word APIs. It is intended to cover comments, footnotes, endnotes,
# headers, footers, text boxes stored as w:t nodes, custom XML and document
# metadata. The Word add-in no longer replaces the open document with a full
# DOCX package; the package helpers remain for API-side scanning/masking and
# emergency/manual workflows, while the panel uses part-based OOXML.

DOCX_XML_PART_RE = re.compile(
    r"^(?:word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments|commentsExtended|commentsIds|glossary/document)\.xml|"
    r"word/(?:numbering|styles|settings|webSettings|fontTable)\.xml|"
    r"docProps/(?:core|app|custom)\.xml|customXml/item\d+\.xml)$",
    re.IGNORECASE,
)

# Parts where user/client data is likely to appear and should be masked.
DOCX_CONTENT_PART_RE = re.compile(
    r"^(?:word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments|glossary/document)\.xml|"
    r"docProps/(?:core|app|custom)\.xml|customXml/item\d+\.xml)$",
    re.IGNORECASE,
)

METADATA_PART_RE = re.compile(r"^docProps/(?:core|app|custom)\.xml$", re.IGNORECASE)
SETTINGS_PART_RE = re.compile(r"^word/settings\.xml$", re.IGNORECASE)

IMAGE_PART_RE = re.compile(r"^word/media/[^/]+\.(?:png|jpe?g|gif|bmp|tiff?|webp)$", re.IGNORECASE)
_REDACTED_IMAGE_BASE64 = {
    "png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC",
    "jpg": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==",
    "jpeg": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==",
    "gif": "R0lGODdhAQABAIEAAP///wAAAAAAAAAAACwAAAAAAQABAAAIBAABBAQAOw==",
    "bmp": "Qk06AAAAAAAAADYAAAAoAAAAAQAAAAEAAAABABgAAAAAAAQAAADEDgAAxA4AAAAAAAAAAAAA////AA==",
    "tif": "SUkqAAgAAAAKAAABBAABAAAAAQAAAAEBBAABAAAAAQAAAAIBAwADAAAAhgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAAAAjAAAABUBAwABAAAAAwAAABYBBAABAAAAAQAAABcBBAABAAAAAwAAABwBAwABAAAAAQAAAAAAAAAIAAgACAD///8=",
    "tiff": "SUkqAAgAAAAKAAABBAABAAAAAQAAAAEBBAABAAAAAQAAAAIBAwADAAAAhgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAAAAjAAAABUBAwABAAAAAwAAABYBBAABAAAAAQAAABcBBAABAAAAAwAAABwBAwABAAAAAQAAAAAAAAAIAAgACAD///8=",
    "webp": "UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAUAmJaQAA3AA/vz0AAA=",
}


def _part_is_image(name: str) -> bool:
    return bool(IMAGE_PART_RE.match(name or ""))


def _redacted_image_bytes(name: str) -> bytes:
    ext = (name.rsplit(".", 1)[-1] if "." in name else "png").lower()
    return base64.b64decode((_REDACTED_IMAGE_BASE64.get(ext) or _REDACTED_IMAGE_BASE64["png"]).encode("ascii"))


def _remove_track_revisions_from_settings_xml(xml: str) -> str:
    """Disable Word tracking in the Claude-safe working copy package.

    This does not edit the user's original document on disk. It prevents the
    reinserted DOCX package from carrying a track-revisions setting that would
    make placeholder operations appear as redlines in many Word builds.
    """
    try:
        root = _parse_xml_text(xml)
    except Exception:
        return xml
    for parent in root.iter():
        for child in list(parent):
            lname = child.tag.split('}', 1)[-1]
            if lname in {"trackRevisions", "doNotTrackMoves", "doNotTrackFormatting"}:
                parent.remove(child)
    return _serialize_xml(root)


def _is_legal_or_defined_term(value: str) -> bool:
    cleaned = _clean_alias(value)
    if not cleaned:
        return True
    if _is_legal_term(cleaned) or _is_role_alias(cleaned):
        return True
    # Title-cased legal phrase made solely of legal vocabulary, e.g.
    # "Ogólne Warunki", "Kodeks Cywilny", "Zarząd Klienta".
    words = [deaccent_role(w.strip(".,;:()[]{}")) for w in cleaned.split() if w.strip(".,;:()[]{}")]
    lex = {deaccent_role(x) for x in LEGAL_WORD_STOPLIST}
    if words and all(w in lex for w in words):
        return True
    return False


def _collect_all_text_nodes(root: ET.Element) -> Tuple[List[Tuple[ET.Element, int, int]], str]:
    """Collect textual XML element contents for metadata/custom parts.

    Metadata values live in normal element text nodes. We insert virtual
    separators between nodes in the plain-text view so detectors do not merge
    adjacent metadata fields such as creator + title into one false entity.
    The separators are not tied to XML nodes, so matches naturally stay within
    one metadata value.
    """
    nodes: List[Tuple[ET.Element, int, int]] = []
    parts: List[str] = []
    pos = 0
    sep = "\ue000"
    for el in root.iter():
        txt = el.text or ""
        if txt and txt.strip():
            if parts:
                parts.append(sep)
                pos += len(sep)
            start = pos
            pos += len(txt)
            nodes.append((el, start, pos))
            parts.append(txt)
    return nodes, "".join(parts)

def _extract_xml_part_text(xml: str, part_name: str = "") -> Tuple[ET.Element, List[Tuple[ET.Element, int, int]], str]:
    root = _parse_xml_text(xml)
    if METADATA_PART_RE.match(part_name or "") or (part_name or "").lower().startswith("customxml/"):
        nodes, plain = _collect_all_text_nodes(root)
    else:
        nodes, plain = _collect_text_nodes(root)
    return root, nodes, plain


def mask_ooxml_package_bytes(docx_bytes: bytes) -> Tuple[bytes, List[Replacement], Dict[str, Any]]:
    """Mask sensitive values across a .docx ZIP package.

    Covers main document, headers, footers, comments, footnotes, endnotes,
    glossary text, custom XML and metadata text nodes. Non-XML/binary parts are
    copied unchanged.
    """
    parsed: Dict[str, Tuple[ET.Element, List[Tuple[ET.Element, int, int]], str, str, int]] = {}
    separator = "\ue000CSM_PART_BOUNDARY\ue001"
    combined_parts: List[str] = []
    offset = 0
    processed_parts: List[str] = []
    skipped_parts: List[str] = []
    image_parts: List[str] = []
    redacted_image_parts: List[str] = []
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        names = zin.namelist()
        image_parts = [name for name in names if _part_is_image(name)]
        for name in names:
            if not DOCX_CONTENT_PART_RE.match(name):
                continue
            raw = zin.read(name)
            try:
                xml = raw.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    xml = raw.decode("utf-16")
                except UnicodeDecodeError:
                    skipped_parts.append(name)
                    continue
            try:
                root, nodes, visible_plain = _extract_xml_part_text(xml, name)
                attr_plain = _collect_sensitive_attributes_as_text(root)
                search_plain = visible_plain + (separator + attr_plain if attr_plain else "")
            except XmlSecurityError:
                raise
            except Exception:
                skipped_parts.append(name)
                continue
            parsed[name] = (root, nodes, visible_plain, search_plain, offset)
            combined_parts.append(search_plain)
            offset += len(search_plain) + len(separator)
            processed_parts.append(name)
        combined = separator.join(combined_parts)
        findings = collect_findings(combined)
        seen, counts = build_replacement_plan(findings, _existing_placeholders(combined))
        for name, (root, nodes, visible_plain, search_plain, part_offset) in parsed.items():
            part_start = part_offset
            visible_end = part_offset + len(visible_plain)
            part_findings = [
                Finding(f.category, f.value, f.start - part_start, f.end - part_start)
                for f in findings
                if f.start >= part_start and f.end <= visible_end
            ]
            for f in sorted(part_findings, key=lambda item: item.start, reverse=True):
                placeholder = seen[(f.category, f.value)]
                _replace_range_in_nodes(nodes, f.start, f.end, placeholder)
        out_buffer = io.BytesIO()
        with _open_docx_output_zip(out_buffer) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in parsed:
                    root = parsed[info.filename][0]
                    _apply_seen_to_sensitive_attributes(root, seen)
                    try:
                        _strip_unmapped_revision_author_attributes(root)
                    except Exception:
                        pass
                    data = _serialize_xml(root).encode("utf-8")
                elif SETTINGS_PART_RE.match(info.filename):
                    try:
                        xml_settings = data.decode("utf-8")
                        data = _remove_track_revisions_from_settings_xml(xml_settings).encode("utf-8")
                    except Exception:
                        pass
                elif _part_is_image(info.filename):
                    data = _redacted_image_bytes(info.filename)
                    redacted_image_parts.append(info.filename)
                zout.writestr(info, data)
    report = {
        "processed_parts": processed_parts,
        "skipped_parts": skipped_parts,
        "processed_parts_count": len(processed_parts),
        "skipped_parts_count": len(skipped_parts),
        "coverage": {
            "body": any(n == "word/document.xml" for n in processed_parts),
            "headers": sum(1 for n in processed_parts if re.match(r"word/header\d+\.xml$", n, re.I)),
            "footers": sum(1 for n in processed_parts if re.match(r"word/footer\d+\.xml$", n, re.I)),
            "comments": any(n == "word/comments.xml" for n in processed_parts),
            "footnotes": any(n == "word/footnotes.xml" for n in processed_parts),
            "endnotes": any(n == "word/endnotes.xml" for n in processed_parts),
            "metadata": sum(1 for n in processed_parts if METADATA_PART_RE.match(n)),
            "custom_xml": sum(1 for n in processed_parts if n.lower().startswith("customxml/")),
            "graphical_elements": {"images": len(image_parts), "redacted_images": len(redacted_image_parts), "shapes": 0, "text_boxes": 0},
        },
        "image_parts": image_parts[:100],
        "redacted_image_parts": redacted_image_parts[:100],
        "warnings": ([f"Obrazy w DOCX: wykryto {len(image_parts)} plik(i) graficzne; w kopii _CSM_anon zasłonięto je lokalnie, ponieważ CSM nie analizuje treści obrazów ani pikseli."] if image_parts else []),
    }
    return out_buffer.getvalue(), replacements_from_plan(seen, counts), report


def restore_ooxml_package_bytes(docx_bytes: bytes, replacements_payload: List[dict]) -> Tuple[bytes, Dict[str, Any]]:
    restored_reports: Dict[str, Any] = {}
    processed_parts: List[str] = []
    skipped_parts: List[str] = []
    total_restored = 0
    leftover_set: Set[str] = set()
    unknown_set: Set[str] = set()
    expected_set = {r.get("placeholder", "") for r in replacements_payload if r.get("placeholder")}
    found_set: Set[str] = set()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        out_buffer = io.BytesIO()
        with _open_docx_output_zip(out_buffer) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if DOCX_CONTENT_PART_RE.match(info.filename):
                    try:
                        xml = data.decode("utf-8")
                        restored_xml, report = restore_xml_part_with_report(xml, replacements_payload, info.filename)
                        data = restored_xml.encode("utf-8")
                        processed_parts.append(info.filename)
                        restored_reports[info.filename] = report
                        total_restored += int(report.get("restored_occurrences", 0) or 0)
                        missing_in_part = set(report.get("missing_placeholders", []) or [])
                        found_set.update(expected_set - missing_in_part)
                        for ph in report.get("unknown_placeholders", []) or []:
                            unknown_set.add(ph)
                        for ph in report.get("leftover_placeholders_after_restore", []) or []:
                            leftover_set.add(ph)
                    except XmlSecurityError:
                        raise
                    except Exception:
                        skipped_parts.append(info.filename)
                zout.writestr(info, data)
    missing_set = expected_set - found_set
    report = {
        "expected_total": len(expected_set),
        "found_total": len(found_set),
        "missing_placeholders": sorted(missing_set)[:50],
        "missing_total": len(missing_set),
        "unknown_placeholders": sorted(unknown_set)[:50],
        "unknown_total": len(unknown_set),
        "processed_parts": processed_parts,
        "skipped_parts": skipped_parts,
        "processed_parts_count": len(processed_parts),
        "skipped_parts_count": len(skipped_parts),
        "restored_occurrences": total_restored,
        "leftover_placeholders_after_restore": sorted(leftover_set)[:50],
        "leftover_total_after_restore": len(leftover_set),
        "all_found": len(missing_set) == 0,
        "parts": restored_reports,
    }
    return out_buffer.getvalue(), report


def docx_package_to_text(docx_bytes: bytes) -> str:
    values: List[str] = []
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        for name in zin.namelist():
            if DOCX_CONTENT_PART_RE.match(name):
                try:
                    xml = zin.read(name).decode("utf-8")
                    root, _nodes, plain = _extract_xml_part_text(xml, name)
                    if plain:
                        values.append(plain)
                except Exception:
                    continue
    return "\n\n".join(values)


def base64_to_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def bytes_to_base64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")
