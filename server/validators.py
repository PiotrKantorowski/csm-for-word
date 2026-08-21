from __future__ import annotations

import re

def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value)

def valid_pesel(value: str) -> bool:
    d = only_digits(value)
    if len(d) != 11:
        return False
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    checksum = (10 - sum(int(d[i]) * weights[i] for i in range(10)) % 10) % 10
    return checksum == int(d[10])

def valid_nip(value: str) -> bool:
    d = only_digits(value)
    if len(d) != 10:
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(d[i]) * weights[i] for i in range(9)) % 11
    return checksum != 10 and checksum == int(d[9])

def valid_regon(value: str) -> bool:
    d = only_digits(value)
    if len(d) == 9:
        weights = [8, 9, 2, 3, 4, 5, 6, 7]
        checksum = sum(int(d[i]) * weights[i] for i in range(8)) % 11
        if checksum == 10:
            checksum = 0
        return checksum == int(d[8])
    if len(d) == 14:
        weights = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]
        checksum = sum(int(d[i]) * weights[i] for i in range(13)) % 11
        if checksum == 10:
            checksum = 0
        return checksum == int(d[13])
    return False

def valid_pl_iban(value: str) -> bool:
    compact = re.sub(r"\s", "", value).upper()
    if not compact.startswith("PL"):
        compact = "PL" + compact
    if not re.fullmatch(r"PL\d{26}", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False

# Country -> exact IBAN length per ISO 13616 registry (subset covering the
# countries most likely in Polish cross-border matters; unknown countries fall
# back to a permissive length range and the mod-97 checksum).
IBAN_COUNTRY_LENGTHS = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15,
    "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27,
    "UA": 29,
}

def valid_iban(value: str) -> bool:
    """General ISO 13616 IBAN validation (any country), mod-97 checksum.

    Accepts optional spaces/dashes. Enforces the exact per-country length when
    the country is known, otherwise a permissive 15..34 range. This complements
    valid_pl_iban, which stays specific to the 26-digit Polish NRB.
    """
    compact = re.sub(r"[\s\-–—  ]", "", value or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", compact):
        return False
    expected = IBAN_COUNTRY_LENGTHS.get(compact[:2])
    if expected is not None:
        if len(compact) != expected:
            return False
    elif not (15 <= len(compact) <= 34):
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False

def _letter_value(ch: str) -> int:
    return ord(ch.upper()) - 55

def valid_idcard_pl(value: str) -> bool:
    s = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"[A-Z]{3}\d{6}", s):
        return False
    weights = [7, 3, 1, 0, 7, 3, 1, 7, 3]
    total = 0
    for i, ch in enumerate(s):
        if i == 3:
            continue
        total += (_letter_value(ch) if ch.isalpha() else int(ch)) * weights[i]
    return total % 10 == int(s[3])

def valid_passport_pl(value: str) -> bool:
    s = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{7}", s):
        return False
    weights = [7, 3, 0, 1, 7, 3, 1, 7, 3]
    total = 0
    for i, ch in enumerate(s):
        if i == 2:
            continue
        total += (_letter_value(ch) if ch.isalpha() else int(ch)) * weights[i]
    return total % 10 == int(s[2])
