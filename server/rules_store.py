"""Persistent manual-rule store for CSM.

Three levels of manual controls:
- session  — sent by the panel per remask/prepare request (not stored here),
- client   — rules for one client/matter, reused across that client's documents,
- global   — firm-wide rules (e.g. the law firm's own name in "never").

Client and global rules are stored locally under BASE_DIR/manual_rules and
protected with the same payload envelope as masking maps (DPAPI on Windows).
Rules can contain plain personal data, so they must never leave the machine.

merge_placeholders is intentionally not persisted: placeholder ids are
map-specific and only make sense for the session that produced the map.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

try:
    from redactor import _protect_payload, _unprotect_payload
    from security import BASE_DIR, audit_log
except ImportError:  # pragma: no cover - package-style import fallback
    from .redactor import _protect_payload, _unprotect_payload
    from .security import BASE_DIR, audit_log

RULES_DIR = BASE_DIR / "manual_rules"
GLOBAL_RULES_FILE = "global.json"
_CLIENT_SLUG_RE = re.compile(r"[^a-z0-9_-]+")

_PERSISTED_KEYS = ("always", "never", "category_overrides")


def client_slug(client_id: str) -> str:
    slug = _CLIENT_SLUG_RE.sub("-", (client_id or "").strip().casefold()).strip("-")
    return slug[:80]


def _rules_path(level: str, client_id: str | None = None) -> Path:
    if level == "global":
        return RULES_DIR / GLOBAL_RULES_FILE
    if level == "client":
        slug = client_slug(client_id or "")
        if not slug:
            raise ValueError("Brak identyfikatora klienta dla reguł na poziomie klienta.")
        return RULES_DIR / "clients" / f"{slug}.json"
    raise ValueError(f"Nieznany poziom reguł: {level}")


def _empty_controls() -> Dict[str, Any]:
    return {"always": [], "never": [], "category_overrides": {}}


def _sanitize_controls(controls: Dict[str, Any] | None) -> Dict[str, Any]:
    """Keep only persistable rule fields with their expected shapes."""
    src = controls or {}
    out = _empty_controls()
    always = src.get("always") or src.get("always_anonymize") or []
    if isinstance(always, list):
        for item in always:
            if isinstance(item, str) and item.strip():
                out["always"].append({"value": item.strip(), "category": "MANUAL"})
            elif isinstance(item, dict):
                value = str(item.get("value") or item.get("text") or "").strip()
                if value:
                    out["always"].append({
                        "value": value,
                        "category": str(item.get("category") or "MANUAL").strip().upper()[:40] or "MANUAL",
                    })
    never = src.get("never") or src.get("never_anonymize") or []
    if isinstance(never, list):
        for item in never:
            if isinstance(item, str) and item.strip():
                out["never"].append(item.strip())
            elif isinstance(item, dict):
                value = str(item.get("value") or "").strip()
                if value:
                    entry: Dict[str, Any] = {"value": value}
                    if item.get("force") or item.get("confirmed"):
                        entry["force"] = True
                    out["never"].append(entry)
    overrides = src.get("category_overrides")
    if isinstance(overrides, dict):
        for key, val in overrides.items():
            k = str(key).strip()
            v = str(val).strip().upper()[:40]
            if k and v:
                out["category_overrides"][k] = v
    return out


def load_rules(level: str, client_id: str | None = None) -> Dict[str, Any]:
    path = _rules_path(level, client_id)
    if not path.exists():
        return _empty_controls()
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = _unprotect_payload(envelope)
    return _sanitize_controls(payload.get("controls"))


def save_rules(level: str, controls: Dict[str, Any] | None, client_id: str | None = None) -> Dict[str, Any]:
    path = _rules_path(level, client_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_controls(controls)
    payload = {"level": level, "client_id": client_slug(client_id or "") or None, "controls": sanitized}
    envelope = _protect_payload(payload)
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_log(
        "manual_rules_saved",
        mode=f"{level}:{client_slug(client_id or '') or '-'}",
        entities_count=len(sanitized["always"]) + len(sanitized["never"]) + len(sanitized["category_overrides"]),
    )
    return sanitized


def delete_rules(level: str, client_id: str | None = None) -> bool:
    path = _rules_path(level, client_id)
    if not path.exists():
        return False
    path.unlink()
    audit_log("manual_rules_deleted", mode=f"{level}:{client_slug(client_id or '') or '-'}")
    return True


def list_clients() -> List[str]:
    clients_dir = RULES_DIR / "clients"
    if not clients_dir.exists():
        return []
    return sorted(p.stem for p in clients_dir.glob("*.json"))


def merge_controls(session_controls: Dict[str, Any] | None, client_id: str | None = None) -> Dict[str, Any]:
    """Combine saved global + client rules with this session's controls.

    Lists are concatenated (session last), duplicate always/never values are
    dropped case-insensitively keeping the first occurrence. For category
    overrides the more specific level wins (session > client > global).
    merge_placeholders is taken only from the session controls.
    """
    layers = [load_rules("global")]
    if client_id and client_slug(client_id):
        layers.append(load_rules("client", client_id))
    layers.append(_sanitize_controls(session_controls))

    merged: Dict[str, Any] = _empty_controls()
    seen_always: set[str] = set()
    seen_never: set[str] = set()
    for layer in layers:
        for item in layer["always"]:
            key = item["value"].casefold()
            if key not in seen_always:
                seen_always.add(key)
                merged["always"].append(item)
        for item in layer["never"]:
            value = item if isinstance(item, str) else item.get("value", "")
            key = str(value).casefold()
            if key not in seen_never:
                seen_never.add(key)
                merged["never"].append(item)
        merged["category_overrides"].update(layer["category_overrides"])

    if isinstance(session_controls, dict):
        merge_pairs = session_controls.get("merge_placeholders")
        if isinstance(merge_pairs, list) and merge_pairs:
            merged["merge_placeholders"] = merge_pairs
    return merged


def saved_rules_summary(client_id: str | None = None) -> Dict[str, int]:
    """Counts of persisted rules that would be merged in (for reports/panel)."""
    summary = {"global_rules": 0, "client_rules": 0}
    g = load_rules("global")
    summary["global_rules"] = len(g["always"]) + len(g["never"]) + len(g["category_overrides"])
    if client_id and client_slug(client_id):
        c = load_rules("client", client_id)
        summary["client_rules"] = len(c["always"]) + len(c["never"]) + len(c["category_overrides"])
    return summary
