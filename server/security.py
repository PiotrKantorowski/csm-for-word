from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(os.environ.get("CSM_BASE_DIR", r"C:\CSM" if os.name == "nt" else str(Path.home() / "CSM")))
MAPS_DIR = BASE_DIR / "maps"
RUNTIME_DIR = BASE_DIR / "runtime"
AUDIT_DIR = BASE_DIR / "audit"
CONFIG_PATH = BASE_DIR / "config.json"
TOKEN_PATH = RUNTIME_DIR / "api-token.txt"
AUDIT_LOG_PATH = AUDIT_DIR / "audit.jsonl"

DEFAULT_CONFIG: Dict[str, Any] = {
    "map_retention_days": 30,
    "snapshot_retention_days": 30,
    "audit_log_retention_days": 90,
    "max_text_bytes": 2_000_000,
    "max_docx_xml_bytes": 50_000_000,
}


def csm_mode() -> str:
    value = os.environ.get("CSM_MODE", "prod").strip().lower()
    return "dev" if value == "dev" else "prod"


def csm_dev_mode() -> bool:
    return csm_mode() == "dev"


def ensure_dirs() -> None:
    for path in (BASE_DIR, MAPS_DIR, RUNTIME_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config is not an object")
    except Exception:
        data = {}
    config = dict(DEFAULT_CONFIG)
    config.update({k: data.get(k, v) for k, v in DEFAULT_CONFIG.items()})
    changed = any(data.get(k) != config[k] for k in DEFAULT_CONFIG)
    if changed:
        CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return config


def get_api_token() -> str | None:
    token = os.environ.get("CSM_API_TOKEN")
    if token:
        return token.strip()
    try:
        if TOKEN_PATH.exists():
            value = TOKEN_PATH.read_text(encoding="utf-8-sig").strip()
            return value or None
    except Exception:
        return None
    return None


def token_matches(provided: str | None) -> bool:
    expected = get_api_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), str(expected))


def _cutoff(days: int) -> float:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).timestamp()


def cleanup_sensitive_files() -> Dict[str, int]:
    ensure_dirs()
    config = load_config()
    report = {"maps_removed": 0, "audit_lines_removed": 0}
    map_days = int(config.get("map_retention_days", 30) or 30)
    cutoff = _cutoff(map_days)
    for path in MAPS_DIR.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                report["maps_removed"] += 1
        except Exception:
            pass

    # Keep audit logs metadata-only, and trim old lines rather than deleting the whole file.
    audit_days = int(config.get("audit_log_retention_days", 90) or 90)
    audit_cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, audit_days))
    if AUDIT_LOG_PATH.exists():
        kept = []
        removed = 0
        for line in AUDIT_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
                ts = datetime.fromisoformat(str(item.get("timestamp", "")).replace("Z", "+00:00"))
                if ts >= audit_cutoff:
                    kept.append(line)
                else:
                    removed += 1
            except Exception:
                # Keep malformed lines defensively; they should not contain PII, but avoid accidental data loss.
                kept.append(line)
        if removed:
            AUDIT_LOG_PATH.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            report["audit_lines_removed"] = removed
    return report


def audit_log(
    event: str,
    *,
    map_id: str | None = None,
    mode: str | None = None,
    source_hash: str | None = None,
    category_counts: Dict[str, int] | None = None,
    entities_count: int | None = None,
    restore_report: Dict[str, Any] | None = None,
    status: str = "ok",
    engine_version: str | None = None,
    warnings_count: int | None = None,
    llm_findings_count: int | None = None,
) -> None:
    ensure_dirs()
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        "status": status,
    }
    if map_id:
        record["map_id"] = map_id
    if mode:
        record["mode"] = mode
    if engine_version:
        record["engine_version"] = engine_version
    if source_hash:
        record["document_hash"] = source_hash
    if category_counts:
        record["category_counts"] = category_counts
    if entities_count is not None:
        record["entities_count"] = int(entities_count)
    if warnings_count is not None:
        record["warnings_count"] = int(warnings_count)
    if llm_findings_count is not None:
        record["llm_findings_count"] = int(llm_findings_count)
    if restore_report:
        record["restore_complete"] = not bool(restore_report.get("missing_total") or restore_report.get("leftover_total_after_restore") or restore_report.get("unknown_total"))
        record["restore_report_summary"] = {
            "restored_occurrences": restore_report.get("restored_occurrences"),
            "missing_total": restore_report.get("missing_total"),
            "leftover_total_after_restore": restore_report.get("leftover_total_after_restore"),
            "unknown_total": restore_report.get("unknown_total"),
        }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


_AUDIT_ALLOWED_FIELDS: set[str] = {
    "timestamp", "event", "status", "map_id", "mode", "engine_version",
    "document_hash", "category_counts", "entities_count", "warnings_count",
    "llm_findings_count", "restore_complete", "restore_report_summary",
}


def read_audit_tail(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the last `limit` audit-log entries, filtered to non-PII fields.

    The audit log is already PII-free by design (no original values, no
    placeholders, only counts and hashes), but we still pass each record
    through an allow-list so an accidentally-added field never leaks through
    this endpoint.
    """
    if not AUDIT_LOG_PATH.exists():
        return []
    try:
        raw = AUDIT_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    n = max(1, min(int(limit), 500))
    tail = raw[-n:] if len(raw) > n else raw
    out: List[Dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        safe = {k: v for k, v in item.items() if k in _AUDIT_ALLOWED_FIELDS}
        out.append(safe)
    return out
