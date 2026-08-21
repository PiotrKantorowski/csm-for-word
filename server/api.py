from __future__ import annotations

from typing import Dict, List, Any
from dataclasses import asdict
import json
import io
import os
import re
import traceback
import zipfile
import hashlib
import subprocess
import threading
import uuid
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import Request
from starlette.responses import JSONResponse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from lxml import etree

from redactor import make_replacements, make_replacements_with_controls, collect_findings_with_controls_report, save_map, load_map, sha256_text, mask_ooxml, restore_ooxml, restore_ooxml_with_report, mask_ooxml_parts, restore_ooxml_parts, find_residual_risks, find_quality_gate_warnings, collect_light_residual_review_findings, collect_bielik_deep_review_findings, normalize_review_mode, collect_ambiguous_person_warnings, collect_uncertain_review_candidates, ooxml_to_text, ooxml_parts_to_text, placeholder_report, mask_ooxml_package_bytes, restore_ooxml_package_bytes, docx_package_to_text, base64_to_bytes, bytes_to_base64, load_install_backup, latest_install_backup_id, list_install_backups, DocxXmlTooLargeError, _check_docx_xml_uncompressed_limit, MAPS_DIR, INSTALL_BACKUPS_DIR
import rules_store
from security import token_matches, get_api_token, cleanup_sensitive_files, audit_log, read_audit_tail, load_config, csm_dev_mode, csm_mode, BASE_DIR
from tc_engine import mask_docx_preserving_tc, restore_docx_preserving_tc, restore_docx_preserving_tc_with_original_context, restore_redacted_images_from_original, overlay_original_revision_contexts, build_placeholder_restore_overrides, ENGINE_VERSION as TC_ENGINE_VERSION
from word_revision_engine import build_custom_xml_payload, build_document_metadata, build_revision_job, revision_job_to_dict, validate_revision_job, select_restore_strategy, ENGINE_VERSION as REVISION_PLAN_ENGINE_VERSION, CSM_REVISION_MAP_NS
from revision_sidecar import SIDECAR_PROTOCOL_VERSION, SUPPORTED_ACTIONS, RevisionSidecarError, RevisionSidecarProtocolError, RevisionSidecarUnavailable, build_sidecar_request, invoke_sidecar, sidecar_status_dict
from version import APP_VERSION

try:
    from bielik_detector import (
        bielik_enabled as _bielik_enabled_fn,
        _api_url as _bielik_api_url,
        _provider as _bielik_provider,
    )
except Exception:  # optional dependency — must never break core CSM
    def _bielik_enabled_fn() -> bool: return False
    def _bielik_api_url() -> str: return ""
    def _bielik_provider() -> str: return "ollama"

_bielik_cache: Dict[str, Any] = {"result": None, "ts": 0.0}


def _bielik_reachable() -> bool:
    if not _bielik_enabled_fn():
        return False
    now = time.time()
    cached_result = _bielik_cache.get("result")
    cached_ts = float(_bielik_cache.get("ts") or 0.0)
    # Asymmetric TTL: once confirmed reachable keep the result for 2 min so the
    # UI indicator stays green during normal Ollama use.  When unreachable, retry
    # every 10 s so the panel recovers quickly after Ollama starts up.
    ttl = 120.0 if cached_result else 10.0
    if cached_result is not None and (now - cached_ts) < ttl:
        return bool(cached_result)
    try:
        import urllib.request as _urlreq
        base = re.sub(r"/api/chat$", "", _bielik_api_url())
        base = re.sub(r"/v1/chat/completions$", "", base)
        ping = base + ("/api/tags" if _bielik_provider() == "ollama" else "/v1/models")
        with _urlreq.urlopen(_urlreq.Request(ping), timeout=2.0) as r:
            result = r.status == 200
    except Exception:
        result = False
    _bielik_cache["result"] = result
    _bielik_cache["ts"] = now
    return result


def _normalize_review_mode_or_400(mode: str | None) -> str:
    try:
        return normalize_review_mode(mode)
    except ValueError as exc:
        raise _http_error(400, str(exc), public_detail="Nieobsługiwany tryb kontroli anonimizacji.") from exc


def _review_warning_summary(findings: List[Any], label_prefix: str) -> List[str]:
    counts: Dict[str, int] = {}
    for finding in findings or []:
        category = str(getattr(finding, "category", "UNKNOWN") or "UNKNOWN")
        counts[category] = counts.get(category, 0) + 1
    return [
        f"{label_prefix} ({category}): {count} potencjalne wystąpienie/a"
        for category, count in sorted(counts.items())
    ]


def _run_review_mode(masked_text: str, replacements: List[Any], review_mode: str | None) -> tuple[List[str], Dict[str, Any]]:
    mode = _normalize_review_mode_or_400(review_mode)
    status: Dict[str, Any] = {
        "review_mode": mode,
        "bielik_available": bool(_bielik_enabled_fn()),
        "bielik_reachable": False,
        "bielik_used": False,
        "bielik_findings_count": 0,
        "bielik_elapsed_ms": 0,
        "bielik_timeout": False,
        "residual_risks": [],
    }
    warnings: List[str] = []
    if mode in {"light", "bielik"}:
        residual = collect_light_residual_review_findings(masked_text, replacements, limit=30)
        status["residual_risks"] = residual
        warnings.extend(residual)
    if mode != "bielik":
        return warnings, status

    if not status["bielik_available"]:
        warnings.append("Bielik niedostępny — wykonano standardową anonimizację i lekką kontrolę.")
        return warnings, status

    reachable = _bielik_reachable()
    status["bielik_reachable"] = reachable
    if not reachable:
        warnings.append("Bielik niedostępny — wykonano standardową anonimizację i lekką kontrolę.")
        return warnings, status

    started = time.monotonic()
    status["bielik_used"] = True
    try:
        findings = collect_bielik_deep_review_findings(masked_text, replacements)
    except TimeoutError:
        findings = []
        status["bielik_timeout"] = True
        warnings.append("Bielik nie zakończył sprawdzania w wyznaczonym czasie. Dokument został zanonimizowany standardowo. Sprawdź go ręcznie przed wysłaniem do AI.")
    except Exception:
        findings = []
        warnings.append("Bielik niedostępny — wykonano standardową anonimizację i lekką kontrolę.")
    finally:
        status["bielik_elapsed_ms"] = int((time.monotonic() - started) * 1000)
    status["bielik_findings_count"] = len(findings)
    warnings.extend(_review_warning_summary(findings, "Bielik: możliwe ryzyko"))
    return warnings, status


def _review_response_fields(review_status: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "review_mode": review_status.get("review_mode", "standard"),
        "bielik_available": bool(review_status.get("bielik_available", False)),
        "bielik_reachable": bool(review_status.get("bielik_reachable", False)),
        "bielik_used": bool(review_status.get("bielik_used", False)),
        "bielik_findings_count": int(review_status.get("bielik_findings_count", 0) or 0),
        "bielik_elapsed_ms": int(review_status.get("bielik_elapsed_ms", 0) or 0),
        "bielik_timeout": bool(review_status.get("bielik_timeout", False)),
    }


DOCX_ZIP_COMPRESSLEVEL_FAST = 1


def _open_docx_output_zip(target) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=DOCX_ZIP_COMPRESSLEVEL_FAST)
    except TypeError:  # pragma: no cover
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED)


MAX_TEXT_BYTES_DEFAULT = 2_000_000
MAX_DOCX_XML_BYTES_DEFAULT = 50_000_000
REVISION_MARKER_RE = re.compile(
    r"<(?:(?:[A-Za-z_][\w.-]*):)?(?:ins|del|moveFrom|moveTo|moveFromRangeStart|moveFromRangeEnd|moveToRangeStart|moveToRangeEnd|"
    r"pPrChange|rPrChange|tblPrChange|trPrChange|tcPrChange|sectPrChange|numberingChange|"
    r"customXmlInsRangeStart|customXmlDelRangeStart|customXmlMoveFromRangeStart|customXmlMoveToRangeStart)\b"
)



def max_text_bytes() -> int:
    try:
        return int(load_config().get("max_text_bytes", MAX_TEXT_BYTES_DEFAULT) or MAX_TEXT_BYTES_DEFAULT)
    except Exception:
        return MAX_TEXT_BYTES_DEFAULT


def max_docx_xml_bytes() -> int:
    try:
        return int(load_config().get("max_docx_xml_bytes", MAX_DOCX_XML_BYTES_DEFAULT) or MAX_DOCX_XML_BYTES_DEFAULT)
    except Exception:
        return MAX_DOCX_XML_BYTES_DEFAULT


_CSM_SAFE_FILENAME_RE = re.compile(r"_CSM_(?:anon|jawny)\.docx$", re.I)


def _sanitize_error_detail(message: str) -> str:
    msg = str(message or "")
    msg = re.sub(r"[A-Za-z]:[/\\][^\n'\"]*", "<path-redacted>", msg)
    msg = re.sub(r"(?<![A-Za-z0-9_])/(?:[^\s'\"]+)", "<path-redacted>", msg)
    # Preserve CSM-standard document-kind suffixes (_CSM_anon.docx, _CSM_jawny.docx) so
    # actionable error messages remain readable after sanitisation.
    msg = re.sub(
        r"\b[\w .()\-ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+\.[A-Za-z0-9]{1,6}\b",
        lambda m: m.group(0) if _CSM_SAFE_FILENAME_RE.search(m.group(0)) else "<file-redacted>",
        msg,
    )
    msg = re.sub(r"\b\d{11}\b", "<number-redacted>", msg)
    msg = re.sub(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ]+)?\b", "<id-redacted>", msg)
    return msg


def _http_error(status: int, detail: str, *, public_detail: str | None = None) -> HTTPException:
    if csm_dev_mode():
        safe = _sanitize_error_detail(detail)
    else:
        safe = public_detail if public_detail is not None else _sanitize_error_detail(detail)
    return HTTPException(status_code=status, detail=safe)


def validate_text_size(text: str) -> None:
    limit = max_text_bytes()
    if len(text.encode("utf-8")) > limit:
        detail = "Tekst przekracza limit 2 MB." if limit == 2_000_000 else f"Tekst przekracza limit {limit} bajtów."
        raise _http_error(413, detail, public_detail=detail)


def docx_revision_files(docx_base64: str) -> List[str]:
    try:
        data = base64_to_bytes(docx_base64)
    except Exception as exc:
        raise _http_error(400, f"Nieprawidłowy DOCX/base64: {exc}", public_detail="Nieprawidłowy plik Word")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total_xml = sum(int(info.file_size or 0) for info in zf.infolist() if info.filename.lower().endswith(".xml"))
            limit = max_docx_xml_bytes()
            if total_xml > limit:
                raise _http_error(413, f"Łączny rozmiar XML w DOCX przekracza limit {limit} bajtów.", public_detail=f"Łączny rozmiar XML w DOCX przekracza limit {limit} bajtów.")
            hits: List[str] = []
            for name in zf.namelist():
                lower = name.lower()
                if not lower.endswith(".xml"):
                    continue
                try:
                    raw = zf.read(name)
                except Exception:
                    continue
                if len(raw) > 20_000_000:
                    continue
                try:
                    xml = raw.decode("utf-8")
                except UnicodeDecodeError:
                    xml = raw.decode("utf-8", errors="ignore")
                if REVISION_MARKER_RE.search(xml):
                    hits.append(name)
            return hits
    except zipfile.BadZipFile:
        raise _http_error(400, "Przekazany plik nie jest prawidłowym DOCX/ZIP.", public_detail="Przekazany plik nie jest prawidłowym DOCX/ZIP.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_sensitive_files()
    yield

app = FastAPI(title="CSM Word Local API", version=APP_VERSION, lifespan=lifespan)


def json_dumps_safe(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def category_counts(replacements) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in replacements:
        counts[r.category] = counts.get(r.category, 0) + int(getattr(r, "count", 1) or 1)
    return counts


DOCUMENT_PROFILES: Dict[str, Dict[str, Any]] = {
    "auto": {
        "label": "Auto / domyślny",
        "priority_categories": [],
        "description": "Profil domyślny. CSM stosuje pełny zestaw bazowych detektorów i raportuje standardowe ryzyka.",
    },
    "pleadings": {
        "label": "Pisma procesowe",
        "priority_categories": ["PERSON", "PERSON_ALIAS", "COURT", "SYGNATURA", "ADDRESS", "PESEL", "IDCARD_PL", "PASSPORT_PL", "PHONE", "EMAIL"],
        "description": "Profil dla pism procesowych. Raport mocniej eksponuje strony, uczestników, sądy, sygnatury, adresy i numery identyfikacyjne.",
    },
    "contracts": {
        "label": "Umowy",
        "priority_categories": ["CONTRACTOR", "COMPANY", "COMPANY_ALIAS", "NIP", "REGON", "KRS", "CEIDG_ID", "BANK_ACCOUNT", "IBAN", "ADDRESS", "PERSON"],
        "description": "Profil dla umów. Raport mocniej eksponuje kontrahentów, spółki, identyfikatory gospodarcze, rachunki bankowe, adresy i reprezentantów.",
    },
}

PROFILE_ALIASES: Dict[str, str] = {
    "process": "pleadings",
    "procesowe": "pleadings",
    "pismo_procesowe": "pleadings",
    "pisma_procesowe": "pleadings",
    "pleading": "pleadings",
    "pleadings": "pleadings",
    "contract": "contracts",
    "contracts": "contracts",
    "umowa": "contracts",
    "umowy": "contracts",
}


def _normalize_document_profile(profile: str | None) -> str:
    key = (profile or "auto").strip().lower().replace(" ", "_").replace("-", "_")
    key = PROFILE_ALIASES.get(key, key)
    return key if key in DOCUMENT_PROFILES else "auto"


def _profile_report(profile: str | None, counts: Dict[str, int]) -> Dict[str, Any]:
    normalized = _normalize_document_profile(profile)
    spec = DOCUMENT_PROFILES[normalized]
    priority = list(spec.get("priority_categories") or [])
    found = {cat: int(counts.get(cat) or 0) for cat in priority if int(counts.get(cat) or 0) > 0}
    missing = [cat for cat in priority if int(counts.get(cat) or 0) == 0]
    return {
        "id": normalized,
        "label": spec.get("label", normalized),
        "description": spec.get("description", ""),
        "priority_categories": priority,
        "priority_found": found,
        "priority_missing": missing,
        "mode": "audit_boost" if normalized != "auto" else "standard",
        "note": "Profil nie wyłącza detektorów bazowych. Służy do mocniejszego raportowania kategorii typowych dla danego dokumentu.",
    }


def _coverage_review_items(coverage: Dict[str, Any] | None, processed_parts: List[str] | None = None, skipped_parts: List[str] | None = None) -> List[str]:
    coverage = coverage or {}
    processed_parts = processed_parts or []
    skipped_parts = skipped_parts or []
    items: List[str] = []
    if not coverage.get("body"):
        items.append("Nie potwierdzono przetworzenia głównej treści dokumentu.")
    if skipped_parts:
        items.append(f"Pominięto {len(skipped_parts)} części DOCX przy analizie — sprawdź dokument ręcznie.")
    optional = []
    if coverage.get("comments"):
        optional.append("komentarze")
    if coverage.get("footnotes"):
        optional.append("przypisy dolne")
    if coverage.get("endnotes"):
        optional.append("przypisy końcowe")
    if int(coverage.get("headers") or 0):
        optional.append("nagłówki")
    if int(coverage.get("footers") or 0):
        optional.append("stopki")
    if int(coverage.get("metadata") or 0):
        optional.append("metadane")
    graphics = coverage.get("graphical_elements") or {}
    try:
        images = int(graphics.get("images") or 0)
        redacted_images = int(graphics.get("redacted_images") or 0)
    except Exception:
        images = 0
        redacted_images = 0
    if images:
        if redacted_images:
            items.append(f"Obrazy: wykryto {images}; w kopii _CSM_anon zasłonięto {redacted_images}, bo CSM nie analizuje treści obrazów ani pikseli.")
        else:
            items.append(f"Obrazy: wykryto {images}; wymagają ręcznej kontroli, jeżeli redakcja obrazów jest wyłączona.")
    if optional:
        items.append("Przetworzono także: " + ", ".join(optional) + ".")
    else:
        items.append("Nie wykryto osobnych komentarzy/przypisów/nagłówków/stopek/metadanych do raportu albo dokument ich nie zawiera.")
    return items


def _build_report_control_sections(counts: Dict[str, int], coverage: Dict[str, Any] | None) -> Dict[str, Any]:
    """Structured, non-disclosing report sections for user QA.

    These sections are intentionally based on categories/counts only. They never
    echo raw values such as bank account numbers or text extracted from images.
    """
    coverage = coverage or {}
    graphics = coverage.get("graphical_elements") or {}
    bank_count = int(counts.get("BANK_ACCOUNT") or counts.get("IBAN") or 0)
    image_count = int(graphics.get("images") or 0)
    redacted_images = int(graphics.get("redacted_images") or 0)
    return {
        "bank_accounts": {
            "title": "Rachunki bankowe",
            "found": bank_count,
            "category": "BANK_ACCOUNT",
            "status": "masked" if bank_count else "not_detected",
            "note": "Pełne numery rachunków nie są ujawniane w raporcie." if bank_count else "Nie wykryto rachunków bankowych w przetworzonym zakresie.",
        },
        "graphical_elements": {
            "title": "Obrazy i elementy nietekstowe",
            "images_found": image_count,
            "images_redacted": redacted_images,
            "status": "redacted" if redacted_images else ("review" if image_count else "not_detected"),
            "note": "Obrazy w kopii _CSM_anon są zasłaniane lokalnie; CSM nie analizuje treści obrazów ani pikseli." if image_count else "Nie wykryto obrazów w DOCX.",
        },
        "manual_review": {
            "title": "Elementy wymagające kontroli ręcznej",
            "status": "review" if image_count and redacted_images < image_count else "standard",
            "note": "Przejrzyj dokument _CSM_anon.docx przed użyciem AI, zwłaszcza gdy dokument zawiera skany, pieczęcie, podpisy lub nietypowe pola DOCX.",
        },
    }


def _build_anonymization_report(replacements, package_report: Dict[str, Any] | None = None, warnings: List[str] | None = None, masked_docx_bytes: bytes | None = None, document_profile: str | None = None, review_status: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """User-facing non-disclosing anonymization quality report for v0.6.1.

    The report intentionally avoids echoing suspected raw values. It gives counts,
    categories, coverage and risk classes so the user can decide whether to review
    the DOCX before sending it to an AI tool.
    """
    package_report = package_report or {}
    warnings = list(warnings or [])
    counts = category_counts(replacements)
    total_occurrences = 0
    for r in replacements:
        try:
            total_occurrences += int(getattr(r, "count", 1) or 1)
        except Exception:
            total_occurrences += 1
    review_status = review_status or {}
    review_mode = str(review_status.get("review_mode") or ("light" if masked_docx_bytes is not None else "standard"))
    residual_risks: List[str] = list(review_status.get("residual_risks") or [])
    if not residual_risks and masked_docx_bytes is not None and review_mode in {"light", "bielik"}:
        try:
            residual_risks = find_quality_gate_warnings(docx_package_to_text(masked_docx_bytes), replacements, limit=30)
        except Exception:
            residual_risks = ["Nie udało się wykonać skanu ryzyk pozostałych w zanonimizowanym DOCX."]
    coverage = package_report.get("coverage", {}) or {}
    control_sections = _build_report_control_sections(counts, coverage)
    profile_info = _profile_report(document_profile, counts)
    review_items = _coverage_review_items(coverage, package_report.get("processed_parts", []), package_report.get("skipped_parts", []))
    bank_accounts = control_sections.get("bank_accounts", {})
    if int(bank_accounts.get("found") or 0):
        review_items.insert(0, f"Rachunki bankowe: wykryto {int(bank_accounts.get('found') or 0)} wystąpień; pełne numery nie są pokazywane w raporcie.")
    graphics = control_sections.get("graphical_elements", {})
    if profile_info.get("id") != "auto":
        found_summary = profile_info.get("priority_found") or {}
        review_items.insert(0, f"Profil dokumentu: {profile_info.get('label')} — kategorie priorytetowe wykryte: {len(found_summary)}; brakujące kategorie pokazano w raporcie do kontroli, bez obniżania bezpieczeństwa bazowego.")
    if int(graphics.get("images_found") or 0):
        review_items.insert(1 if int(bank_accounts.get("found") or 0) else 0, f"Obrazy i elementy nietekstowe: wykryto {int(graphics.get('images_found') or 0)} obrazów; zasłonięto {int(graphics.get('images_redacted') or 0)} w kopii _CSM_anon.")
    if review_status:
        if review_status.get("bielik_used"):
            review_items.append(f"Bielik: sprawdzono, wykryto {int(review_status.get('bielik_findings_count') or 0)} potencjalne ryzyka.")
        else:
            review_items.append("Bielik: nie użyto.")
    severity = "ok"
    if warnings or residual_risks or package_report.get("skipped_parts"):
        severity = "review"
    if not counts:
        severity = "empty"
    top_categories = [
        {"category": cat, "count": int(val)}
        for cat, val in sorted(counts.items(), key=lambda item: (-int(item[1]), item[0]))[:20]
    ]
    return {
        "schema_version": "1.0",
        "severity": severity,
        "entities_unique": len(replacements),
        "entities_occurrences": total_occurrences,
        "category_counts": counts,
        "top_categories": top_categories,
        "warnings": warnings[:50],
        "residual_risks": residual_risks[:30],
        "manual_review_items": review_items[:50],
        "review_mode": review_mode,
        "bielik": _review_response_fields(review_status) if review_status else {},
        "control_sections": control_sections,
        "document_profile": profile_info,
        "coverage": coverage,
        "processed_parts_count": len(package_report.get("processed_parts", []) or []),
        "skipped_parts_count": len(package_report.get("skipped_parts", []) or []),
        "revisions_summary": package_report.get("revisions_summary", {}),
        "recommendation": "Przejrzyj raport i dokument _CSM_anon.docx przed uruchomieniem Claude, szczególnie gdy severity=review.",
    }


def _build_restore_quality_report(restore_report: Dict[str, Any] | None = None, warnings: List[str] | None = None, input_change_report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    restore_report = restore_report or {}
    warnings = list(warnings or [])
    input_change_report = input_change_report or {}
    leftover = int(restore_report.get("leftover_total_after_restore") or 0)
    restored_occurrences = int(restore_report.get("restored_occurrences") or 0)
    severity = "ok"
    if leftover > 0 or warnings:
        severity = "review"
    if restored_occurrences == 0:
        severity = "empty" if not leftover else "review"
    review_items: List[str] = []
    if leftover:
        review_items.append(f"Po przywróceniu pozostało {leftover} placeholderów — dokument wymaga kontroli.")
    if input_change_report.get("changed_from_prepare") is False:
        review_items.append("Plik _CSM_anon nie różnił się tekstowo od kopii bazowej po anonimizacji.")
    if input_change_report.get("changed_from_prepare") is True:
        review_items.append("Wykryto zmiany w pliku _CSM_anon względem kopii bazowej po anonimizacji.")
    return {
        "schema_version": "1.0",
        "severity": severity,
        "restored_occurrences": restored_occurrences,
        "leftover_total_after_restore": leftover,
        "leftover_placeholders_after_restore": restore_report.get("leftover_placeholders_after_restore", [])[:50],
        "warnings": warnings[:50],
        "manual_review_items": review_items[:50],
        "input_change_report": input_change_report,
        "recommendation": "Sprawdź wersję _CSM_jawny.docx, zwłaszcza gdy pozostały placeholdery albo CSM zgłosił ostrzeżenia.",
    }


def _allowed_cors_origins() -> List[str]:
    origins = ["https://localhost:3000", "https://127.0.0.1:3000"]
    raw = os.environ.get("CSM_ALLOWED_ORIGINS", "")
    for item in raw.split(","):
        origin = item.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "X-CSM-Token"],
)



def _requires_local_api_token(request: Request) -> bool:
    """Return True for local API routes that expose or mutate sensitive CSM state."""
    method = request.method.upper()
    path = request.url.path.rstrip("/")
    if method in {"POST", "PUT", "DELETE"}:
        return True
    # The sidecar status can reveal local execution configuration. Keep it behind
    # the same local token boundary as sidecar execution endpoints.
    if method == "GET" and path == "/v2/revision/sidecar/status":
        return True
    # Service management streaming endpoint: requires token even for GET.
    if method == "GET" and path == "/service/diagnose":
        return True
    # Audit summary leaks session map_id values and document fingerprints.
    if method == "GET" and path == "/audit_summary":
        return True
    return False


@app.middleware("http")
async def require_local_api_token(request: Request, call_next):
    if _requires_local_api_token(request):
        provided = request.headers.get("X-CSM-Token")
        if not token_matches(provided):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid CSM local API token"})
    return await call_next(request)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    audit_log("error", mode="api", status="failed")
    if csm_dev_mode():
        detail = _sanitize_error_detail("".join(traceback.format_exception_only(type(exc), exc)).strip())
    else:
        detail = "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


class MaskRequest(BaseModel):
    text: str
    original_docx_base64: str | None = None
    review_mode: str = "standard"


class DocxRevisionReportRequest(BaseModel):
    docx_base64: str


class MaskResponse(BaseModel):
    masked_text: str
    map_id: str
    entities_count: int
    version: str
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    category_counts: Dict[str, int] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class ScanResponse(BaseModel):
    entities_count: int
    version: str
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    category_counts: Dict[str, int] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class OoxmlMaskRequest(BaseModel):
    ooxml: str
    review_mode: str = "standard"


class OoxmlMaskResponse(BaseModel):
    ooxml: str
    map_id: str
    entities_count: int
    version: str
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    category_counts: Dict[str, int] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False




class OoxmlPartsMaskRequest(BaseModel):
    parts: Dict[str, str]
    original_docx_base64: str | None = None
    original_text: str | None = None
    review_mode: str = "standard"


class OoxmlPartsMaskResponse(BaseModel):
    parts: Dict[str, str]
    map_id: str
    entities_count: int
    version: str
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    category_counts: Dict[str, int] = {}
    processed_parts: List[str] = []
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class OoxmlPartsRestoreRequest(BaseModel):
    map_id: str
    parts: Dict[str, str]


class PlaceholderReportRequest(BaseModel):
    map_id: str
    text: str | None = None
    ooxml: str | None = None
    parts: Dict[str, str] | None = None


class RestoreRequest(BaseModel):
    map_id: str


class OoxmlRestoreRequest(BaseModel):
    map_id: str
    ooxml: str


class OriginalSnapshotRequest(BaseModel):
    map_id: str


class LatestBackupRequest(BaseModel):
    map_id: str | None = None


class DocxPackageMaskRequest(BaseModel):
    docx_base64: str
    review_mode: str = "standard"


class DocxPackageMaskResponse(BaseModel):
    docx_base64: str
    map_id: str
    entities_count: int
    version: str
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    category_counts: Dict[str, int] = {}
    package_report: Dict = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class DocxPackageRestoreRequest(BaseModel):
    map_id: str
    docx_base64: str


class DocxV3MaskRequest(BaseModel):
    docx_base64: str
    mode: str = "preserve"
    review_mode: str = "standard"


class DocxV3MaskResponse(BaseModel):
    version: str
    engine_version: str
    masked_docx_base64: str
    map_id: str
    category_counts: Dict[str, int] = {}
    entities_count: int
    revisions_summary: Dict[str, Any] = {}
    coverage: Dict[str, Any] = {}
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class DocxV3RestoreRequest(BaseModel):
    docx_base64: str
    map_id: str


class DocxV3RestoreResponse(BaseModel):
    version: str
    engine_version: str
    restored_docx_base64: str
    restore_report: Dict[str, Any] = {}
    warnings: List[str] = []
    restore_quality_report: Dict[str, Any] = {}

class DocxV4PrepareRequest(BaseModel):
    docx_base64: str
    filename: str | None = None
    mode: str = "preserve"
    review_mode: str = "standard"


class DocxV4PrepareResponse(BaseModel):
    version: str
    engine_version: str
    anon_docx_base64: str
    map_id: str
    suggested_filename: str
    category_counts: Dict[str, int] = {}
    entities_count: int
    coverage: Dict[str, Any] = {}
    revisions_summary: Dict[str, Any] = {}
    negotiation_report: Dict[str, Any] = {}
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False


class DocxV4RestoreRequest(BaseModel):
    docx_base64: str
    map_id: str
    filename: str | None = None


class DocxV4RestoreResponse(BaseModel):
    version: str
    engine_version: str
    restored_docx_base64: str
    map_id: str
    suggested_filename: str
    restore_report: Dict[str, Any] = {}
    negotiation_report: Dict[str, Any] = {}
    warnings: List[str] = []
    restore_quality_report: Dict[str, Any] = {}


class DocxV4ValidateRoundtripRequest(BaseModel):
    original_docx_base64: str
    restored_docx_base64: str


class DocxV4DiffReportRequest(BaseModel):
    left_docx_base64: str
    right_docx_base64: str


class AnonymizationControls(BaseModel):
    always: List[Dict[str, str] | str] = []
    # A "never" item may be a plain phrase or {"value": ..., "force": true}.
    # force is required to suppress checksum-validated findings (PESEL, NIP...).
    never: List[Dict[str, Any] | str] = []
    category_overrides: Dict[str, str] = {}
    category_changes: List[Dict[str, str]] = []
    merge_placeholders: List[Dict[str, str]] = []


class DocumentProfileRequest(BaseModel):
    document_profile: str = "auto"



def _summarize_anonymization_controls(controls: AnonymizationControls | Dict[str, Any] | None) -> Dict[str, int]:
    if not controls:
        return {"always": 0, "never": 0, "category_overrides": 0, "category_changes": 0, "merge_placeholders": 0, "total": 0}
    data = controls if isinstance(controls, dict) else controls.model_dump()
    summary = {
        "always": len(data.get("always") or []),
        "never": len(data.get("never") or []),
        "category_overrides": len(data.get("category_overrides") or {}),
        "category_changes": len(data.get("category_changes") or []),
        "merge_placeholders": len(data.get("merge_placeholders") or []),
    }
    summary["total"] = sum(summary.values())
    return summary


def _effective_controls_dict(
    controls: AnonymizationControls | None,
    client_id: str | None,
    use_saved_rules: bool,
) -> Dict[str, Any] | None:
    """Session controls merged with locally saved global/client rules."""
    session_dict = controls.model_dump() if controls else None
    if not use_saved_rules:
        return session_dict
    try:
        merged = rules_store.merge_controls(session_dict, client_id)
    except Exception:
        # A broken saved-rules file must not block masking; session rules still apply.
        return session_dict
    if session_dict and session_dict.get("category_changes"):
        # Legacy list form used by older panel payloads; the engine accepts both.
        merged["category_changes"] = session_dict["category_changes"]
    if not any(merged.get(k) for k in ("always", "never", "category_overrides", "category_changes", "merge_placeholders")):
        return session_dict
    return merged

class MapPreviewRequest(BaseModel):
    map_id: str
    document_profile: str = "auto"


class MapPreviewResponse(BaseModel):
    version: str
    map_id: str
    replacements: List[Dict[str, Any]]
    category_counts: Dict[str, int] = {}
    privacy_notice: str = ""
    controls_supported: List[str] = []
    preview_generated_at: str = ""
    document_profiles: List[Dict[str, Any]] = []
    selected_profile: Dict[str, Any] = {}


class DocxV4CurrentPrepareRequest(BaseModel):
    docx_base64: str
    filename: str | None = None
    mode: str = "preserve"
    review_mode: str = "standard"
    open_file: bool = True
    controls: AnonymizationControls | None = None
    # Locally saved rules (global + this client) are merged into controls.
    client_id: str | None = None
    use_saved_rules: bool = True
    document_profile: str = "auto"
    # Full path of the source file on the user's disk (from Office.context.document.url).
    # Stored in manifest.json so restore can write back to the original location.
    word_source_path: str | None = None
    # Filename fallback used when Office.js cannot expose a local full path.
    # The backend only uses it when exactly one open Word document has this name.
    word_source_name: str | None = None


class DocxV4CurrentPrepareResponse(BaseModel):
    version: str
    engine_version: str
    map_id: str
    session_id: str
    suggested_filename: str
    original_path: str
    anon_path: str
    opened_file: bool = False
    open_error: str | None = None
    category_counts: Dict[str, int] = {}
    entities_count: int
    coverage: Dict[str, Any] = {}
    revisions_summary: Dict[str, Any] = {}
    negotiation_report: Dict[str, Any] = {}
    warnings: List[str] = []
    anonymization_report: Dict[str, Any] = {}
    report_prepare_path: str | None = None
    controls_applied: bool = False
    controls_summary: Dict[str, int] = {}
    document_profile: str = "auto"
    word_close_report: Dict[str, Any] = {}
    review_mode: str = "standard"
    bielik_available: bool = False
    bielik_reachable: bool = False
    bielik_used: bool = False
    bielik_findings_count: int = 0
    bielik_elapsed_ms: int = 0
    bielik_timeout: bool = False
    uncertain_review_candidates: List[Dict[str, Any]] = []
    # Per-rule accountability from the engine (matches, suppressions, dead rules).
    controls_effects: Dict[str, Any] = {}
    saved_rules: Dict[str, int] = {}


class DocxV4RemaskSessionRequest(BaseModel):
    map_id: str
    session_id: str | None = None
    filename: str | None = None
    open_file: bool = True
    controls: AnonymizationControls | None = None
    document_profile: str = "auto"
    review_mode: str = "standard"
    # Locally saved rules (global + this client) are merged into controls.
    client_id: str | None = None
    use_saved_rules: bool = True


class DocxV4CurrentRestoreRequest(BaseModel):
    docx_base64: str
    filename: str | None = None
    open_file: bool = True
    # Optional fallback from the taskpane/session. This is needed when Word
    # strips or does not expose the customXml CSM metadata from the active file,
    # while the document still visibly contains CSM placeholders.
    map_id: str | None = None
    session_id: str | None = None
    # Full Windows path of the anon copy that is currently open in Word.
    # When provided the server closes it automatically after the restored
    # original has had time to open (PowerShell COM, fire-and-forget).
    word_anon_path: str | None = None
    # Filename fallback used when Office.js cannot expose a local full path.
    word_anon_name: str | None = None


class DocxV4PathRestoreRequest(BaseModel):
    anon_path: str | None = None
    map_id: str | None = None
    session_id: str | None = None
    word_anon_path: str | None = None
    word_anon_name: str | None = None
    open_file: bool = True
    # Used by the UI when restore falls back from a non-anon active document.
    # It prevents producing a misleading jawny file from the untouched baseline
    # *_CSM_anon.docx when user edits were made in another Word window and were
    # not saved or not accessible to the add-in.
    require_changes: bool = False


class DocxV4CurrentRestoreResponse(BaseModel):
    version: str
    engine_version: str
    map_id: str
    session_id: str
    suggested_filename: str
    anon_path: str
    restored_path: str
    opened_file: bool = False
    open_error: str | None = None
    restore_report: Dict[str, Any] = {}
    negotiation_report: Dict[str, Any] = {}
    input_changed_from_prepare: bool | None = None
    input_change_report: Dict[str, Any] = {}
    warnings: List[str] = []
    restore_quality_report: Dict[str, Any] = {}
    report_restore_path: str | None = None
    word_close_report: Dict[str, Any] = {}


class DocxV4CurrentStatusRequest(BaseModel):
    docx_base64: str
    # Optional map hint lets CSM recognize an anonymized document even when
    # Word/SaveAs stripped CSM customXml metadata but the document still contains
    # placeholders belonging to the active map.
    map_id: str | None = None


class RevisionPlanRequest(BaseModel):
    map_id: str | None = None
    mode: str = "restore"
    replacements: List[Dict[str, Any]] = []
    anchors: List[Dict[str, Any]] = []
    keep_tracking: bool = True
    author: str = "CSM"


class RevisionPlanResponse(BaseModel):
    version: str
    engine_version: str
    namespace: str
    map_id: str
    mode: str
    operations: List[Dict[str, Any]] = []
    anchors: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    validation: Dict[str, Any] = {}
    strategy: Dict[str, Any] = {}
    document_metadata: Dict[str, Any] = {}
    custom_xml_payload: str = ""


class RevisionSidecarStatusResponse(BaseModel):
    version: str
    engine_version: str
    protocol_version: str
    sidecar_status: Dict[str, Any] = {}
    supported_actions: List[str] = []


class RevisionSidecarCompareRequest(BaseModel):
    original_docx_base64: str
    revised_docx_base64: str
    author: str = "CSM"
    execute: bool = False


class RevisionSidecarNormalizeRequest(BaseModel):
    docx_base64: str
    author: str = "CSM"
    execute: bool = False


class RevisionSidecarTrackedReplaceRequest(BaseModel):
    docx_base64: str
    operations: List[Dict[str, Any]] = []
    author: str = "CSM"
    map_id: str | None = None
    execute: bool = False


class RevisionSidecarActionResponse(BaseModel):
    version: str
    engine_version: str
    protocol_version: str
    action: str
    sidecar_status: Dict[str, Any] = {}
    request_contract: Dict[str, Any] = {}
    execution: Dict[str, Any] = {}
    result: Dict[str, Any] = {}


class DocxV4OpenPathRequest(BaseModel):
    path: str


def _safe_filename_stem(filename: str | None, default: str = "dokument") -> str:
    raw = (filename or default).replace("\\", "/").rsplit("/", 1)[-1]
    raw = re.sub(r"(?i)\.docx$", "", raw).strip() or default
    raw = re.sub(r"[^A-Za-z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ _.-]+", "_", raw).strip(" ._") or default
    return raw[:120]


def _docx_suggested_filename(filename: str | None, suffix: str) -> str:
    return f"{_safe_filename_stem(filename)}_{suffix}.docx"


def _canonical_xml_bytes(data: bytes) -> bytes:
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False, huge_tree=False)
        root = etree.fromstring(data, parser=parser)
        return etree.tostring(root, method="c14n", exclusive=False, with_comments=True)
    except Exception:
        return data


def _canonical_docx_manifest(docx_bytes: bytes) -> Dict[str, str]:
    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/"):
                continue
            raw = zf.read(name)
            if name.lower().endswith((".xml", ".rels")):
                raw = _canonical_xml_bytes(raw)
            manifest[name] = hashlib.sha256(raw).hexdigest()
    return manifest


def _canonical_docx_hash(docx_bytes: bytes) -> str:
    manifest = _canonical_docx_manifest(docx_bytes)
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _docx_diff_summary(left_bytes: bytes, right_bytes: bytes) -> Dict[str, Any]:
    left = _canonical_docx_manifest(left_bytes)
    right = _canonical_docx_manifest(right_bytes)
    left_keys = set(left)
    right_keys = set(right)
    changed = sorted(k for k in left_keys & right_keys if left[k] != right[k])
    return {
        "identical": left == right,
        "left_hash": hashlib.sha256(json.dumps(left, sort_keys=True).encode("utf-8")).hexdigest(),
        "right_hash": hashlib.sha256(json.dumps(right, sort_keys=True).encode("utf-8")).hexdigest(),
        "changed_parts_count": len(changed),
        "added_parts_count": len(right_keys - left_keys),
        "removed_parts_count": len(left_keys - right_keys),
        "changed_parts": changed[:100],
        "added_parts": sorted(right_keys - left_keys)[:100],
        "removed_parts": sorted(left_keys - right_keys)[:100],
    }


# Visible-content hashes are used only to detect whether a *_CSM_anon.docx used
# for restore actually contains user/Claude edits. They intentionally ignore
# docProps and customXml because Word may rewrite metadata without changing the
# legal/business text.
_DOCX_VISIBLE_TEXT_PART_RE = re.compile(
    r"^word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments|glossary/document)\.xml$",
    re.IGNORECASE,
)


def _docx_visible_text_for_change_detection(docx_bytes: bytes) -> str:
    values: List[str] = []
    text_local_names = {"t", "delText", "instrText"}
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
            xml_total = sum((info.file_size or 0) for info in zf.infolist() if _DOCX_VISIBLE_TEXT_PART_RE.match(info.filename or ""))
            if xml_total > max_docx_xml_bytes():
                return ""
            for name in zf.namelist():
                if not _DOCX_VISIBLE_TEXT_PART_RE.match(name or ""):
                    continue
                try:
                    root = etree.fromstring(zf.read(name), parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=True))
                except Exception:
                    continue
                parts: List[str] = []
                for node in root.iter():
                    try:
                        local = etree.QName(node).localname
                    except Exception:
                        continue
                    if local in text_local_names and node.text:
                        parts.append(str(node.text))
                if parts:
                    values.append("".join(parts))
    except Exception:
        return ""
    return "\n\n".join(values)


def _docx_visible_text_hash(docx_bytes: bytes) -> str:
    normalized = re.sub(r"\s+", " ", _docx_visible_text_for_change_detection(docx_bytes) or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_session_manifest_best_effort(session_dir: Path) -> Dict[str, Any]:
    try:
        path = session_dir / "manifest.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def _v4_negotiation_report(original_bytes: bytes | None = None, anon_bytes: bytes | None = None, restored_bytes: bytes | None = None, package_report: Dict[str, Any] | None = None, restore_report: Dict[str, Any] | None = None) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "mode": "file_docx_negotiation",
        "mutates_active_word_document": False,
        "range_api_used": False,
        "package_scope": "full_docx_ooxml_package",
    }
    if original_bytes is not None:
        report["original_canonical_hash"] = _canonical_docx_hash(original_bytes)
    if anon_bytes is not None:
        report["anon_canonical_hash"] = _canonical_docx_hash(anon_bytes)
    if restored_bytes is not None:
        report["restored_canonical_hash"] = _canonical_docx_hash(restored_bytes)
    if original_bytes is not None and restored_bytes is not None:
        report["roundtrip"] = _docx_diff_summary(original_bytes, restored_bytes)
    if package_report:
        report["coverage"] = package_report.get("coverage", {})
        report["processed_parts"] = package_report.get("processed_parts", [])[:100]
        report["skipped_parts"] = package_report.get("skipped_parts", [])[:100]
        report["revisions_summary"] = package_report.get("revisions_summary", {})
    if restore_report:
        report["restore"] = {
            "restored_occurrences": restore_report.get("restored_occurrences", 0),
            "leftover_total_after_restore": restore_report.get("leftover_total_after_restore", 0),
            "missing_total": restore_report.get("missing_total", 0),
            "unknown_total": restore_report.get("unknown_total", 0),
            "processed_parts_count": restore_report.get("processed_parts_count", 0),
            "skipped_parts_count": restore_report.get("skipped_parts_count", 0),
        }
    return report



CSM_METADATA_NS = "https://skills.kancelariakantorowski.pl/csm/metadata/1"
CSM_CUSTOMXML_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
SESSIONS_DIR = BASE_DIR / "sessions"


class CsmFileLockedError(RuntimeError):
    """Raised when a DOCX needed by CSM is temporarily locked by Word/Windows."""


class CsmStaleAnonInputError(RuntimeError):
    """Raised when a fallback restore would use the unchanged baseline anon DOCX."""


def _is_file_lock_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    winerror = getattr(exc, "winerror", None)
    if winerror in {5, 32, 33}:  # access denied / sharing violation / lock violation
        return True
    errno_value = getattr(exc, "errno", None)
    return errno_value in {13}


def _sleep_retry(attempt: int, base_delay: float = 0.15) -> None:
    time.sleep(min(1.0, base_delay * max(1, attempt)))


def _sessions_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def _make_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _zipinfo_copy(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    zi.compress_type = zipfile.ZIP_DEFLATED if info.compress_type == zipfile.ZIP_STORED else info.compress_type
    zi.comment = info.comment
    zi.extra = info.extra
    zi.internal_attr = info.internal_attr
    zi.external_attr = info.external_attr
    zi.create_system = info.create_system
    return zi


def _write_zip_entry(zout: zipfile.ZipFile, info: zipfile.ZipInfo, data: bytes) -> None:
    zout.writestr(_zipinfo_copy(info), data)


def _is_csm_metadata_xml(data: bytes) -> bool:
    prefix = data[:2048]
    return b"CSM_METADATA" in prefix or CSM_METADATA_NS.encode("utf-8") in prefix


def _find_csm_metadata_items(docx_bytes: bytes) -> List[str]:
    """Return all customXml parts that belong to CSM metadata items.

    Includes both the item XML itself (customXml/itemN.xml) and its
    corresponding properties file (customXml/itemPropsN.xml) when present,
    so that _docx_upsert_csm_metadata / _docx_remove_csm_metadata leave no
    orphaned props files that could trigger Word's recovery dialog.
    """
    found: List[str] = []
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
        nameset = set(zf.namelist())
        for name in list(nameset):
            m = re.match(r"(customXml)/item(\d+)\.xml$", name, re.I)
            if not m:
                continue
            try:
                raw = zf.read(name)
            except Exception:
                continue
            if _is_csm_metadata_xml(raw):
                found.append(name)
                # Also mark the companion properties file for removal so Word
                # does not encounter an orphaned itemProps without its item.
                props_name = f"{m.group(1)}/itemProps{m.group(2)}.xml"
                if props_name in nameset:
                    found.append(props_name)
    return found


def _metadata_xml(metadata: Dict[str, Any]) -> bytes:
    root = etree.Element("{%s}metadata" % CSM_METADATA_NS, nsmap={"csm": CSM_METADATA_NS})
    root.set("marker", "CSM_METADATA")
    for key, value in metadata.items():
        child = etree.SubElement(root, "{%s}%s" % (CSM_METADATA_NS, re.sub(r"[^A-Za-z0-9_.-]", "_", str(key))))
        child.text = "" if value is None else str(value)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def _parse_metadata_xml(data: bytes) -> Dict[str, str]:
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except Exception:
        return {}
    if root.tag != "{%s}metadata" % CSM_METADATA_NS and root.get("marker") != "CSM_METADATA":
        return {}
    out: Dict[str, str] = {}
    for child in root:
        key = str(child.tag).rsplit("}", 1)[-1]
        out[key] = child.text or ""
    return out


def _extract_csm_metadata(docx_bytes: bytes) -> Dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
        for name in zf.namelist():
            if not re.match(r"customXml/item\d+\.xml$", name, re.I):
                continue
            try:
                raw = zf.read(name)
            except Exception:
                continue
            if _is_csm_metadata_xml(raw):
                parsed = _parse_metadata_xml(raw)
                if parsed:
                    return parsed
    return {}


def _update_root_rels(data: bytes | None, *, remove_targets: set[str], add_target: str | None = None) -> bytes:
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    if data:
        try:
            root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
        except Exception:
            root = etree.Element("Relationships", nsmap={None: rel_ns})
    else:
        root = etree.Element("Relationships", nsmap={None: rel_ns})
    for rel in list(root):
        target = str(rel.get("Target") or "")
        if target in remove_targets:
            root.remove(rel)
    if add_target:
        existing = {str(rel.get("Id") or "") for rel in root}
        i = 1
        while f"rIdCSM{i}" in existing:
            i += 1
        rel = etree.SubElement(root, "{%s}Relationship" % rel_ns)
        rel.set("Id", f"rIdCSM{i}")
        rel.set("Type", CSM_CUSTOMXML_REL_TYPE)
        rel.set("Target", add_target)
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def _docx_upsert_csm_metadata(docx_bytes: bytes, metadata: Dict[str, Any]) -> bytes:
    remove_items = set(_find_csm_metadata_items(docx_bytes))
    remove_rels = {name for name in remove_items}
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        nums = []
        for name in zin.namelist():
            m = re.match(r"customXml/item(\d+)\.xml$", name, re.I)
            if m:
                nums.append(int(m.group(1)))
        new_name = f"customXml/item{(max(nums) + 1) if nums else 1}.xml"
        out = io.BytesIO()
        rels_written = False
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                if info.filename in remove_items:
                    continue
                data = zin.read(info.filename)
                if info.filename == "_rels/.rels":
                    data = _update_root_rels(data, remove_targets=remove_rels, add_target=new_name)
                    rels_written = True
                _write_zip_entry(zout, info, data)
            if not rels_written:
                zi = zipfile.ZipInfo("_rels/.rels")
                zi.compress_type = zipfile.ZIP_DEFLATED
                zout.writestr(zi, _update_root_rels(None, remove_targets=remove_rels, add_target=new_name))
            zi = zipfile.ZipInfo(new_name)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, _metadata_xml(metadata))
        return out.getvalue()


def _docx_remove_csm_metadata(docx_bytes: bytes) -> bytes:
    remove_items = set(_find_csm_metadata_items(docx_bytes))
    if not remove_items:
        return docx_bytes
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        out = io.BytesIO()
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                if info.filename in remove_items:
                    continue
                data = zin.read(info.filename)
                if info.filename == "_rels/.rels":
                    data = _update_root_rels(data, remove_targets=remove_items, add_target=None)
                _write_zip_entry(zout, info, data)
        return out.getvalue()


def _session_docx_path(session_dir: Path, filename: str, default: str = "dokument") -> Path:
    safe = _safe_filename_stem(filename, default) + ".docx"
    return session_dir / safe


def _unique_docx_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix or ".docx"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for i in range(1, 1000):
        candidate = path.with_name(f"{stem}_{timestamp}_{i:02d}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{timestamp}_{uuid.uuid4().hex[:8]}{suffix}")


def _write_session_file(session_dir: Path, filename: str, data: bytes, *, avoid_overwrite: bool = False, attempts: int = 6) -> Path:
    """Write a DOCX into a CSM session without clobbering open Word files.

    On Windows, Word and antivirus/indexing software can briefly deny access to
    a just-created or already-open DOCX. For restore outputs, overwriting is not
    necessary and is unsafe. This helper therefore tries the requested path only
    when explicitly allowed, then keeps generating fresh names and retrying.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    path = _session_docx_path(session_dir, filename)
    last_error: Exception | None = None
    tried: set[Path] = set()
    max_attempts = max(1, int(attempts or 1))
    for attempt in range(max_attempts):
        if attempt == 0 and not avoid_overwrite:
            candidate = path
        else:
            candidate = _unique_docx_path(path)
            if candidate in tried:
                candidate = path.with_name(f"{path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}{path.suffix or '.docx'}")
        tried.add(candidate)
        try:
            candidate.write_bytes(data)
            return candidate
        except OSError as exc:
            last_error = exc
            if not _is_file_lock_error(exc):
                raise
            _sleep_retry(attempt + 1)
            continue
    if last_error:
        raise last_error
    raise PermissionError(str(path))


def _read_bytes_with_retry(path: Path, *, attempts: int = 12, base_delay: float = 0.2) -> bytes:
    """Read a DOCX that Word may still be saving/opening.

    The restore path uses this as a fallback when Office.js cannot export the
    active anonymized document. A short retry window absorbs transient Word
    locks; a persistent lock becomes a clear 423-style user message.
    """
    if os.environ.get("CSM_FAST_LOCK_RETRY") == "1":
        attempts = min(int(attempts or 1), 3)
        base_delay = 0.01
    last_error: Exception | None = None
    for attempt in range(max(1, int(attempts or 1))):
        try:
            return path.read_bytes()
        except OSError as exc:
            last_error = exc
            if not _is_file_lock_error(exc):
                raise
            _sleep_retry(attempt + 1, base_delay=base_delay)
    raise CsmFileLockedError(
        "Plik *_CSM_anon.docx jest teraz zablokowany przez Worda lub Windows. "
        "Zapisz dokument roboczy w Wordzie (Ctrl+S), odczekaj kilka sekund i kliknij ponownie „Utwórz wersję jawną”. "
        "Jeżeli komunikat wraca, zamknij tylko plik *_CSM_anon.docx i użyj przycisku ponownie."
    ) from last_error



def _powershell_exe() -> str | None:
    """Return the Windows PowerShell executable when available.

    The COM bridge intentionally uses Windows PowerShell 5.x because it can talk
    to the desktop Word COM object without adding pywin32 as a dependency.
    """
    if os.name != "nt":
        return None
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    candidate = Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.exists():
        return str(candidate)
    return "powershell.exe"


def _read_open_word_document_copy(path: Path, *, timeout_seconds: int = 10) -> tuple[bytes | None, str | None]:
    """Try to read the in-memory Word document matching *path* via COM.

    This is the key fallback for the common UX case where the CSM task pane is
    still attached to the original document, but Word has the *_CSM_anon.docx
    open in another window. Reading the file from disk can miss unsaved edits;
    SaveCopyAs captures the open document state without changing the user's file.
    """
    if os.name != "nt" or os.environ.get("CSM_DISABLE_WORD_COM_COPY") == "1":
        return None, "Word COM live copy is not available on this platform or is disabled."
    ps = _powershell_exe()
    if not ps:
        return None, "PowerShell is not available."
    source = str(path.resolve())
    # SaveCopyAs is executed by the running Word process. Put the temporary
    # DOCX copy next to the source *_CSM_anon.docx instead of in the backend's
    # temp directory: if CSM was started elevated and Word runs as the normal
    # user, Word may not be able to write into the elevated user's temp folder.
    # The session directory is the path Word already opened from and is the
    # safest cross-elevation target. The PowerShell helper script itself can
    # stay in the backend temp directory.
    tmp_dir = Path(tempfile.gettempdir()) / "csm-word-live-copy"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = path.parent / f".csm_live_{uuid.uuid4().hex}.docx"
    script = tmp_dir / f"csm_savecopy_{uuid.uuid4().hex}.ps1"
    script_text = r'''
param(
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$Target
)
$ErrorActionPreference = 'Stop'
$sourceFull = [System.IO.Path]::GetFullPath($Source)
$targetFull = [System.IO.Path]::GetFullPath($Target)
$word = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application')
$found = $false
foreach ($doc in @($word.Documents)) {
  $full = ''
  try { $full = [System.IO.Path]::GetFullPath([string]$doc.FullName) } catch { $full = '' }
  if ([string]::Equals($full, $sourceFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    $doc.SaveCopyAs($targetFull)
    $found = $true
    break
  }
}
if (-not $found) {
  throw 'CSM_ANON_DOCUMENT_NOT_OPEN_IN_WORD'
}
Write-Output 'OK'
'''
    try:
        script.write_text(script_text, encoding="utf-8")
        proc = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), source, str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(3, int(timeout_seconds or 10)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "Word COM SaveCopyAs failed").strip()
            return None, _sanitize_error_detail(detail)
        if not target.exists():
            return None, "Word COM SaveCopyAs nie utworzył kopii dokumentu."
        return target.read_bytes(), None
    except subprocess.TimeoutExpired:
        return None, "Word COM SaveCopyAs przekroczył limit czasu."
    except Exception as exc:
        return None, _sanitize_error_detail(str(exc))
    finally:
        for cleanup_path in (script, target):
            try:
                if cleanup_path.exists():
                    cleanup_path.unlink()
            except Exception:
                pass


def _read_best_available_anon_docx(path: Path) -> tuple[bytes, str, str | None]:
    """Read the edited anonymized DOCX using the safest available source.

    Priority:
    1. On Windows, ask the running Word instance to SaveCopyAs the open document
       matching path. This captures unsaved edits and avoids file-lock surprises.
    2. Fall back to the session file on disk with retry.
    """
    live_bytes, live_error = _read_open_word_document_copy(path)
    if live_bytes is not None:
        return live_bytes, "word-com-savecopyas", None
    disk_bytes = _read_bytes_with_retry(path)
    return disk_bytes, "saved-session-file", live_error


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_json_best_effort(path: Path, data: Dict[str, Any], warnings: List[str]) -> None:
    try:
        _write_json(path, data)
    except OSError as exc:
        warnings.append(f"Nie udało się zapisać raportu technicznego CSM: {_sanitize_error_detail(str(exc))}")


def _audit_log_best_effort(event: str, warnings: List[str], **kwargs: Any) -> None:
    try:
        audit_log(event, **kwargs)
    except OSError as exc:
        warnings.append(f"Nie udało się dopisać audytu technicznego CSM: {_sanitize_error_detail(str(exc))}")



def _path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
        return child_resolved == parent_resolved or parent_resolved in child_resolved.parents
    except Exception:
        return False


def _is_csm_working_docx_path(path: Path) -> bool:
    """Return True for CSM-owned working/output DOCX files, not user originals."""
    name = path.name.lower()
    if re.search(r"_csm_(?:anon|jawny)(?:_[0-9]{8}-[0-9]{6}_\d+)?\.docx$", name, re.I):
        return True
    if re.search(r"_oryginal\.docx$", name, re.I):
        return True
    if _path_is_inside(path, _sessions_dir()):
        return True
    return False


def _safe_original_docx_target(raw_path: str | None) -> tuple[Path | None, str | None]:
    """Validate a client-supplied original path before restore overwrites it.

    The frontend captures Office.context.document.url before the focus switch, but
    WebView/Office can still return stale or empty paths. Never treat CSM session
    files or *_CSM_anon/_CSM_jawny outputs as the user's original target.
    """
    value = (raw_path or "").strip()
    if not value:
        return None, "brak zapamiętanej ścieżki oryginału"
    try:
        candidate = Path(value).expanduser().resolve()
    except Exception as exc:
        return None, f"nieprawidłowa ścieżka oryginału: {_sanitize_error_detail(str(exc))}"
    if candidate.suffix.lower() != ".docx":
        return None, "zapamiętana ścieżka oryginału nie wskazuje pliku .docx"
    if _is_csm_working_docx_path(candidate):
        return None, "zapamiętana ścieżka wskazuje plik roboczy CSM, nie oryginał użytkownika"
    return candidate, None

def _resolve_session_docx_path(raw_path: str | None, *, session_id: str | None = None, map_id: str | None = None) -> Path:
    """Resolve a DOCX path that must live under CSM sessions.

    The Word task pane can remain bound to the original document even after CSM
    opens *_CSM_anon.docx in Word. In that case Office.js exports the wrong
    active document. Path-based restore intentionally reads the last saved
    anonymized session file from disk instead of trusting the task pane context.
    """
    base = _sessions_dir().resolve()
    candidate: Path | None = None
    if raw_path:
        candidate = Path(raw_path).expanduser().resolve()
    else:
        sid = re.sub(r"[^a-zA-Z0-9_.-]", "", (session_id or map_id or "").strip())
        if not sid:
            raise ValueError("Brak ścieżki do pliku *_CSM_anon.docx i brak identyfikatora sesji CSM.")
        session_dir = (base / sid).resolve()
        if base not in session_dir.parents and session_dir != base:
            raise ValueError("Identyfikator sesji CSM zawiera niedozwolone znaki.")
        manifest_path = session_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            anon_filename = manifest.get("anon_filename") or ""
            if anon_filename:
                candidate = (session_dir / anon_filename).resolve()
        if candidate is None:
            matches = sorted(session_dir.glob("*_CSM_anon.docx"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            if matches:
                candidate = matches[0].resolve()
    if candidate is None:
        raise ValueError("Nie znaleziono ostatniego pliku *_CSM_anon.docx w sesji CSM.")
    if base not in candidate.parents and candidate != base:
        raise ValueError("Plik do przywrócenia musi znajdować się w folderze sesji CSM.")
    if not candidate.exists():
        raise FileNotFoundError(str(candidate))
    if candidate.suffix.lower() != ".docx" or not re.search(r"_CSM_anon\.docx$", candidate.name, re.I):
        raise ValueError("Wskaż zapisany plik z końcówką *_CSM_anon.docx.")
    return candidate


def _restore_v4_docx_bytes(raw: bytes, *, filename: str | None = None, map_id: str | None = None, session_id: str | None = None, open_file: bool = True, mode: str = "docx_v4_current_restore", source_path: Path | None = None, source_mode: str | None = None, source_warning: str | None = None, require_changes: bool = False, word_anon_path: str | None = None, word_anon_name: str | None = None) -> DocxV4CurrentRestoreResponse:
    metadata = _extract_csm_metadata(raw)
    metadata_map_id = metadata.get("map_id") or ""
    requested_map_id = (map_id or "").strip()
    resolved_map_id = metadata_map_id or requested_map_id
    resolved_session_id = metadata.get("session_id") or (session_id or "").strip() or resolved_map_id
    if not resolved_map_id:
        raise ValueError(
            "Nie rozpoznaję dokumentu jako kopii CSM. "
            "Użyj pliku *_CSM_anon.docx utworzonego przez CSM albo wskaż go w trybie awaryjnym."
        )
    payload = _load_map_any(resolved_map_id)
    metadata_missing = not bool(metadata_map_id)
    if metadata_missing and not _docx_contains_any_map_placeholder(raw, payload.get("replacements", [])):
        raise ValueError(
            "Dokument nie zawiera metadanych CSM ani placeholderów z ostatniej mapy. "
            "Najpewniej użyto oryginału zamiast kopii *_CSM_anon.docx."
        )
    original_bytes = None
    try:
        original_docx_base64 = payload.get("original_docx_base64")
        if original_docx_base64:
            original_bytes = base64_to_bytes(original_docx_base64)
    except Exception:
        original_bytes = None

    restored_bytes, restore_report = restore_docx_preserving_tc_with_original_context(
        raw,
        payload["replacements"],
        original_bytes,
        placeholder_restore_overrides=payload.get("placeholder_restore_overrides"),
    )
    restored_bytes = _docx_remove_csm_metadata(restored_bytes)
    restored_bytes, revision_overlay_report = overlay_original_revision_contexts(restored_bytes, original_bytes, payload["replacements"])
    if revision_overlay_report.get("available_fragments") or revision_overlay_report.get("reapplied_fragments"):
        restore_report["revision_context_overlay"] = revision_overlay_report
    restored_bytes, image_restore_report = restore_redacted_images_from_original(restored_bytes, original_bytes)
    if any(int(v or 0) for v in image_restore_report.values()):
        restore_report["image_restore_report"] = image_restore_report
    restore_report.setdefault("leftover_total_after_restore", 0)
    restore_report.setdefault("leftover_placeholders_after_restore", [])

    warnings: List[str] = []
    if source_warning:
        warnings.append(f"Nie udało się pobrać otwartej kopii Word przez COM; użyto pliku z dysku. Szczegóły: {_sanitize_error_detail(source_warning)}")
    try:
        anon_content_hash = metadata.get("anon_content_hash") or ""
        if anon_content_hash:
            current_content_hash = _canonical_docx_hash(_docx_remove_csm_metadata(raw))
            if current_content_hash == anon_content_hash:
                warnings.append(
                    "CSM nie wykrył zmian w roboczym pliku *_CSM_anon.docx względem kopii utworzonej przy anonimizacji. "
                    "Jeżeli pracowałeś nad dokumentem w Wordzie, zapisz plik (Ctrl+S) albo użyj otwartego okna *_CSM_anon.docx z panelem CSM, a następnie ponów przywracanie."
                )
    except Exception:
        pass

    session_dir = _sessions_dir() / (resolved_session_id or resolved_map_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    session_manifest = _load_session_manifest_best_effort(session_dir)
    baseline_text_hash = str(metadata.get("anon_text_hash") or session_manifest.get("anon_text_hash") or "")
    input_text_hash = _docx_visible_text_hash(raw)
    input_changed_from_prepare = None
    if baseline_text_hash:
        input_changed_from_prepare = input_text_hash != baseline_text_hash
    input_change_report = {
        "baseline_anon_text_hash": baseline_text_hash,
        "input_text_hash": input_text_hash,
        "changed_from_prepare": input_changed_from_prepare,
        "require_changes": bool(require_changes),
        "mode": mode,
    }
    if require_changes and input_changed_from_prepare is False:
        raise CsmStaleAnonInputError(
            "CSM widzi zapisany plik *_CSM_anon.docx w stanie bazowym, bez zmian względem kopii utworzonej po anonimizacji. "
            "Najpewniej kliknięto „Utwórz wersję jawną” w panelu przy oryginalnym dokumencie albo zmiany w pliku *_CSM_anon.docx nie zostały zapisane. "
            "Przełącz się do dokumentu *_CSM_anon.docx i kliknij restore z panelu w tym dokumencie, albo zapisz plik *_CSM_anon.docx (Ctrl+S) i wskaż go ręcznie w sekcji awaryjnej."
        )

    stem = _safe_filename_stem(filename or metadata.get("restored_filename") or metadata.get("anon_filename") or "dokument", "dokument")
    if stem.endswith("_CSM_anon"):
        stem = stem[:-9]
    restored_filename = metadata.get("restored_filename") or f"{stem}_CSM_jawny.docx"
    anon_filename = metadata.get("anon_filename") or f"{stem}_CSM_anon.docx"

    resolved_source_path = source_path.resolve() if source_path else None
    expected_anon_path = _session_docx_path(session_dir, anon_filename).resolve()
    if resolved_source_path and resolved_source_path == expected_anon_path:
        # Session restore reads the saved *_CSM_anon.docx that Word may still have
        # open. Rewriting that same file on Windows raises PermissionError
        # ([Errno 13]) because Word can hold an exclusive/deny-write handle. The
        # anonymized working file should remain untouched; only create a jawny copy.
        anon_path = resolved_source_path
    else:
        # Save incoming bytes as the session anon copy.  Overwrite any existing
        # copy — numbered backups (_CSM_anon_*_01.docx) are confusing and waste space.
        # If the file is locked by Word we fall back to using the existing path as-is.
        try:
            anon_path = _write_session_file(session_dir, anon_filename, raw, avoid_overwrite=False)
        except (PermissionError, OSError):
            anon_path = _session_docx_path(session_dir, anon_filename)

    # --- Write restored bytes back to the original Word file if path is known ---
    # The backup already exists: the original was saved to session_dir/<stem>_oryginal.docx
    # at prepare time. We try to overwrite the original; fall back to _CSM_jawny.docx
    # in the session folder if the file is locked (open in Word) or path is unavailable.
    word_source_path_str = session_manifest.get("word_source_path") or metadata.get("word_source_path") or ""
    restore_target, restore_target_warning = _safe_original_docx_target(word_source_path_str)
    restore_to_original = False
    if restore_target_warning and word_source_path_str:
        warnings.append(f"CSM nie użył zapamiętanej ścieżki oryginału: {restore_target_warning}. Zapisano wersję jawną w folderze sesji.")

    if restore_target:
        # Proactively close the original before writing, not only after a
        # PermissionError. Some Word/Windows configurations allow a byte write
        # while Word still shows an already-open stale document; reopening that
        # path may then focus the stale window instead of loading the restored file.
        if os.name == "nt":
            closed, close_error = _close_word_document(str(restore_target), delay_sec=0.0, save_mode="save_then_close", timeout_seconds=12)
            if close_error and "CSM_NOT_FOUND" not in close_error:
                warnings.append(f"Nie udało się potwierdzić zamknięcia oryginału w Wordzie przed zapisem: {close_error}")
            if closed:
                time.sleep(0.35)
        try:
            restore_target.write_bytes(restored_bytes)
            restored_path = restore_target
            restore_to_original = True
        except PermissionError:
            # Word has the original open. Close it synchronously through COM and
            # only then retry writing. The helper saves/marks the document clean
            # first, which prevents Word from leaving an AutoRecovered copy.
            closed, close_error = _close_word_document(str(restore_target), delay_sec=0.0, save_mode="save_then_close", timeout_seconds=12)
            if not closed and close_error:
                warnings.append(f"Nie udało się automatycznie zamknąć oryginału w Wordzie przed restore: {close_error}")
            time.sleep(0.75)
            try:
                restore_target.write_bytes(restored_bytes)
                restored_path = restore_target
                restore_to_original = True
            except (PermissionError, OSError) as exc2:
                warnings.append(
                    f"Nie udało się nadpisać oryginalnego pliku ({restore_target.name}) — plik nadal jest zablokowany po próbie automatycznego zamknięcia. "
                    f"Zapisano wersję jawną w folderze sesji CSM jako {restored_filename}. "
                    "Zamknij oryginał ręcznie w Wordzie i skopiuj ten plik na jego miejsce."
                )
                restored_path = _write_session_file(session_dir, restored_filename, restored_bytes, avoid_overwrite=True)
        except OSError as exc:
            warnings.append(
                f"Nie udało się zapisać wersji jawnej w oryginalnej lokalizacji ({restore_target}): "
                f"{_sanitize_error_detail(str(exc))}. Zapisano w folderze sesji CSM."
            )
            restored_path = _write_session_file(session_dir, restored_filename, restored_bytes, avoid_overwrite=True)
    else:
        # No original path known — save as _CSM_jawny.docx in session folder (old behaviour).
        restored_path = _write_session_file(session_dir, restored_filename, restored_bytes, avoid_overwrite=True)

    restored_filename = restored_path.name
    negotiation_report = _v4_negotiation_report(original_bytes, raw, restored_bytes, None, restore_report)
    negotiation_report["input_change_detection"] = input_change_report
    negotiation_report["restore_to_original"] = restore_to_original
    if source_mode:
        negotiation_report["restore_source"] = source_mode
    if input_changed_from_prepare is False and not require_changes:
        warnings.append("CSM utworzył wersję jawną z pliku _CSM_anon, w którym nie wykryto zmian tekstowych względem kopii bazowej po anonimizacji.")
    if restore_report.get("leftover_total_after_restore"):
        warnings.append("Po restore w pliku pozostały placeholdery; dokument wymaga kontroli.")
    restore_quality_report = _build_restore_quality_report(restore_report, warnings, input_change_report)
    report_restore_path = session_dir / "report_restore.json"
    _write_json_best_effort(report_restore_path, {"version": APP_VERSION, "session_id": resolved_session_id or resolved_map_id, "map_id": payload["map_id"], "negotiation_report": negotiation_report, "restore_report": restore_report, "restore_quality_report": restore_quality_report, "warnings": warnings}, warnings)
    opened, open_error = _open_file_path(restored_path, enabled=bool(open_file))
    # Close the anon copy in Word after the restored original has had time to open.
    # The content has already been transferred — wdDoNotSaveChanges (0) is safe.
    word_close_report = {}
    if word_anon_path or word_anon_name:
        word_close_report = _schedule_word_close_after_open((word_anon_path or "").strip(), doc_name=(word_anon_name or "").strip(), save_mode="discard_without_recovery")
    # Session clean-up: after restoring to the original location the working
    # files are no longer needed.  Keep only *_oryginal.docx* as the pre-anonymisation
    # evidence copy.  The clean-up fires after Word has had time to close the anon file.
    if restore_to_original:
        _cleanup_session_working_files_async(session_dir, anon_filename, delay_sec=8.0)
    _audit_log_best_effort("restore", warnings, map_id=payload["map_id"], mode=mode, restore_report=restore_report)
    return DocxV4CurrentRestoreResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        map_id=payload["map_id"],
        session_id=resolved_session_id or resolved_map_id,
        suggested_filename=restored_filename,
        anon_path=str(anon_path),
        restored_path=str(restored_path),
        opened_file=opened,
        open_error=open_error,
        restore_report=restore_report,
        negotiation_report=negotiation_report,
        input_changed_from_prepare=input_changed_from_prepare,
        input_change_report=input_change_report,
        warnings=warnings,
        restore_quality_report=restore_quality_report,
        report_restore_path=str(report_restore_path),
        word_close_report=word_close_report,
    )


def _close_word_document(doc_path: str, *, doc_name: str | None = None, delay_sec: float = 0.0, save_mode: str = "save_then_close", timeout_seconds: int = 18) -> tuple[bool, str | None]:
    """Close a specific Word document through the running desktop Word COM instance.

    The first implementation matched Word documents by an exact FullName only and
    ran once in a swallowed background thread. In real Word sessions that is too
    fragile: Office.js can return a file:// URL, Word can expose a normalized path,
    OneDrive/UNC paths can differ, and Word may still be opening the new document.

    This helper therefore matches in two stages:
    1. exact normalized FullName/path match;
    2. safe filename fallback, but only when exactly one open document has that name.

    save_mode:
    - "save_then_close": save the Word document first, mark it clean, then close.
    - "discard_without_recovery": mark the document as saved and close without writing.
    - "discard": close without saving and without changing Word's Saved flag.
    """
    requested_path = (doc_path or "").strip()
    requested_name = (doc_name or "").strip()
    if not requested_path and not requested_name:
        return False, "empty document path/name"
    if os.name != "nt" or os.environ.get("CSM_DISABLE_WORD_COM_CLOSE") == "1":
        return False, "Word COM close is not available on this platform or is disabled."
    ps = _powershell_exe()
    if not ps:
        return False, "PowerShell is not available."
    mode = (save_mode or "save_then_close").strip().lower()
    if mode not in {"save_then_close", "discard_without_recovery", "discard"}:
        mode = "save_then_close"
    tmp_dir = Path(tempfile.gettempdir()) / "csm-word-com"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    script = tmp_dir / f"csm_close_{uuid.uuid4().hex}.ps1"
    script_text = r'''
param(
  [string]$Source = '',
  [string]$SourceName = '',
  [Parameter(Mandatory=$true)][string]$SaveMode,
  [double]$DelaySec = 0,
  [int]$TimeoutSec = 18
)
$ErrorActionPreference = 'Stop'
if ($DelaySec -gt 0) { Start-Sleep -Milliseconds ([int]([double]$DelaySec * 1000)) }

function Normalize-CsmPath([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
  $v = ([string]$Value).Trim().Trim('"')
  if ($v -match '^file://') {
    try {
      $uri = [System.Uri]$v
      if ($uri.IsUnc) { $v = $uri.LocalPath } else { $v = $uri.LocalPath }
    } catch {}
  }
  $v = $v -replace '/', '\'
  try { return [System.IO.Path]::GetFullPath($v) } catch { return $v }
}

function Csm-DocPath($Doc) {
  try {
    $full = [string]$Doc.FullName
    if (-not [string]::IsNullOrWhiteSpace($full)) { return Normalize-CsmPath $full }
  } catch {}
  try {
    $path = [string]$Doc.Path
    $name = [string]$Doc.Name
    if (-not [string]::IsNullOrWhiteSpace($path) -and -not [string]::IsNullOrWhiteSpace($name)) {
      return Normalize-CsmPath ([System.IO.Path]::Combine($path, $name))
    }
  } catch {}
  return ''
}

function Csm-CloseDoc($Doc, [string]$Mode) {
  if ($Mode -eq 'save_then_close') {
    try { if (-not [bool]$Doc.ReadOnly) { $Doc.Save() } } catch {}
    try { $Doc.Saved = $true } catch {}
  } elseif ($Mode -eq 'discard_without_recovery') {
    try { $Doc.Saved = $true } catch {}
  }
  try { $Doc.Activate() } catch {}
  $wdDoNotSaveChanges = 0
  try { $Doc.Close([ref]$wdDoNotSaveChanges) } catch { $Doc.Close(0) }
}

$sourceFull = Normalize-CsmPath $Source
$sourceName = ([string]$SourceName).Trim()
if ([string]::IsNullOrWhiteSpace($sourceName) -and -not [string]::IsNullOrWhiteSpace($sourceFull)) {
  try { $sourceName = [System.IO.Path]::GetFileName($sourceFull) } catch {}
}
$deadline = (Get-Date).AddSeconds([Math]::Max(3, $TimeoutSec))
$lastOpen = ''

while ((Get-Date) -le $deadline) {
  $word = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application')
  $nameMatches = @()
  $openSummaries = New-Object System.Collections.Generic.List[string]
  foreach ($doc in @($word.Documents)) {
    $full = Csm-DocPath $doc
    $name = ''
    try { $name = [string]$doc.Name } catch { $name = '' }
    if (-not [string]::IsNullOrWhiteSpace($name)) { [void]$openSummaries.Add($name) }
    if (-not [string]::IsNullOrWhiteSpace($sourceFull) -and -not [string]::IsNullOrWhiteSpace($full) -and [string]::Equals($full, $sourceFull, [System.StringComparison]::OrdinalIgnoreCase)) {
      Csm-CloseDoc $doc $SaveMode
      Write-Output ('CSM_CLOSED exact ' + $name)
      exit 0
    }
    if (-not [string]::IsNullOrWhiteSpace($sourceName) -and [string]::Equals($name, $sourceName, [System.StringComparison]::OrdinalIgnoreCase)) {
      $nameMatches += $doc
    }
  }
  $lastOpen = [string]::Join(', ', $openSummaries.ToArray())
  if ($nameMatches.Count -eq 1) {
    $name = ''
    try { $name = [string]$nameMatches[0].Name } catch {}
    Csm-CloseDoc $nameMatches[0] $SaveMode
    Write-Output ('CSM_CLOSED unique-name ' + $name)
    exit 0
  }
  if ($nameMatches.Count -gt 1) {
    Write-Error ('CSM_AMBIGUOUS_NAME_MATCH: more than one open Word document is named ' + $sourceName)
    exit 3
  }
  Start-Sleep -Milliseconds 700
}
Write-Output ('CSM_NOT_FOUND; open=' + $lastOpen)
exit 2
'''
    try:
        script.write_text(script_text, encoding="utf-8")
        cmd = [ps, "-NoProfile", "-Sta", "-ExecutionPolicy", "Bypass", "-File", str(script), requested_path, requested_name, mode, str(float(delay_sec or 0.0)), str(int(timeout_seconds or 18))]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(6, int(timeout_seconds or 18) + int(delay_sec or 0) + 5),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            return True, None
        detail = (proc.stderr or proc.stdout or "Word COM close failed").strip()
        return False, _sanitize_error_detail(detail)
    except subprocess.TimeoutExpired:
        return False, "Word COM close przekroczył limit czasu."
    except Exception as exc:
        return False, _sanitize_error_detail(str(exc))
    finally:
        try:
            if script.exists():
                script.unlink()
        except Exception:
            pass


def _close_word_document_async(doc_path: str = "", delay_sec: float = 1.5, *, save_mode: str = "save_then_close", doc_name: str | None = None, attempts: int = 5) -> None:
    """Fire-and-forget wrapper around _close_word_document with retries.

    This is used after CSM opens the next document. Retrying matters because
    Word can be busy while switching windows/opening the new DOCX, and a single
    COM attempt can miss the document or fail transiently.
    """
    def _worker() -> None:
        last_error = None
        for attempt in range(max(1, int(attempts or 1))):
            try:
                closed, err = _close_word_document(
                    doc_path or "",
                    doc_name=doc_name,
                    delay_sec=delay_sec if attempt == 0 else 0.8,
                    save_mode=save_mode,
                    timeout_seconds=10,
                )
                if closed:
                    return
                last_error = err
            except Exception as exc:
                last_error = str(exc)
            try:
                audit_log("warn", mode="word_close_async", status="retry", attempt=attempt + 1, error=_sanitize_error_detail(str(last_error or "")))
            except Exception:
                pass
        try:
            audit_log("warn", mode="word_close_async", status="failed", error=_sanitize_error_detail(str(last_error or "")))
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _schedule_word_close_after_open(doc_path: str = "", *, doc_name: str | None = None, save_mode: str = "save_then_close") -> Dict[str, Any]:
    """Schedule robust post-open Word close and return a user-visible report."""
    if not (doc_path or doc_name):
        return {"scheduled": False, "reason": "missing path/name"}
    _close_word_document_async(doc_path or "", doc_name=doc_name, save_mode=save_mode)
    return {
        "scheduled": True,
        "method": "word-com-retry",
        "match": "path-or-unique-filename",
        "path_provided": bool(doc_path),
        "name_provided": bool(doc_name),
        "save_mode": save_mode,
    }


def _cleanup_session_working_files_async(session_dir: Path, anon_filename: str, *, delay_sec: float = 8.0) -> None:
    """Background: after a successful restore-to-original, delete working files from the
    session directory so the user is left with only *_oryginal.docx* as their pre-anonymisation
    evidence copy.  Deleted: *_CSM_anon.docx*, any numbered *_CSM_anon_*.docx backups, and
    *_CSM_jawny.docx* if it somehow exists.  Runs in a daemon thread — never blocks the response.
    """
    base_stem = Path(anon_filename).stem.replace("_CSM_anon", "")

    def _do_cleanup() -> None:
        if delay_sec > 0:
            time.sleep(delay_sec)
        # Keep only <stem>_oryginal.docx as the evidence copy. Remove the
        # working anonymized file, any numbered anon backups, jawny session
        # fallbacks, and temporary COM SaveCopyAs files.
        patterns = [
            f"{base_stem}_CSM_anon.docx",
            f"{base_stem}_CSM_anon_*.docx",
            f"{base_stem}_CSM_jawny.docx",
            f"{base_stem}_CSM_jawny_*.docx",
            ".csm_live_*.docx",
        ]
        for pattern in patterns:
            try:
                for p in session_dir.glob(pattern):
                    try:
                        if p.is_file():
                            p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass

    threading.Thread(target=_do_cleanup, daemon=True).start()


def _open_file_path(path: Path, enabled: bool = True) -> tuple[bool, str | None]:
    if not enabled or os.environ.get("CSM_DISABLE_OPEN_FILE") == "1":
        return False, None
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, None
    except Exception as exc:
        return False, _sanitize_error_detail(str(exc))


def _docx_contains_any_map_placeholder(docx_bytes: bytes, replacements_payload: List[dict]) -> bool:
    """Return True when a DOCX package contains at least one placeholder from the selected CSM map.

    This is a defensive fallback for /v4/current/restore: when CSM metadata is
    absent from the current Word package, we only allow a caller-supplied map_id
    if the active DOCX actually contains placeholders from that map. This avoids
    silently producing a meaningless "jawny" copy from the original document.
    """
    placeholders = [str(item.get("placeholder", "")) for item in (replacements_payload or []) if item.get("placeholder")]
    if not placeholders:
        return True
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
            for name in zf.namelist():
                if not str(name).lower().endswith(".xml"):
                    continue
                try:
                    text = zf.read(name).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if any(ph and ph in text for ph in placeholders):
                    return True
    except Exception:
        return False
    return False


def _load_map_any(map_id: str) -> dict:
    try:
        return load_map(map_id)
    except FileNotFoundError:
        return load_install_backup(map_id)

@app.get("/audit_summary")
def audit_summary(limit: int = 50):
    """Return recent audit-log entries (PII-free, allow-listed fields only)."""
    n = max(1, min(int(limit or 50), 500))
    return {"version": APP_VERSION, "entries": read_audit_tail(n)}


@app.get("/health")
def health():
    be = _bielik_enabled_fn()
    bielik_reachable = _bielik_reachable() if be else False
    embedding_provider = os.environ.get("EMBEDDING_PROVIDER", "").strip() or "ollama"
    bielik_model = (
        os.environ.get("CSMW_BIELIK_MODEL", "").strip()
        or os.environ.get("BIELIK_MODEL", "").strip()
    )
    return {
        "status": "ok",
        "version": APP_VERSION,
        "token_required": True,
        "mode": csm_mode(),
        "remote_mode": os.environ.get("CSM_REMOTE_MODE", "").strip().lower() in {"1", "true", "yes", "on"},
        "api_base_url": os.environ.get("CSM_PUBLIC_API_URL", "").strip(),
        "embedding_provider": embedding_provider,
        "bielik_model": bielik_model,
        "bielik_available": be,
        "bielik_reachable": bielik_reachable,
        "paths": {
            "maps": str(MAPS_DIR),
            "backups": str(INSTALL_BACKUPS_DIR),
        },
        "nlp": {
            "bielik_enabled": be,
            "bielik_reachable": bielik_reachable,
            "bielik_model": bielik_model,
            "embedding_provider": embedding_provider,
        },
    }


@app.get("/auth/bootstrap")
def auth_bootstrap():
    """Return the current local API token to the Office add-in.

    Cache-Control: no-store is set so proxies and security tools cannot cache
    the token response.

    The add-in is loaded from the trusted local catalog at https://localhost:3000,
    but Word/WebView may keep an older static csm-token.js in cache after STOP/START
    or after an update. The backend already reads the runtime api-token.txt file
    on every protected request, so this unprotected local-only GET endpoint lets the
    trusted add-in resynchronize before retrying a POST. CORS still limits browser
    access to the local add-in origin.
    """
    token = get_api_token() or ""
    return JSONResponse(
        content={
            "status": "ok" if token else "missing",
            "version": APP_VERSION,
            "token": token,
            "token_required": True,
        },
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/auth_check")
def auth_check():
    return {"status": "ok", "version": APP_VERSION, "authorized": True}


@app.post("/docx_revision_report")
def docx_revision_report(req: DocxRevisionReportRequest):
    files = docx_revision_files(req.docx_base64)
    return {"has_tracked_changes": bool(files), "revision_files": files[:50], "version": APP_VERSION}


@app.post("/scan", response_model=ScanResponse)
def scan(req: MaskRequest):
    """Preview detection without saving a map or returning original values."""
    validate_text_size(req.text)
    masked, replacements = make_replacements(req.text)
    counts = category_counts(replacements)
    review_warnings, review_status = _run_review_mode(masked, replacements, req.review_mode)
    warnings = collect_ambiguous_person_warnings(replacements) + review_warnings
    anonymization_report = _build_anonymization_report(replacements, {"coverage": {"body": True}, "processed_parts": ["text"]}, warnings, review_status=review_status)
    return ScanResponse(entities_count=len(replacements), version=APP_VERSION, warnings=warnings, category_counts=counts, anonymization_report=anonymization_report, **_review_response_fields(review_status))


@app.post("/mask", response_model=MaskResponse)
def mask(req: MaskRequest):
    validate_text_size(req.text)
    masked, replacements = make_replacements(req.text)
    source_hash = sha256_text(req.text)
    map_id = save_map(replacements, source_hash=source_hash, original_text=req.text, original_docx_base64=req.original_docx_base64, require_install_backup=bool(req.original_docx_base64))
    counts = category_counts(replacements)
    review_warnings, review_status = _run_review_mode(masked, replacements, req.review_mode)
    warnings = collect_ambiguous_person_warnings(replacements) + review_warnings
    anonymization_report = _build_anonymization_report(replacements, {"coverage": {"body": True}, "processed_parts": ["text"]}, warnings, review_status=review_status)
    audit_log("mask", map_id=map_id, mode="text", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return MaskResponse(masked_text=masked, map_id=map_id, entities_count=len(replacements), version=APP_VERSION, warnings=warnings, category_counts=counts, anonymization_report=anonymization_report, **_review_response_fields(review_status))


@app.post("/mask_ooxml", response_model=OoxmlMaskResponse)
def mask_ooxml_endpoint(req: OoxmlMaskRequest):
    limit = max_docx_xml_bytes()
    if len(req.ooxml.encode("utf-8")) > limit:
        raise _http_error(413, f"Rozmiar OOXML przekracza limit {limit} bajtów.", public_detail=f"Rozmiar struktury dokumentu Word przekracza limit {limit} bajtów.")
    try:
        masked_ooxml, replacements = mask_ooxml(req.ooxml)
    except Exception as exc:
        audit_log("error", mode="ooxml_mask", status="failed")
        raise _http_error(400, f"OOXML masking failed: {exc}", public_detail="Nie udało się przygotować dokumentu w trybie strukturalnym") from exc
    source_hash = sha256_text(req.ooxml)
    map_id = save_map(replacements, source_hash=source_hash, original_ooxml=req.ooxml)
    counts = category_counts(replacements)
    review_warnings, review_status = _run_review_mode(ooxml_to_text(masked_ooxml), replacements, req.review_mode)
    warnings = collect_ambiguous_person_warnings(replacements) + review_warnings
    anonymization_report = _build_anonymization_report(replacements, {"coverage": {"body": True}, "processed_parts": ["ooxml"]}, warnings, review_status=review_status)
    audit_log("mask", map_id=map_id, mode="ooxml", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return OoxmlMaskResponse(ooxml=masked_ooxml, map_id=map_id, entities_count=len(replacements), version=APP_VERSION, warnings=warnings, category_counts=counts, anonymization_report=anonymization_report, **_review_response_fields(review_status))


@app.post("/restore")
def restore(req: RestoreRequest):
    try:
        payload = load_map(req.map_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    audit_log("restore_map", map_id=payload["map_id"], mode="text")
    return {
        "map_id": payload["map_id"],
        "created_at": payload["created_at"],
        "replacements": payload["replacements"],
        "version": APP_VERSION,
    }


@app.post("/restore_ooxml")
def restore_ooxml_endpoint(req: OoxmlRestoreRequest):
    try:
        payload = load_map(req.map_id)
        restored_ooxml, restore_report = restore_ooxml_with_report(req.ooxml, payload["replacements"])
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except Exception as exc:
        audit_log("error", mode="ooxml_restore", status="failed")
        raise _http_error(400, f"OOXML restore failed: {exc}", public_detail="Nie udało się przywrócić dokumentu w trybie strukturalnym") from exc
    audit_log("restore", map_id=payload["map_id"], mode="ooxml", restore_report=restore_report)
    return {
        "map_id": payload["map_id"],
        "ooxml": restored_ooxml,
        "version": APP_VERSION,
        "restore_report": restore_report,
    }


@app.post("/mask_ooxml_parts", response_model=OoxmlPartsMaskResponse)
def mask_ooxml_parts_endpoint(req: OoxmlPartsMaskRequest):
    total_size = sum(len(v.encode("utf-8")) for v in req.parts.values())
    limit = max_docx_xml_bytes()
    if total_size > limit:
        raise _http_error(413, f"Łączny rozmiar OOXML parts przekracza limit {limit} bajtów.", public_detail=f"Łączny rozmiar części dokumentu Word przekracza limit {limit} bajtów.")
    try:
        masked_parts, replacements = mask_ooxml_parts(req.parts)
    except Exception as exc:
        audit_log("error", mode="ooxml_parts_mask", status="failed")
        raise _http_error(400, f"OOXML parts masking failed: {exc}", public_detail="Nie udało się przygotować części dokumentu w trybie strukturalnym") from exc
    source_hash = sha256_text(str(req.parts))
    map_id = save_map(replacements, source_hash=source_hash, original_ooxml=json_dumps_safe(req.parts), original_text=req.original_text, original_docx_base64=req.original_docx_base64, require_install_backup=bool(req.original_docx_base64))
    counts = category_counts(replacements)
    review_warnings, review_status = _run_review_mode(ooxml_parts_to_text(masked_parts), replacements, req.review_mode)
    warnings = collect_ambiguous_person_warnings(replacements) + review_warnings
    anonymization_report = _build_anonymization_report(replacements, {"coverage": {"body": True}, "processed_parts": list(masked_parts.keys())}, warnings, review_status=review_status)
    audit_log("mask", map_id=map_id, mode="ooxml_parts", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return OoxmlPartsMaskResponse(parts=masked_parts, map_id=map_id, entities_count=len(replacements), version=APP_VERSION, warnings=warnings, category_counts=counts, processed_parts=list(masked_parts.keys()), anonymization_report=anonymization_report, **_review_response_fields(review_status))


@app.post("/restore_ooxml_parts")
def restore_ooxml_parts_endpoint(req: OoxmlPartsRestoreRequest):
    total_size = sum(len(v.encode("utf-8")) for v in req.parts.values())
    limit = max_docx_xml_bytes()
    if total_size > limit:
        raise _http_error(413, f"Łączny rozmiar OOXML parts przekracza limit {limit} bajtów.", public_detail=f"Łączny rozmiar części dokumentu Word przekracza limit {limit} bajtów.")
    try:
        payload = load_map(req.map_id)
        restored_parts, restore_report = restore_ooxml_parts(req.parts, payload["replacements"])
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except Exception as exc:
        audit_log("error", mode="ooxml_parts_restore", status="failed")
        raise _http_error(400, f"OOXML parts restore failed: {exc}", public_detail="Nie udało się przywrócić części dokumentu w trybie strukturalnym") from exc
    audit_log("restore", map_id=payload["map_id"], mode="ooxml_parts", restore_report=restore_report)
    return {"map_id": payload["map_id"], "parts": restored_parts, "version": APP_VERSION, "restore_report": restore_report}


@app.post("/placeholder_report")
def placeholder_report_endpoint(req: PlaceholderReportRequest):
    try:
        payload = load_map(req.map_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    text = req.text or ""
    if req.ooxml:
        try:
            text += "\n" + ooxml_to_text(req.ooxml)
        except Exception:
            pass
    if req.parts:
        text += "\n" + ooxml_parts_to_text(req.parts)
    return {"map_id": payload["map_id"], "version": APP_VERSION, "placeholder_report": placeholder_report(text, payload["replacements"])}



def _revision_plan_response(req: RevisionPlanRequest, *, mode: str) -> RevisionPlanResponse:
    replacements = list(req.replacements or [])
    resolved_map_id = (req.map_id or "").strip()
    if not replacements and resolved_map_id:
        try:
            payload = load_map(resolved_map_id)
        except FileNotFoundError as exc:
            audit_log("error", mode="revision_plan", status="map_not_found", map_id=resolved_map_id)
            raise _http_error(
                404,
                f"Revision map not found for map_id={resolved_map_id}: {exc}",
                public_detail="Nie znaleziono mapy rewizyjnej CSM dla wskazanego map_id.",
            ) from exc
        replacements = list(payload.get("replacements", []) or [])
        resolved_map_id = payload.get("map_id") or resolved_map_id
    job = build_revision_job(
        map_id=resolved_map_id,
        mode=mode,
        replacements=replacements,
        anchors=req.anchors or [],
        keep_tracking=req.keep_tracking,
        author=req.author or "CSM",
    )
    validation = validate_revision_job(job)
    as_dict = revision_job_to_dict(job)
    return RevisionPlanResponse(
        version=APP_VERSION,
        engine_version=REVISION_PLAN_ENGINE_VERSION,
        namespace=CSM_REVISION_MAP_NS,
        map_id=job.map_id,
        mode=job.mode,
        operations=as_dict["operations"],
        anchors=as_dict["anchors"],
        summary=as_dict["summary"],
        validation=validation,
        strategy=validation.get("strategy") or as_dict["summary"].get("restore_strategy", {}),
        document_metadata=build_document_metadata(job),
        custom_xml_payload=build_custom_xml_payload(job),
    )


@app.post("/v2/revision/anonymize", response_model=RevisionPlanResponse)
def revision_anonymize_plan_endpoint(req: RevisionPlanRequest):
    return _revision_plan_response(req, mode="anonymize")


@app.post("/v2/revision/restore", response_model=RevisionPlanResponse)
def revision_restore_plan_endpoint(req: RevisionPlanRequest):
    return _revision_plan_response(req, mode="restore")


@app.post("/v2/revision/validate")
def revision_validate_plan_endpoint(req: RevisionPlanRequest):
    response = _revision_plan_response(req, mode=req.mode or "restore")
    return {
        "version": response.version,
        "engine_version": response.engine_version,
        "namespace": response.namespace,
        "map_id": response.map_id,
        "mode": response.mode,
        "summary": response.summary,
        "strategy": response.strategy,
        "validation": response.validation,
    }


def _validate_revision_sidecar_docx_base64(value: str, *, field_name: str) -> bytes:
    try:
        raw = base64_to_bytes(value or "")
    except Exception as exc:
        raise _http_error(400, f"Nieprawidłowy DOCX/base64 w polu {field_name}: {exc}", public_detail=f"Nieprawidłowy plik Word w polu {field_name}") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            _check_docx_xml_uncompressed_limit(zf)
            if "word/document.xml" not in set(zf.namelist()):
                raise _http_error(400, f"Pole {field_name} nie zawiera word/document.xml.", public_detail=f"Pole {field_name} nie wygląda jak dokument programu Word.")
    except DocxXmlTooLargeError as exc:
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except zipfile.BadZipFile as exc:
        raise _http_error(400, f"Pole {field_name} nie jest prawidłowym DOCX/ZIP.", public_detail=f"Pole {field_name} nie jest prawidłowym DOCX/ZIP.") from exc
    return raw


def _redact_revision_sidecar_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    redacted = dict(contract or {})
    for key in ["docx_base64", "revised_docx_base64"]:
        value = redacted.pop(key, "")
        redacted[f"{key}_present"] = bool(value)
    return redacted


def _redact_revision_sidecar_status(status: Dict[str, Any]) -> Dict[str, Any]:
    """Return sidecar diagnostics without leaking local command paths or args."""
    redacted = dict(status or {})
    command = redacted.get("command")
    executable = redacted.get("executable")
    if command:
        redacted["command"] = "<redacted>"
        redacted["command_configured"] = True
    else:
        redacted["command_configured"] = bool(redacted.get("configured"))
    if executable:
        redacted["executable"] = "<redacted>"
        redacted["executable_resolved"] = True
    else:
        redacted["executable_resolved"] = False
    return redacted


def _sidecar_action_response(*, action: str, request_contract: Dict[str, Any], execute: bool) -> RevisionSidecarActionResponse:
    status = sidecar_status_dict()
    execution: Dict[str, Any] = {
        "requested": bool(execute),
        "executed": False,
        "status": "dry_run" if not execute else "pending",
    }
    result: Dict[str, Any] = {}
    if execute:
        try:
            result = invoke_sidecar(request_contract)
            execution.update({"executed": True, "status": "completed"})
            status = sidecar_status_dict()
        except RevisionSidecarUnavailable as exc:
            execution.update({"status": "sidecar_unavailable", "error": str(exc)})
            raise _http_error(503, f"Revision sidecar unavailable: {exc}", public_detail="Mechanizm zachowania śledzenia zmian nie jest podłączony albo jest niedostępny.") from exc
        except RevisionSidecarProtocolError as exc:
            execution.update({"status": "sidecar_protocol_error", "error": str(exc)})
            raise _http_error(502, f"Revision sidecar protocol error: {exc}", public_detail="Mechanizm zachowania śledzenia zmian zwrócił nieprawidłową odpowiedź.") from exc
        except RevisionSidecarError as exc:
            execution.update({"status": "sidecar_error", "error": str(exc)})
            raise _http_error(502, f"Revision sidecar error: {exc}", public_detail="Mechanizm zachowania śledzenia zmian zgłosił błąd wykonania.") from exc
    else:
        execution["note"] = "CSM pokazuje plan działania; wykonanie będzie dostępne po podłączeniu mechanizmu zachowania śledzenia zmian."
    return RevisionSidecarActionResponse(
        version=APP_VERSION,
        engine_version=REVISION_PLAN_ENGINE_VERSION,
        protocol_version=SIDECAR_PROTOCOL_VERSION,
        action=action,
        sidecar_status=_redact_revision_sidecar_status(status),
        request_contract=_redact_revision_sidecar_contract(request_contract),
        execution=execution,
        result=result,
    )


@app.get("/v2/revision/sidecar/status", response_model=RevisionSidecarStatusResponse)
def revision_sidecar_status_endpoint():
    return RevisionSidecarStatusResponse(
        version=APP_VERSION,
        engine_version=REVISION_PLAN_ENGINE_VERSION,
        protocol_version=SIDECAR_PROTOCOL_VERSION,
        sidecar_status=_redact_revision_sidecar_status(sidecar_status_dict(probe=True)),
        supported_actions=sorted(SUPPORTED_ACTIONS),
    )


@app.post("/v2/revision/compare", response_model=RevisionSidecarActionResponse)
def revision_compare_endpoint(req: RevisionSidecarCompareRequest):
    _validate_revision_sidecar_docx_base64(req.original_docx_base64, field_name="original_docx_base64")
    _validate_revision_sidecar_docx_base64(req.revised_docx_base64, field_name="revised_docx_base64")
    contract = build_sidecar_request(
        action="compare",
        docx_base64=req.original_docx_base64,
        revised_docx_base64=req.revised_docx_base64,
        author=req.author or "CSM",
        strategy={"mode": "full-docx", "operations_scope": "package", "source": "WmlComparer.Compare"},
    )
    return _sidecar_action_response(action="compare", request_contract=contract, execute=req.execute)


@app.post("/v2/revision/normalize", response_model=RevisionSidecarActionResponse)
def revision_normalize_endpoint(req: RevisionSidecarNormalizeRequest):
    _validate_revision_sidecar_docx_base64(req.docx_base64, field_name="docx_base64")
    contract = build_sidecar_request(
        action="normalize",
        docx_base64=req.docx_base64,
        author=req.author or "CSM",
        strategy={"mode": "full-docx", "operations_scope": "package", "source": "RevisionProcessor.AcceptReject"},
    )
    return _sidecar_action_response(action="normalize", request_contract=contract, execute=req.execute)


@app.post("/v2/revision/tracked-replace", response_model=RevisionSidecarActionResponse)
def revision_tracked_replace_endpoint(req: RevisionSidecarTrackedReplaceRequest):
    _validate_revision_sidecar_docx_base64(req.docx_base64, field_name="docx_base64")
    operations = list(req.operations or [])
    if not operations:
        raise _http_error(400, "tracked-replace wymaga co najmniej jednej operacji.", public_detail="Zachowanie śledzenia zmian przy podmianie danych wymaga co najmniej jednej operacji.")
    contract = build_sidecar_request(
        action="tracked-replace",
        docx_base64=req.docx_base64,
        operations=operations,
        author=req.author or "CSM",
        map_id=req.map_id or "",
        strategy={"mode": "range-ooxml", "operations_scope": "anchored-ranges", "source": "OpenXmlRegex.Replace(trackRevisions=true)"},
    )
    return _sidecar_action_response(action="tracked-replace", request_contract=contract, execute=req.execute)


@app.post("/mask_docx_package", response_model=DocxPackageMaskResponse)
def mask_docx_package_endpoint(req: DocxPackageMaskRequest):
    try:
        raw = base64_to_bytes(req.docx_base64)
        masked_bytes, replacements, package_report = mask_ooxml_package_bytes(raw)
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_package_mask", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_package_mask", status="failed")
        raise _http_error(400, f"DOCX package masking failed: {exc}", public_detail="DOCX package masking failed") from exc
    source_hash = sha256_text(req.docx_base64)
    map_id = save_map(
        replacements,
        source_hash=source_hash,
        original_docx_base64=req.docx_base64,
        require_install_backup=True,
    )
    counts = category_counts(replacements)
    text_for_scan = docx_package_to_text(masked_bytes)
    review_warnings, review_status = _run_review_mode(text_for_scan, replacements, req.review_mode)
    full_warnings = collect_ambiguous_person_warnings(replacements) + review_warnings
    anonymization_report = _build_anonymization_report(replacements, package_report, full_warnings, masked_bytes, review_status=review_status)
    audit_log("mask", map_id=map_id, mode="docx_package", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return DocxPackageMaskResponse(
        docx_base64=bytes_to_base64(masked_bytes),
        map_id=map_id,
        entities_count=len(replacements),
        version=APP_VERSION,
        warnings=full_warnings,
        category_counts=counts,
        package_report=package_report,
        anonymization_report=anonymization_report,
        **_review_response_fields(review_status),
    )


@app.post("/restore_docx_package")
def restore_docx_package_endpoint(req: DocxPackageRestoreRequest):
    try:
        payload = load_map(req.map_id)
        raw = base64_to_bytes(req.docx_base64)
        restored_bytes, restore_report = restore_ooxml_package_bytes(raw, payload["replacements"])
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except Exception as exc:
        audit_log("error", mode="docx_package_restore", status="failed")
        raise _http_error(400, f"DOCX package restore failed: {exc}", public_detail="DOCX package restore failed") from exc
    audit_log("restore", map_id=payload["map_id"], mode="docx_package", restore_report=restore_report)
    return {
        "map_id": payload["map_id"],
        "docx_base64": bytes_to_base64(restored_bytes),
        "version": APP_VERSION,
        "restore_report": restore_report,
    }




@app.post("/mask_docx_v3", response_model=DocxV3MaskResponse)
def mask_docx_v3_endpoint(req: DocxV3MaskRequest):
    mode = (req.mode or "preserve").strip()
    if mode not in {"preserve", "accept_then_mask", "reject_then_mask"}:
        raise _http_error(400, f"Unsupported v3 DOCX mode: {mode}", public_detail="Unsupported v3 DOCX mode")
    try:
        raw = base64_to_bytes(req.docx_base64)
        masked_bytes, replacements, package_report = mask_docx_preserving_tc(raw, mode=mode)
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v3_mask", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v3_mask", status="failed")
        raise _http_error(400, f"DOCX v3 masking failed: {exc}", public_detail="DOCX v3 masking failed") from exc
    source_hash = sha256_text(req.docx_base64)
    map_id = save_map(
        replacements,
        source_hash=source_hash,
        original_docx_base64=req.docx_base64,
        require_install_backup=True,
    )
    counts = category_counts(replacements)
    ambiguity_warnings = collect_ambiguous_person_warnings(replacements)
    review_warnings, review_status = _run_review_mode(docx_package_to_text(masked_bytes), replacements, req.review_mode)
    full_warnings = ambiguity_warnings + list(package_report.get("warnings", [])) + review_warnings
    audit_log("mask", map_id=map_id, mode="docx_v3", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), engine_version=TC_ENGINE_VERSION, warnings_count=len(full_warnings), llm_findings_count=review_status.get("bielik_findings_count", 0))
    anonymization_report = _build_anonymization_report(replacements, package_report, full_warnings, masked_bytes, review_status=review_status)
    return DocxV3MaskResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        masked_docx_base64=bytes_to_base64(masked_bytes),
        map_id=map_id,
        category_counts=counts,
        entities_count=len(replacements),
        revisions_summary=package_report.get("revisions_summary", {}),
        coverage=package_report.get("coverage", {}),
        warnings=full_warnings,
        anonymization_report=anonymization_report,
        **_review_response_fields(review_status),
    )


@app.post("/restore_docx_v3", response_model=DocxV3RestoreResponse)
def restore_docx_v3_endpoint(req: DocxV3RestoreRequest):
    try:
        payload = load_map(req.map_id)
        raw = base64_to_bytes(req.docx_base64)
        original_bytes = None
        try:
            original_docx_base64 = payload.get("original_docx_base64")
            if original_docx_base64:
                original_bytes = base64_to_bytes(original_docx_base64)
        except Exception:
            original_bytes = None
        restored_bytes, restore_report = restore_docx_preserving_tc_with_original_context(
            raw,
            payload["replacements"],
            original_bytes,
            placeholder_restore_overrides=payload.get("placeholder_restore_overrides"),
        )
        restored_bytes, image_restore_report = restore_redacted_images_from_original(restored_bytes, original_bytes)
        if any(int(v or 0) for v in image_restore_report.values()):
            restore_report["image_restore_report"] = image_restore_report
        restore_report.setdefault("leftover_total_after_restore", 0)
        restore_report.setdefault("leftover_placeholders_after_restore", [])
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v3_restore", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v3_restore", status="failed")
        raise _http_error(400, f"DOCX v3 restore failed: {exc}", public_detail="DOCX v3 restore failed") from exc
    audit_log("restore", map_id=payload["map_id"], mode="docx_v3", restore_report=restore_report)
    restore_quality_report = _build_restore_quality_report(restore_report, [])
    return DocxV3RestoreResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        restored_docx_base64=bytes_to_base64(restored_bytes),
        restore_report=restore_report,
        warnings=[],
        restore_quality_report=restore_quality_report,
    )



@app.post("/v4/docx/prepare", response_model=DocxV4PrepareResponse)
def v4_docx_prepare(req: DocxV4PrepareRequest):
    """Create a negotiation-safe anonymized DOCX copy.

    This endpoint works on the full DOCX package and returns a new
    file payload. It does not edit the active Word document through Range API.
    """
    mode = (req.mode or "preserve").strip()
    if mode not in {"preserve", "accept_then_mask", "reject_then_mask"}:
        raise _http_error(400, f"Unsupported v4 DOCX mode: {mode}", public_detail="Unsupported v4 DOCX mode")
    try:
        raw = base64_to_bytes(req.docx_base64)
        anon_bytes, replacements, package_report = mask_docx_preserving_tc(raw, mode=mode)
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v4_prepare", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v4_prepare", status="failed")
        raise _http_error(400, f"DOCX v4 prepare failed: {exc}", public_detail="DOCX v4 prepare failed") from exc
    source_hash = _canonical_docx_hash(raw)
    map_id = save_map(
        replacements,
        source_hash=source_hash,
        original_docx_base64=req.docx_base64,
        require_install_backup=True,
    )
    counts = category_counts(replacements)
    review_warnings, review_status = _run_review_mode(docx_package_to_text(anon_bytes), replacements, req.review_mode)
    full_warnings = collect_ambiguous_person_warnings(replacements) + list(package_report.get("warnings", [])) + review_warnings
    negotiation_report = _v4_negotiation_report(raw, anon_bytes, None, package_report, None)
    # Safety check: immediate roundtrip should be canonical-identical when
    # no user changes have been made between prepare and restore.
    # Skip for large documents (>500 kB DOCX bytes) to avoid doubling the
    # response time — the roundtrip runs the full restore pipeline again.
    _ROUNDTRIP_SIZE_LIMIT = 500_000
    if len(raw) <= _ROUNDTRIP_SIZE_LIMIT:
        try:
            rt_bytes, rt_report = restore_docx_preserving_tc(anon_bytes, [asdict(r) for r in replacements])
            rt_bytes, rt_image_report = restore_redacted_images_from_original(rt_bytes, raw)
            if any(int(v or 0) for v in rt_image_report.values()):
                rt_report["image_restore_report"] = rt_image_report
            negotiation_report["immediate_roundtrip"] = _docx_diff_summary(raw, rt_bytes)
            negotiation_report["immediate_restore_report"] = rt_report
            if not negotiation_report["immediate_roundtrip"].get("identical"):
                full_warnings.append("Kontrola roundtrip: prepare→restore is not canonical-identical; review diff report before legal negotiation use.")
        except Exception as exc:
            full_warnings.append(f"Kontrola roundtrip failed: {_sanitize_error_detail(str(exc))}")
    else:
        negotiation_report["immediate_roundtrip"] = {"skipped": True, "reason": "document too large for inline roundtrip check"}
    anonymization_report = _build_anonymization_report(replacements, package_report, full_warnings, anon_bytes, review_status=review_status)
    audit_log("mask", map_id=map_id, mode="docx_v4_prepare", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), engine_version=TC_ENGINE_VERSION, warnings_count=len(full_warnings), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return DocxV4PrepareResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        anon_docx_base64=bytes_to_base64(anon_bytes),
        map_id=map_id,
        suggested_filename=_docx_suggested_filename(req.filename, "CSM_anon"),
        category_counts=counts,
        entities_count=len(replacements),
        coverage=package_report.get("coverage", {}),
        revisions_summary=package_report.get("revisions_summary", {}),
        negotiation_report=negotiation_report,
        warnings=full_warnings,
        anonymization_report=anonymization_report,
        **_review_response_fields(review_status),
    )


@app.post("/v4/docx/restore", response_model=DocxV4RestoreResponse)
def v4_docx_restore(req: DocxV4RestoreRequest):
    """Create a restored clear DOCX copy from an anonymized negotiation copy."""
    try:
        payload = load_map(req.map_id)
        raw = base64_to_bytes(req.docx_base64)
        original_bytes = None
        try:
            original_docx_base64 = payload.get("original_docx_base64")
            if original_docx_base64:
                original_bytes = base64_to_bytes(original_docx_base64)
        except Exception:
            original_bytes = None
        restored_bytes, restore_report = restore_docx_preserving_tc_with_original_context(
            raw,
            payload["replacements"],
            original_bytes,
            placeholder_restore_overrides=payload.get("placeholder_restore_overrides"),
        )
        restored_bytes, image_restore_report = restore_redacted_images_from_original(restored_bytes, original_bytes)
        if any(int(v or 0) for v in image_restore_report.values()):
            restore_report["image_restore_report"] = image_restore_report
        restore_report.setdefault("leftover_total_after_restore", 0)
        restore_report.setdefault("leftover_placeholders_after_restore", [])
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v4_restore", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v4_restore", status="failed")
        raise _http_error(400, f"DOCX v4 restore failed: {exc}", public_detail="DOCX v4 restore failed") from exc
    negotiation_report = _v4_negotiation_report(original_bytes, raw, restored_bytes, None, restore_report)
    warnings: List[str] = []
    if restore_report.get("leftover_total_after_restore"):
        warnings.append("Po restore w pliku pozostały placeholdery; dokument wymaga kontroli.")
    restore_quality_report = _build_restore_quality_report(restore_report, warnings)
    audit_log("restore", map_id=payload["map_id"], mode="docx_v4_restore", restore_report=restore_report)
    return DocxV4RestoreResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        restored_docx_base64=bytes_to_base64(restored_bytes),
        map_id=payload["map_id"],
        suggested_filename=_docx_suggested_filename(req.filename, "CSM_jawny"),
        restore_report=restore_report,
        negotiation_report=negotiation_report,
        warnings=warnings,
        restore_quality_report=restore_quality_report,
    )


@app.post("/v4/docx/validate-roundtrip")
def v4_docx_validate_roundtrip(req: DocxV4ValidateRoundtripRequest):
    try:
        original = base64_to_bytes(req.original_docx_base64)
        restored = base64_to_bytes(req.restored_docx_base64)
        diff = _docx_diff_summary(original, restored)
    except Exception as exc:
        raise _http_error(400, f"DOCX v4 validation failed: {exc}", public_detail="DOCX v4 validation failed") from exc
    return {"version": APP_VERSION, "roundtrip": diff}


@app.post("/v4/docx/diff-report")
def v4_docx_diff_report(req: DocxV4DiffReportRequest):
    try:
        left = base64_to_bytes(req.left_docx_base64)
        right = base64_to_bytes(req.right_docx_base64)
        diff = _docx_diff_summary(left, right)
    except Exception as exc:
        raise _http_error(400, f"DOCX v4 diff failed: {exc}", public_detail="DOCX v4 diff failed") from exc
    return {"version": APP_VERSION, "diff": diff}



@app.post("/v4/current/status")
def v4_current_status(req: DocxV4CurrentStatusRequest):
    try:
        raw = base64_to_bytes(req.docx_base64)
        metadata = _extract_csm_metadata(raw)
    except Exception as exc:
        raise _http_error(400, f"DOCX v4 status failed: {exc}", public_detail="DOCX v4 status failed") from exc

    document_kind = metadata.get("csm_document_kind", "unknown") if metadata else "unknown"
    placeholder_match_map_id = ""
    # Word can strip or fail to expose CSM customXml metadata after Save/Save As.
    # In that state the file is still a valid CSM anonymized working document if
    # it contains placeholders from the active map. Treat it as anon so the task
    # pane can restore from the current Office.js package instead of falling back
    # to a stale saved session file.
    if document_kind == "unknown" and req.map_id:
        try:
            payload = _load_map_any(req.map_id.strip())
            if _docx_contains_any_map_placeholder(raw, payload.get("replacements", [])):
                document_kind = "anon"
                placeholder_match_map_id = req.map_id.strip()
        except Exception:
            placeholder_match_map_id = ""

    return {
        "version": APP_VERSION,
        "is_csm_document": bool(metadata) or bool(placeholder_match_map_id),
        "metadata": metadata,
        "document_kind": document_kind,
        "metadata_missing_but_placeholder_match": bool(placeholder_match_map_id),
        "placeholder_match_map_id": placeholder_match_map_id,
    }





def _normalize_placeholder_merge_controls(controls: AnonymizationControls | None) -> Dict[str, str]:
    """Return SOURCE placeholder -> TARGET placeholder pairs from user controls."""
    if not controls:
        return {}
    pairs = controls.merge_placeholders or []
    out: Dict[str, str] = {}
    for item in pairs:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source") or item.get("from") or item.get("old") or "").strip()
        dst = str(item.get("target") or item.get("to") or item.get("new") or "").strip()
        if not re.fullmatch(r"\[[A-Z0-9_]+\]", src or ""):
            continue
        if not re.fullmatch(r"\[[A-Z0-9_]+\]", dst or ""):
            continue
        if src != dst:
            out[src] = dst
    return out


def _resolve_placeholder_merge_controls(
    requested: Dict[str, str],
    previous_replacements: List[dict],
    current_replacements: List[Replacement],
) -> tuple[Dict[str, str], List[str]]:
    """Resolve merge controls from the old map to placeholders in the remasked map.

    The reviewer selects placeholders from the preview of the previous map. A
    subsequent always/never/category rule can change placeholder numbering, so
    resolving by original value prevents valid merges from being silently lost.
    """
    if not requested:
        return {}, []

    current_by_placeholder = {r.placeholder: r for r in current_replacements}
    old_by_placeholder = {
        str(item.get("placeholder", "")): item
        for item in (previous_replacements or [])
        if item.get("placeholder")
    }
    current_by_original: Dict[str, List[Replacement]] = {}
    for repl in current_replacements:
        current_by_original.setdefault(str(repl.original), []).append(repl)

    unresolved: List[str] = []

    def resolve(placeholder: str) -> str | None:
        if placeholder in current_by_placeholder:
            return placeholder
        old = old_by_placeholder.get(placeholder)
        if not old:
            return None
        original = str(old.get("original", ""))
        candidates = current_by_original.get(original, [])
        if len(candidates) == 1:
            return candidates[0].placeholder
        return None

    resolved: Dict[str, str] = {}
    for src, dst in requested.items():
        new_src = resolve(src)
        new_dst = resolve(dst)
        if not new_src or not new_dst or new_src == new_dst:
            unresolved.append(f"{src} => {dst}")
            continue
        resolved[new_src] = new_dst
    return resolved, unresolved


def _replace_placeholders_in_docx_bytes(docx_bytes: bytes, replacements: Dict[str, str]) -> bytes:
    """Replace placeholder text in OOXML text-bearing parts.

    This is used only for manual placeholder merge in v0.6.1. The source and
    target placeholders are ASCII bracket tokens, so byte-safe XML text replace is
    sufficient and avoids modifying binary assets.
    """
    if not replacements:
        return docx_bytes
    content_re = re.compile(r"^(word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml|docProps/(core|app|custom)\.xml|word/settings\.xml|word/people\.xml)$", re.I)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if content_re.match(info.filename):
                    text = data.decode("utf-8", errors="ignore")
                    for src, dst in replacements.items():
                        text = text.replace(src, dst)
                    data = text.encode("utf-8")
                zout.writestr(info, data)
    return out.getvalue()


def _apply_placeholder_merges_to_replacements(replacements: List[Replacement], merge_map: Dict[str, str]) -> List[Replacement]:
    if not merge_map:
        return replacements
    by_placeholder: Dict[str, Replacement] = {r.placeholder: r for r in replacements}
    result: List[Replacement] = []
    skip: set[str] = set()
    for src, dst in merge_map.items():
        source = by_placeholder.get(src)
        target = by_placeholder.get(dst)
        if not source or not target:
            continue
        target.count = int(target.count or 1) + int(source.count or 1)
        skip.add(src)
    for r in replacements:
        if r.placeholder not in skip:
            result.append(r)
    result.sort(key=lambda r: (r.category, r.placeholder))
    return result

@app.post("/v4/map/preview", response_model=MapPreviewResponse)
def v4_map_preview(req: MapPreviewRequest):
    payload = _load_map_any(req.map_id.strip())
    reps = list(payload.get("replacements", []) or [])
    counts: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for item in reps:
        cat = str(item.get("category", ""))
        counts[cat] = counts.get(cat, 0) + int(item.get("count", 1) or 1)
        out.append({
            "category": cat,
            "original": str(item.get("original", "")),
            "placeholder": str(item.get("placeholder", "")),
            "count": int(item.get("count", 1) or 1),
        })
    out.sort(key=lambda x: (x.get("category", ""), x.get("placeholder", "")))
    return MapPreviewResponse(
        version=APP_VERSION,
        map_id=req.map_id,
        replacements=out,
        category_counts=counts,
        privacy_notice=(
            "Podgląd mapowań pokazuje wartości źródłowe wyłącznie lokalnie w panelu CSM. "
            "Nie jest to raport do wysłania poza komputer użytkownika."
        ),
        controls_supported=[
            "always_anonymize",
            "never_anonymize",
            "category_override",
            "merge_placeholders",
            "document_profiles",
        ],
        preview_generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        document_profiles=[{"id": k, "label": v.get("label"), "description": v.get("description"), "priority_categories": v.get("priority_categories", [])} for k, v in DOCUMENT_PROFILES.items()],
        selected_profile=_profile_report(req.document_profile, counts),
    )


class ManualRulesSaveRequest(BaseModel):
    level: str  # "global" | "client"
    client_id: str | None = None
    controls: AnonymizationControls


class ManualRulesDeleteRequest(BaseModel):
    level: str
    client_id: str | None = None


class ControlsPreviewRequest(BaseModel):
    map_id: str
    controls: AnonymizationControls | None = None
    client_id: str | None = None
    use_saved_rules: bool = True


@app.get("/v4/rules")
def v4_rules_get(client_id: str | None = None):
    """Locally saved manual rules (firm-wide and per-client). Local panel only."""
    out: Dict[str, Any] = {
        "version": APP_VERSION,
        "global": rules_store.load_rules("global"),
        "clients": rules_store.list_clients(),
        "privacy_notice": "Reguły są zapisane wyłącznie lokalnie i mogą zawierać jawne dane. Nie wysyłaj ich poza komputer.",
    }
    if client_id:
        out["client_id"] = rules_store.client_slug(client_id)
        out["client"] = rules_store.load_rules("client", client_id)
    return out


@app.post("/v4/rules")
def v4_rules_save(req: ManualRulesSaveRequest):
    if req.level not in {"global", "client"}:
        raise _http_error(400, f"Unsupported rules level: {req.level}", public_detail="Nieznany poziom reguł.")
    try:
        saved = rules_store.save_rules(req.level, req.controls.model_dump(), req.client_id)
    except ValueError as exc:
        raise _http_error(400, str(exc), public_detail=str(exc)) from exc
    return {"version": APP_VERSION, "level": req.level, "client_id": rules_store.client_slug(req.client_id or "") or None, "controls": saved}


@app.post("/v4/rules/delete")
def v4_rules_delete(req: ManualRulesDeleteRequest):
    if req.level not in {"global", "client"}:
        raise _http_error(400, f"Unsupported rules level: {req.level}", public_detail="Nieznany poziom reguł.")
    try:
        deleted = rules_store.delete_rules(req.level, req.client_id)
    except ValueError as exc:
        raise _http_error(400, str(exc), public_detail=str(exc)) from exc
    return {"version": APP_VERSION, "deleted": deleted}


@app.post("/v4/controls/preview")
def v4_controls_preview(req: ControlsPreviewRequest):
    """Dry-run of manual rules against the session's original document.

    Returns per-rule effects (match counts, suppressed detections with local
    context snippets, checksum-protected detections a rule would touch, dead
    rules) without generating a new anonymized copy. Context snippets contain
    fragments of the source document and stay on this machine.
    """
    payload = _load_map_any(req.map_id.strip())
    original_b64 = payload.get("original_docx_base64")
    if not original_b64:
        raise _http_error(404, "Brak lokalnej kopii oryginalnego DOCX dla tej mapy.", public_detail="Brak lokalnej kopii oryginalnego DOCX dla tej mapy.")
    effective_controls = _effective_controls_dict(req.controls, req.client_id, req.use_saved_rules)
    try:
        text = docx_package_to_text(base64_to_bytes(original_b64))
        _, effects = collect_findings_with_controls_report(text, effective_controls or {})
    except Exception as exc:
        raise _http_error(400, f"Controls preview failed: {exc}", public_detail="Podgląd skutków reguł nie powiódł się.") from exc
    audit_log("controls_preview", map_id=req.map_id, entities_count=_summarize_anonymization_controls(effective_controls).get("total", 0))
    return {
        "version": APP_VERSION,
        "map_id": req.map_id,
        "controls_summary": _summarize_anonymization_controls(effective_controls),
        "saved_rules": rules_store.saved_rules_summary(req.client_id) if req.use_saved_rules else {},
        "effects": effects,
        "privacy_notice": "Podgląd skutków reguł działa wyłącznie lokalnie i może pokazywać fragmenty dokumentu. Nie jest to raport do wysłania poza komputer.",
    }


@app.post("/v4/current/remask-session", response_model=DocxV4CurrentPrepareResponse)
def v4_current_remask_session(req: DocxV4RemaskSessionRequest):
    """Regenerate *_CSM_anon.docx from the original session snapshot using user controls.

    This is the v0.6.1 manual-review path: after previewing mappings the user can
    add always/never/category controls and generate a new anonymized working copy
    without touching the original Word document.
    """
    old_map_id = (req.map_id or "").strip()
    profile = _normalize_document_profile(req.document_profile)
    effective_controls = _effective_controls_dict(req.controls, req.client_id, req.use_saved_rules)
    controls_summary = _summarize_anonymization_controls(effective_controls)
    saved_rules_summary = rules_store.saved_rules_summary(req.client_id) if req.use_saved_rules else {}
    payload = _load_map_any(old_map_id)
    original_b64 = payload.get("original_docx_base64")
    if not original_b64:
        raise _http_error(404, "Brak lokalnej kopii oryginalnego DOCX dla tej mapy.", public_detail="Brak lokalnej kopii oryginalnego DOCX dla tej mapy.")
    placeholder_restore_overrides: Dict[str, Any] = {}
    try:
        raw = base64_to_bytes(original_b64)
        anon_bytes, replacements, package_report = mask_docx_preserving_tc(raw, mode="preserve", controls=effective_controls)
        requested_merge_map = _normalize_placeholder_merge_controls(req.controls)
        merge_map, unresolved_merges = _resolve_placeholder_merge_controls(
            requested_merge_map,
            list(payload.get("replacements", []) or []),
            replacements,
        )
        if unresolved_merges:
            detail = "Nie udało się jednoznacznie odnaleźć placeholderów do scalenia: " + ", ".join(unresolved_merges[:10])
            raise ValueError(detail)
        if merge_map:
            placeholder_restore_overrides = build_placeholder_restore_overrides(anon_bytes, replacements, merge_map)
            anon_bytes = _replace_placeholders_in_docx_bytes(anon_bytes, merge_map)
            replacements = _apply_placeholder_merges_to_replacements(replacements, merge_map)
            manual_report = package_report.setdefault("manual_controls", {})
            manual_report["merged_placeholders"] = len(merge_map)
            manual_report["restore_overrides"] = {
                placeholder: len(originals)
                for placeholder, originals in placeholder_restore_overrides.items()
            }
    except Exception as exc:
        public_detail = str(exc) if str(exc).startswith("Nie udało się jednoznacznie") else "Remask session failed"
        raise _http_error(400, f"Remask session failed: {exc}", public_detail=public_detail) from exc
    source_hash = _canonical_docx_hash(raw)
    map_id = save_map(
        replacements,
        source_hash=source_hash,
        original_docx_base64=original_b64,
        require_install_backup=True,
        extra_payload={"placeholder_restore_overrides": placeholder_restore_overrides} if placeholder_restore_overrides else None,
    )
    session_id = map_id
    session_dir = _sessions_dir() / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename_stem(req.filename or payload.get("original_filename") or "dokument", "dokument")
    original_filename = f"{stem}_oryginal.docx"
    anon_filename = f"{stem}_CSM_anon.docx"
    restored_filename = f"{stem}_CSM_jawny.docx"
    metadata = {
        "csm_version": APP_VERSION,
        "csm_document_kind": "anon",
        "csm_mode": "negotiation-docx-remask",
        "document_profile": profile,
        "session_id": session_id,
        "map_id": map_id,
        "previous_map_id": old_map_id,
        "original_hash": source_hash,
        "original_filename": req.filename or payload.get("original_filename") or "dokument.docx",
        "anon_filename": anon_filename,
        "restored_filename": restored_filename,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "anon_content_hash": _canonical_docx_hash(anon_bytes),
        "anon_text_hash": _docx_visible_text_hash(anon_bytes),
    }
    anon_with_metadata = _docx_upsert_csm_metadata(anon_bytes, metadata)
    original_path = _write_session_file(session_dir, original_filename, raw)
    anon_path = _write_session_file(session_dir, anon_filename, anon_with_metadata)
    _write_json(session_dir / "manifest.json", metadata)
    if req.controls:
        _write_json(session_dir / "user_controls.json", req.controls.model_dump())
    counts = category_counts(replacements)
    uncertain_review_candidates = collect_uncertain_review_candidates(docx_package_to_text(raw), replacements, limit=25)
    review_warnings, review_status = _run_review_mode(docx_package_to_text(anon_bytes), replacements, req.review_mode)
    full_warnings = collect_ambiguous_person_warnings(replacements) + list(package_report.get("warnings", [])) + review_warnings
    for prepare_path_warning in metadata.get("prepare_path_warnings", []) or []:
        full_warnings.append(f"Nie zapamiętano ścieżki oryginału do automatycznego nadpisania: {prepare_path_warning}.")
    negotiation_report = _v4_negotiation_report(raw, anon_bytes, None, package_report, None)
    anonymization_report = _build_anonymization_report(replacements, package_report, full_warnings, anon_with_metadata, document_profile=profile, review_status=review_status)
    report_prepare_path = session_dir / "report_prepare.json"
    _write_json(report_prepare_path, {"version": APP_VERSION, "session_id": session_id, "map_id": map_id, "previous_map_id": old_map_id, "negotiation_report": negotiation_report, "anonymization_report": anonymization_report, "warnings": full_warnings, "category_counts": counts, "controls_applied": bool(effective_controls), "controls_summary": controls_summary, "controls_effects": package_report.get("manual_controls_effects", {}), "saved_rules": saved_rules_summary, "document_profile": profile, "uncertain_review_candidates_count": len(uncertain_review_candidates), **_review_response_fields(review_status)})
    opened, open_error = _open_file_path(anon_path, enabled=bool(req.open_file))
    audit_log("mask", map_id=map_id, mode="docx_v4_current_remask_session", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), engine_version=TC_ENGINE_VERSION, warnings_count=len(full_warnings), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return DocxV4CurrentPrepareResponse(
        version=APP_VERSION, engine_version=TC_ENGINE_VERSION, map_id=map_id, session_id=session_id,
        suggested_filename=anon_filename, original_path=str(original_path), anon_path=str(anon_path),
        opened_file=opened, open_error=open_error, category_counts=counts, entities_count=len(replacements),
        coverage=package_report.get("coverage", {}), revisions_summary=package_report.get("revisions_summary", {}),
        negotiation_report=negotiation_report, warnings=full_warnings, anonymization_report=anonymization_report,
        report_prepare_path=str(report_prepare_path), controls_applied=bool(effective_controls), controls_summary=controls_summary, document_profile=profile,
        uncertain_review_candidates=uncertain_review_candidates,
        controls_effects=package_report.get("manual_controls_effects", {}),
        saved_rules=saved_rules_summary,
        **_review_response_fields(review_status)
    )


@app.post("/v4/current/prepare", response_model=DocxV4CurrentPrepareResponse)
def v4_current_prepare(req: DocxV4CurrentPrepareRequest):
    """Create and open an anonymized negotiation DOCX from the active Word file.

    The user does not manually select or download files. The add-in sends the
    current document package, CSM writes a session folder, embeds CSM metadata in
    the anonymized copy, and attempts to open the copy in Word.
    """
    mode = (req.mode or "preserve").strip()
    if mode not in {"preserve", "accept_then_mask", "reject_then_mask"}:
        raise _http_error(400, f"Unsupported v4 DOCX mode: {mode}", public_detail="Unsupported v4 DOCX mode")
    profile = _normalize_document_profile(req.document_profile)
    effective_controls = _effective_controls_dict(req.controls, req.client_id, req.use_saved_rules)
    controls_summary = _summarize_anonymization_controls(effective_controls)
    saved_rules_summary = rules_store.saved_rules_summary(req.client_id) if req.use_saved_rules else {}
    try:
        raw = base64_to_bytes(req.docx_base64)
        anon_bytes, replacements, package_report = mask_docx_preserving_tc(raw, mode=mode, controls=effective_controls)
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v4_current_prepare", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v4_current_prepare", status="failed")
        raise _http_error(400, f"DOCX v4 current prepare failed: {exc}", public_detail="DOCX v4 current prepare failed") from exc

    source_hash = _canonical_docx_hash(raw)
    map_id = save_map(replacements, source_hash=source_hash, original_docx_base64=req.docx_base64, require_install_backup=True)
    session_id = map_id
    session_dir = _sessions_dir() / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename_stem(req.filename, "dokument")
    original_filename = f"{stem}_oryginal.docx"
    anon_filename = f"{stem}_CSM_anon.docx"
    restored_filename = f"{stem}_CSM_jawny.docx"
    metadata = {
        "csm_version": APP_VERSION,
        "csm_document_kind": "anon",
        "csm_mode": "negotiation-docx",
        "document_profile": profile,
        "session_id": session_id,
        "map_id": map_id,
        "original_hash": source_hash,
        "original_filename": req.filename or "dokument.docx",
        "anon_filename": anon_filename,
        "restored_filename": restored_filename,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "anon_content_hash": _canonical_docx_hash(anon_bytes),
        "anon_text_hash": _docx_visible_text_hash(anon_bytes),
    }
    # Store the original Word file path so restore can write back to it.
    word_source_path = (req.word_source_path or "").strip()
    word_source_name = (req.word_source_name or req.filename or "").strip()
    if word_source_path:
        safe_source_path, source_path_warning = _safe_original_docx_target(word_source_path)
        if safe_source_path:
            metadata["word_source_path"] = str(safe_source_path)
        else:
            full_warnings_pending = metadata.setdefault("prepare_path_warnings", [])
            full_warnings_pending.append(source_path_warning or "nie udało się zweryfikować ścieżki oryginału")
    anon_with_metadata = _docx_upsert_csm_metadata(anon_bytes, metadata)
    original_path = _write_session_file(session_dir, original_filename, raw)
    anon_path = _write_session_file(session_dir, anon_filename, anon_with_metadata)
    _write_json(session_dir / "manifest.json", metadata)
    counts = category_counts(replacements)
    uncertain_review_candidates = collect_uncertain_review_candidates(docx_package_to_text(raw), replacements, limit=25)
    review_warnings, review_status = _run_review_mode(docx_package_to_text(anon_bytes), replacements, req.review_mode)
    full_warnings = collect_ambiguous_person_warnings(replacements) + list(package_report.get("warnings", [])) + review_warnings
    for prepare_path_warning in metadata.get("prepare_path_warnings", []) or []:
        full_warnings.append(f"Nie zapamiętano ścieżki oryginału do automatycznego nadpisania: {prepare_path_warning}.")
    negotiation_report = _v4_negotiation_report(raw, anon_bytes, None, package_report, None)
    if len(raw) <= 500_000:
        try:
            rt_bytes, rt_report = restore_docx_preserving_tc(anon_bytes, [asdict(r) for r in replacements])
            rt_bytes, rt_image_report = restore_redacted_images_from_original(rt_bytes, raw)
            if any(int(v or 0) for v in rt_image_report.values()):
                rt_report["image_restore_report"] = rt_image_report
            negotiation_report["immediate_roundtrip"] = _docx_diff_summary(raw, rt_bytes)
            negotiation_report["immediate_restore_report"] = rt_report
            if not negotiation_report["immediate_roundtrip"].get("identical"):
                full_warnings.append("Kontrola roundtrip: prepare→restore is not canonical-identical; review diff report before legal negotiation use.")
        except Exception as exc:
            full_warnings.append(f"Kontrola roundtrip failed: {_sanitize_error_detail(str(exc))}")
    else:
        negotiation_report["immediate_roundtrip"] = {"skipped": True, "reason": "document too large for inline roundtrip check"}
    anonymization_report = _build_anonymization_report(replacements, package_report, full_warnings, anon_with_metadata, document_profile=profile, review_status=review_status)
    report_prepare_path = session_dir / "report_prepare.json"
    _write_json(report_prepare_path, {"version": APP_VERSION, "session_id": session_id, "map_id": map_id, "negotiation_report": negotiation_report, "anonymization_report": anonymization_report, "warnings": full_warnings, "category_counts": counts, "controls_applied": bool(effective_controls), "controls_summary": controls_summary, "controls_effects": package_report.get("manual_controls_effects", {}), "saved_rules": saved_rules_summary, "document_profile": profile, "uncertain_review_candidates_count": len(uncertain_review_candidates), **_review_response_fields(review_status)})
    opened, open_error = _open_file_path(anon_path, enabled=bool(req.open_file))
    # Close the original document in Word after the anon copy has had time to open.
    # The original has been fully saved to the session folder. Match by full path
    # when available, or by unique filename fallback when Office.js hides the path.
    word_close_report = {}
    if word_source_path or word_source_name:
        word_close_report = _schedule_word_close_after_open(word_source_path, doc_name=word_source_name, save_mode="save_then_close")
    audit_log("mask", map_id=map_id, mode="docx_v4_current_prepare", source_hash=source_hash, category_counts=counts, entities_count=len(replacements), engine_version=TC_ENGINE_VERSION, warnings_count=len(full_warnings), llm_findings_count=review_status.get("bielik_findings_count", 0))
    return DocxV4CurrentPrepareResponse(
        version=APP_VERSION,
        engine_version=TC_ENGINE_VERSION,
        map_id=map_id,
        session_id=session_id,
        suggested_filename=anon_filename,
        original_path=str(original_path),
        anon_path=str(anon_path),
        opened_file=opened,
        open_error=open_error,
        category_counts=counts,
        entities_count=len(replacements),
        coverage=package_report.get("coverage", {}),
        revisions_summary=package_report.get("revisions_summary", {}),
        negotiation_report=negotiation_report,
        warnings=full_warnings,
        anonymization_report=anonymization_report,
        report_prepare_path=str(report_prepare_path),
        controls_applied=bool(effective_controls), controls_summary=controls_summary, document_profile=profile,
        word_close_report=word_close_report,
        uncertain_review_candidates=uncertain_review_candidates,
        controls_effects=package_report.get("manual_controls_effects", {}),
        saved_rules=saved_rules_summary,
        **_review_response_fields(review_status),
    )


@app.post("/v4/current/restore", response_model=DocxV4CurrentRestoreResponse)
def v4_current_restore(req: DocxV4CurrentRestoreRequest):
    """Restore the active CSM anonymized DOCX from the Office.js document package."""
    try:
        raw = base64_to_bytes(req.docx_base64)
        return _restore_v4_docx_bytes(
            raw,
            filename=req.filename,
            map_id=req.map_id,
            session_id=req.session_id,
            open_file=req.open_file,
            mode="docx_v4_current_restore",
            source_mode="officejs-current-package",
            word_anon_path=req.word_anon_path,
            word_anon_name=req.word_anon_name or req.filename,
        )
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v4_current_restore", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except Exception as exc:
        audit_log("error", mode="docx_v4_current_restore", status="failed")
        detail = _sanitize_error_detail(str(exc))
        raise _http_error(400, f"DOCX v4 current restore failed: {detail}", public_detail=f"DOCX v4 current restore failed: {detail}") from exc


@app.post("/v4/session/restore-last", response_model=DocxV4CurrentRestoreResponse)
def v4_session_restore_last(req: DocxV4PathRestoreRequest):
    """Restore the last saved *_CSM_anon.docx from the CSM session folder.

    This deliberately bypasses the current Office.js document package. Word can
    show the anonymized document while the task pane still belongs to the
    original document; in that case /v4/current/restore correctly rejects the
    original package. This endpoint uses the saved session file instead.
    """
    try:
        anon_path = _resolve_session_docx_path(req.anon_path, session_id=req.session_id, map_id=req.map_id)
        raw, source_mode, source_warning = _read_best_available_anon_docx(anon_path)
        return _restore_v4_docx_bytes(
            raw,
            filename=anon_path.name,
            map_id=req.map_id,
            session_id=req.session_id,
            open_file=req.open_file,
            mode="docx_v4_session_restore_last",
            source_path=anon_path,
            source_mode=source_mode,
            source_warning=source_warning,
            require_changes=req.require_changes,
            word_anon_path=req.word_anon_path,
            word_anon_name=req.word_anon_name or anon_path.name,
        )
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Nie znaleziono zapisanego pliku *_CSM_anon.docx w sesji CSM.") from exc
    except DocxXmlTooLargeError as exc:
        audit_log("error", mode="docx_v4_session_restore_last", status="rejected_too_large")
        raise _http_error(413, str(exc), public_detail="DOCX package XML zbyt duży po dekompresji") from exc
    except CsmFileLockedError as exc:
        audit_log("error", mode="docx_v4_session_restore_last", status="locked")
        raise _http_error(423, str(exc), public_detail=str(exc)) from exc
    except CsmStaleAnonInputError as exc:
        audit_log("error", mode="docx_v4_session_restore_last", status="stale_anon_input")
        raise _http_error(409, str(exc), public_detail=str(exc)) from exc
    except Exception as exc:
        audit_log("error", mode="docx_v4_session_restore_last", status="failed")
        detail = _sanitize_error_detail(str(exc))
        raise _http_error(400, f"DOCX v4 session restore failed: {detail}", public_detail=f"DOCX v4 session restore failed: {detail}") from exc


@app.post("/v4/session/open-file")
def v4_session_open_file(req: DocxV4OpenPathRequest):
    raw_path = Path(req.path)
    try:
        path = raw_path.resolve()
        base = _sessions_dir().resolve()
        if base not in path.parents and path != base:
            raise ValueError("Path outside CSM sessions directory")
        if not path.exists():
            raise FileNotFoundError(str(path))
        opened, error = _open_file_path(path, enabled=True)
        return {"version": APP_VERSION, "opened_file": opened, "open_error": error, "path": str(path)}
    except Exception as exc:
        raise _http_error(400, f"Open file failed: {exc}", public_detail="Open file failed") from exc


@app.post("/original_docx_package")
def original_docx_package_endpoint(req: OriginalSnapshotRequest):
    try:
        payload = load_map(req.map_id)
    except FileNotFoundError:
        try:
            payload = load_install_backup(req.map_id)
        except FileNotFoundError as exc:
            raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    original_docx_base64 = payload.get("original_docx_base64")
    if not original_docx_base64:
        try:
            payload = load_install_backup(req.map_id)
            original_docx_base64 = payload.get("original_docx_base64")
        except Exception:
            pass
    if not original_docx_base64:
        raise _http_error(404, "No original DOCX package snapshot stored for this map", public_detail="Brak lokalnej kopii DOCX dla tej mapy.")
    return {"map_id": payload.get("map_id", req.map_id), "docx_base64": original_docx_base64, "version": APP_VERSION}

@app.post("/original_ooxml")
def original_ooxml_endpoint(req: OriginalSnapshotRequest):
    """Return the original OOXML snapshot stored locally for emergency recovery.

    This endpoint is intended only for the Word add-in during restore/recovery.
    It is exposed only on localhost by the local API.
    """
    try:
        payload = load_map(req.map_id)
    except FileNotFoundError:
        try:
            payload = load_install_backup(req.map_id)
        except FileNotFoundError as exc:
            raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    original_ooxml = payload.get("original_ooxml")
    if not original_ooxml:
        try:
            payload = load_install_backup(req.map_id)
            original_ooxml = payload.get("original_ooxml")
        except Exception:
            pass
    if not original_ooxml:
        raise _http_error(404, "No original OOXML snapshot stored for this map", public_detail="Brak lokalnej kopii struktury dokumentu Word dla tej mapy.")
    return {
        "map_id": payload.get("map_id", req.map_id),
        "ooxml": original_ooxml,
        "version": APP_VERSION,
    }


@app.post("/backup_latest")
def backup_latest_endpoint(req: LatestBackupRequest):
    map_id = req.map_id or latest_install_backup_id()
    if not map_id:
        raise _http_error(404, "No install-folder backup found", public_detail="Nie znaleziono lokalnej kopii awaryjnej.")
    try:
        payload = load_install_backup(map_id)
    except FileNotFoundError as exc:
        raise _http_error(404, str(exc), public_detail="Zasób lokalny nie został odnaleziony.") from exc
    manifest = payload.get("manifest", {})
    return {"map_id": map_id, "version": APP_VERSION, "manifest": manifest}


@app.post("/backup_list")
def backup_list_endpoint():
    return {"version": APP_VERSION, "backups": list_install_backups()}


# ── Service management endpoints (launcher panel in taskpane) ─────────────────
# These let the Word add-in trigger the same operations as the desktop CSM.ps1
# launcher window (START / STOP / CLEAN / NAPRAW / DIAGNOZA).
# Each endpoint runs the corresponding PowerShell script via Start-Process so
# it opens in its own window (matching the existing desktop launcher behaviour).
# All endpoints require the standard CSM API token.

from fastapi.responses import StreamingResponse

def _tools_dir() -> Path:
    """Return the tools/ directory relative to the CSM install root (BASE_DIR)."""
    from security import BASE_DIR as _BASE
    return _BASE / "tools"


def _run_service_script(script_name: str, extra_args: list[str] | None = None) -> dict:
    """Launch a PowerShell script from the tools directory in a new window.

    Mirrors the Start-CsmScript function in CSM.ps1.
    Returns immediately (non-blocking) — the script window is visible to the user.
    """
    tools = _tools_dir()
    script_path = tools / script_name
    if not script_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Script not found: {script_name}. CSM may not be fully installed.",
        )
    ps_exe = _powershell_exe() or "powershell.exe"
    cmd = [
        ps_exe,
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(script_path),
    ]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.Popen(
            cmd,
            cwd=str(tools.parent),  # run from install root
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )
        return {"ok": True, "script": script_name}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch {script_name}: {exc}") from exc


@app.post("/service/start")
def service_start():
    """Launch start-claude-safe-mode.ps1 (same as START button in CSM.ps1)."""
    return _run_service_script("start-claude-safe-mode.ps1", ["-NoOpenWord", "-NonInteractive"])


@app.post("/service/stop")
def service_stop():
    """Launch stop-claude-safe-mode.ps1 (same as STOP button in CSM.ps1)."""
    return _run_service_script("stop-claude-safe-mode.ps1")


@app.post("/service/repair")
def service_repair():
    """Launch repair-csm.ps1 (same as NAPRAW button in CSM.ps1)."""
    return _run_service_script("repair-csm.ps1")


@app.post("/service/clean")
def service_clean():
    """Launch CSM-CLEAN.ps1 -Force (same as CLEAN button in CSM.ps1).

    WARNING: closes Microsoft Word.  The taskpane will disappear.
    """
    return _run_service_script("CSM-CLEAN.ps1", ["-Force"])


@app.post("/service/uninstall")
def service_uninstall():
    """Launch uninstall-csm.ps1 in a new elevated console window.

    The script handles its own UAC self-elevation (Start-Process -Verb RunAs).
    Returns immediately — the uninstall window runs independently.
    WARNING: removes the CSM installation, closes Word, and deletes all CSM data.
    """
    return _run_service_script("uninstall-csm.ps1")


@app.get("/service/diagnose")
def service_diagnose(request: Request):
    """Run diagnose-csm.ps1 and stream its stdout back line-by-line as SSE.

    The taskpane opens an EventSource to this endpoint and displays the log
    inside the panel without opening a separate PowerShell window.
    The CSM API token is passed as X-CSM-Token query param because
    EventSource / fetch streaming in WebView2 may not support custom headers.
    The middleware reads X-CSM-Token from the query string as a fallback.
    """
    tools = _tools_dir()
    script_path = tools / "diagnose-csm.ps1"
    if not script_path.exists():
        raise HTTPException(status_code=503, detail="diagnose-csm.ps1 not found")

    ps_exe = _powershell_exe() or "powershell.exe"
    cmd = [
        ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-NonInteractive", "-File", str(script_path),
    ]

    def generate():
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(tools.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                # SSE format: "data: <line>\n\n"
                yield f"data: {line.rstrip()}\n\n"
            proc.wait()
            yield f"data: [DIAGNOZA zakończona — kod wyjścia: {proc.returncode}]\n\n"
            yield "data: __END__\n\n"
        except Exception as exc:
            yield f"data: [BŁĄD: {exc}]\n\n"
            yield "data: __END__\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
