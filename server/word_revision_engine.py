from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List
import html
import re

ENGINE_VERSION = "0.5.2-revision-plan"
SCHEMA_VERSION = "0.5.2-revision-map"
CSM_REVISION_MAP_NS = "https://skills.kancelariakantorowski.pl/csm/revision-map/1"
ANCHOR_PREFIX = "CSM_ANCHOR:"
REVISION_MAP_SETTING_KEYS = {
    "part_id": "CSM_RevisionMapPartId",
    "map_id": "CSM_RevisionMapId",
    "schema_version": "CSM_RevisionMapSchemaVersion",
    "engine_version": "CSM_RevisionEngineVersion",
    "namespace": "CSM_RevisionMapNamespace",
}

FULL_DOCX_PART_MARKERS = (
    "header",
    "footer",
    "footnote",
    "endnote",
    "comment",
    "textbox",
    "txbx",
    "section",
)


@dataclass
class RevisionAnchor:
    anchor_id: str
    entity_id: str = ""
    entity_type: str = ""
    original_text: str = ""
    current_text: str = ""
    change_tracking_mode: str = "unknown"
    tracked_change_count: int = 0
    source_part: str = "body"
    paragraph_id: str = ""
    original_ooxml_present: bool = False
    reviewed_original_present: bool = False
    reviewed_current_present: bool = False


@dataclass
class RevisionOp:
    mode: str
    from_text: str
    to_text: str
    anchor_id: str = ""
    entity_type: str = ""
    author: str = "CSM"


@dataclass
class RevisionStrategy:
    mode: str
    reason: str
    requires_sidecar: bool
    requires_full_package: bool
    operations_scope: str
    confidence: str = "medium"


@dataclass
class RevisionJob:
    map_id: str
    mode: str
    operations: List[RevisionOp]
    anchors: List[RevisionAnchor]
    keep_tracking: bool = True
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSION


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "tak", "yes", "y"}


def normalize_anchor(anchor: Dict[str, Any]) -> RevisionAnchor:
    data = anchor or {}
    anchor_id = _string(data.get("anchorId") or data.get("anchor_id") or data.get("tag") or "")
    original_ooxml = data.get("originalOoxml") or data.get("original_ooxml") or data.get("selectionOoxml") or data.get("selection_ooxml")
    reviewed_original = data.get("reviewedOriginal") or data.get("reviewed_original") or data.get("originalText") or data.get("original_text")
    reviewed_current = data.get("reviewedCurrent") or data.get("reviewed_current") or data.get("currentText") or data.get("current_text")
    return RevisionAnchor(
        anchor_id=anchor_id,
        entity_id=_string(data.get("entityId") or data.get("entity_id") or ""),
        entity_type=_string(data.get("entityType") or data.get("entity_type") or data.get("category") or ""),
        original_text=_string(data.get("originalText") or data.get("original_text") or ""),
        current_text=_string(data.get("currentText") or data.get("current_text") or data.get("text") or ""),
        change_tracking_mode=_string(data.get("changeTrackingMode") or data.get("change_tracking_mode") or "unknown"),
        tracked_change_count=_int(data.get("trackedChangeCount") or data.get("tracked_change_count") or 0),
        source_part=_string(data.get("sourcePart") or data.get("source_part") or data.get("documentPart") or data.get("document_part") or "body"),
        paragraph_id=_string(data.get("paragraphId") or data.get("paragraph_id") or data.get("paragraph") or ""),
        original_ooxml_present=_bool(data.get("originalOoxmlPresent") or data.get("original_ooxml_present")) or bool(original_ooxml),
        reviewed_original_present=_bool(data.get("reviewedOriginalPresent") or data.get("reviewed_original_present")) or bool(reviewed_original),
        reviewed_current_present=_bool(data.get("reviewedCurrentPresent") or data.get("reviewed_current_present")) or bool(reviewed_current),
    )


def normalize_replacement(replacement: Dict[str, Any]) -> Dict[str, str]:
    data = replacement or {}
    return {
        "category": _string(data.get("category") or data.get("entity_type") or data.get("entityType") or ""),
        "original": _string(data.get("original") or data.get("original_text") or data.get("originalText") or ""),
        "placeholder": _string(data.get("placeholder") or data.get("replacement") or data.get("replacement_text") or data.get("replacementText") or ""),
    }


def _anchor_for_replacement(anchor_map: Dict[str, RevisionAnchor], replacement: Dict[str, str]) -> RevisionAnchor | None:
    if not anchor_map:
        return None
    candidates = [replacement.get("placeholder", ""), replacement.get("original", "")]
    for value in candidates:
        if value and value in anchor_map:
            return anchor_map[value]
    return None


def build_revision_job(
    *,
    map_id: str = "",
    mode: str = "restore",
    replacements: Iterable[Dict[str, Any]] | None = None,
    anchors: Iterable[Dict[str, Any]] | None = None,
    keep_tracking: bool = True,
    author: str = "CSM",
) -> RevisionJob:
    """Build a deterministic revision operation plan.

    This module is intentionally plan-only. It does not try to synthesize
    WordprocessingML revision markup in Python. The plan is the contract between
    the add-in Range bridge and the future OOXML sidecar based on OpenXmlPowerTools.
    """
    selected_mode = (mode or "restore").strip().lower()
    if selected_mode not in {"restore", "anonymize", "mask"}:
        raise ValueError(f"Unsupported revision job mode: {mode}")
    normalized_anchors = [normalize_anchor(item) for item in (anchors or [])]
    anchor_map: Dict[str, RevisionAnchor] = {}
    for anchor in normalized_anchors:
        for key in [anchor.current_text, anchor.original_text, anchor.entity_id, anchor.anchor_id]:
            if key:
                anchor_map.setdefault(key, anchor)

    ops: List[RevisionOp] = []
    for raw in replacements or []:
        repl = normalize_replacement(raw)
        original = repl["original"]
        placeholder = repl["placeholder"]
        if not original or not placeholder:
            continue
        anchor = _anchor_for_replacement(anchor_map, repl)
        if selected_mode in {"anonymize", "mask"}:
            from_text, to_text, op_mode = original, placeholder, "anonymize"
        else:
            from_text, to_text, op_mode = placeholder, original, "restore"
        ops.append(
            RevisionOp(
                mode=op_mode,
                from_text=from_text,
                to_text=to_text,
                anchor_id=anchor.anchor_id if anchor else "",
                entity_type=(anchor.entity_type if anchor and anchor.entity_type else repl["category"]),
                author=author or "CSM",
            )
        )
    return RevisionJob(
        map_id=map_id or "",
        mode="anonymize" if selected_mode == "mask" else selected_mode,
        operations=ops,
        anchors=normalized_anchors,
        keep_tracking=bool(keep_tracking),
    )


def _source_part_requires_full_docx(source_part: str) -> bool:
    normalized = (source_part or "body").strip().lower()
    if not normalized or normalized in {"body", "document", "main", "document.xml", "word/document.xml"}:
        return False
    return any(marker in normalized for marker in FULL_DOCX_PART_MARKERS)


def _paragraph_operation_counts(job: RevisionJob) -> Dict[str, int]:
    by_anchor = {anchor.anchor_id: anchor for anchor in job.anchors if anchor.anchor_id}
    counts: Dict[str, int] = {}
    for op in job.operations:
        anchor = by_anchor.get(op.anchor_id)
        if anchor and anchor.paragraph_id:
            counts[anchor.paragraph_id] = counts.get(anchor.paragraph_id, 0) + 1
    return counts


def select_restore_strategy(job: RevisionJob) -> RevisionStrategy:
    """Classify the plan into the safest execution strategy for a future sidecar.

    The strategy is advisory. Python still returns a plan only; it does not rewrite
    OOXML. The classification lets the add-in/backend choose between range-level,
    paragraph-level, and full-package execution in later iterations.
    """
    if not job.operations:
        return RevisionStrategy(
            mode="none",
            reason="Brak operacji rewizyjnych do wykonania.",
            requires_sidecar=False,
            requires_full_package=False,
            operations_scope="none",
            confidence="high",
        )
    if any(_source_part_requires_full_docx(anchor.source_part) for anchor in job.anchors):
        return RevisionStrategy(
            mode="full-docx",
            reason="Co najmniej jeden anchor leży poza głównym body dokumentu lub w złożonej części pakietu DOCX.",
            requires_sidecar=True,
            requires_full_package=True,
            operations_scope="package",
            confidence="high",
        )
    paragraph_counts = _paragraph_operation_counts(job)
    if any(count > 1 for count in paragraph_counts.values()):
        return RevisionStrategy(
            mode="paragraph-ooxml",
            reason="W jednym akapicie występuje więcej niż jedna operacja, więc bezpieczniejszy jest patch akapitowy niż kilka niezależnych Range replacements.",
            requires_sidecar=True,
            requires_full_package=False,
            operations_scope="paragraph",
            confidence="medium",
        )
    if job.keep_tracking and any(anchor.tracked_change_count > 0 for anchor in job.anchors):
        return RevisionStrategy(
            mode="range-ooxml",
            reason="Operacje są zakotwiczone, a zakresy zawierają tracked changes; użyj Range/OOXML i zachowaj tryb śledzenia zmian.",
            requires_sidecar=True,
            requires_full_package=False,
            operations_scope="range",
            confidence="medium",
        )
    if any(not op.anchor_id for op in job.operations):
        return RevisionStrategy(
            mode="text-fallback",
            reason="Część operacji nie ma anchorId; plan wymaga fallbacku tekstowego albo pełniejszego silnika OOXML.",
            requires_sidecar=True,
            requires_full_package=False,
            operations_scope="document-text",
            confidence="low",
        )
    return RevisionStrategy(
        mode="range-ooxml",
        reason="Każda operacja ma pojedynczy anchor w głównym body dokumentu.",
        requires_sidecar=False,
        requires_full_package=False,
        operations_scope="range",
        confidence="high",
    )


def summarize_revision_job(job: RevisionJob) -> Dict[str, Any]:
    anchored = sum(1 for op in job.operations if op.anchor_id)
    tracked_anchors = sum(1 for anchor in job.anchors if anchor.tracked_change_count > 0)
    strategy = select_restore_strategy(job)
    return {
        "engine_version": job.engine_version,
        "schema_version": job.schema_version,
        "map_id": job.map_id,
        "mode": job.mode,
        "operations_count": len(job.operations),
        "anchored_operations_count": anchored,
        "unanchored_operations_count": len(job.operations) - anchored,
        "anchors_count": len(job.anchors),
        "tracked_anchors_count": tracked_anchors,
        "keep_tracking": job.keep_tracking,
        "custom_xml_persistence_required": True,
        "sidecar_required": strategy.requires_sidecar,
        "sidecar_available": False,
        "restore_strategy": asdict(strategy),
        "status": "plan_ready" if job.operations else "empty_plan",
    }


def revision_job_to_dict(job: RevisionJob) -> Dict[str, Any]:
    return {
        "map_id": job.map_id,
        "mode": job.mode,
        "keep_tracking": job.keep_tracking,
        "engine_version": job.engine_version,
        "schema_version": job.schema_version,
        "operations": [asdict(op) for op in job.operations],
        "anchors": [asdict(anchor) for anchor in job.anchors],
        "summary": summarize_revision_job(job),
    }


def _xml(value: Any) -> str:
    return html.escape(_string(value), quote=True)


def _xml_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value or "item")
    return cleaned or "item"


def build_custom_xml_payload(job: RevisionJob) -> str:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    strategy = select_restore_strategy(job)
    parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<csm:revisionMap xmlns:csm="{_xml(CSM_REVISION_MAP_NS)}" schemaVersion="{_xml(job.schema_version)}" engineVersion="{_xml(job.engine_version)}" mapId="{_xml(job.map_id)}" mode="{_xml(job.mode)}" createdAt="{_xml(created_at)}">',
        f'<csm:strategy mode="{_xml(strategy.mode)}" operationsScope="{_xml(strategy.operations_scope)}" requiresSidecar="{_xml(str(strategy.requires_sidecar).lower())}" requiresFullPackage="{_xml(str(strategy.requires_full_package).lower())}" confidence="{_xml(strategy.confidence)}">{_xml(strategy.reason)}</csm:strategy>',
        '<csm:anchors>',
    ]
    for anchor in job.anchors:
        parts.append(
            f'<csm:anchor id="{_xml(anchor.anchor_id)}" entityId="{_xml(anchor.entity_id)}" entityType="{_xml(anchor.entity_type)}" trackedChangeCount="{anchor.tracked_change_count}" changeTrackingMode="{_xml(anchor.change_tracking_mode)}" sourcePart="{_xml(anchor.source_part)}" paragraphId="{_xml(anchor.paragraph_id)}" originalOoxmlPresent="{_xml(str(anchor.original_ooxml_present).lower())}" reviewedOriginalPresent="{_xml(str(anchor.reviewed_original_present).lower())}" reviewedCurrentPresent="{_xml(str(anchor.reviewed_current_present).lower())}">'
            f'<csm:originalText>{_xml(anchor.original_text)}</csm:originalText>'
            f'<csm:currentText>{_xml(anchor.current_text)}</csm:currentText>'
            '</csm:anchor>'
        )
    parts.append('</csm:anchors><csm:operations>')
    for index, op in enumerate(job.operations, 1):
        parts.append(
            f'<csm:operation id="op{index}" mode="{_xml(op.mode)}" anchorId="{_xml(op.anchor_id)}" entityType="{_xml(op.entity_type)}" author="{_xml(op.author)}">'
            f'<csm:from>{_xml(op.from_text)}</csm:from>'
            f'<csm:to>{_xml(op.to_text)}</csm:to>'
            '</csm:operation>'
        )
    parts.append('</csm:operations></csm:revisionMap>')
    return ''.join(parts)


def build_document_metadata(job: RevisionJob, *, custom_xml_part_id: str = "") -> Dict[str, str]:
    """Build small document-level metadata for Word settings/custom properties.

    The full revision map belongs in CustomXmlPart. These values are intentionally
    short so they can be mirrored into Word settings and, where supported by the
    host, custom document properties.
    """
    strategy = select_restore_strategy(job)
    return {
        REVISION_MAP_SETTING_KEYS["part_id"]: _string(custom_xml_part_id),
        REVISION_MAP_SETTING_KEYS["map_id"]: _string(job.map_id),
        REVISION_MAP_SETTING_KEYS["schema_version"]: _string(job.schema_version),
        REVISION_MAP_SETTING_KEYS["engine_version"]: _string(job.engine_version),
        REVISION_MAP_SETTING_KEYS["namespace"]: CSM_REVISION_MAP_NS,
        "CSM_RevisionMapMode": _string(job.mode),
        "CSM_RevisionOperationsCount": str(len(job.operations)),
        "CSM_RevisionAnchorsCount": str(len(job.anchors)),
        "CSM_RevisionRestoreStrategy": strategy.mode,
    }


def build_revision_map_contract(job: RevisionJob) -> Dict[str, Any]:
    """Return the complete persistence contract consumed by revision_bridge.js."""
    return {
        "namespace": CSM_REVISION_MAP_NS,
        "setting_keys": dict(REVISION_MAP_SETTING_KEYS),
        "document_metadata": build_document_metadata(job),
        "custom_xml_payload": build_custom_xml_payload(job),
        "strategy": asdict(select_restore_strategy(job)),
    }


def _issue(code: str, message: str, severity: str = "warning") -> Dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


def validate_revision_job(job: RevisionJob) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    strategy = select_restore_strategy(job)
    if not job.operations:
        issues.append(_issue("empty_operations", "Brak operacji rewizyjnych do wykonania.", "warning"))
    for index, op in enumerate(job.operations):
        if not op.from_text or not op.to_text:
            issues.append(_issue("empty_replacement", f"Operacja {index} nie ma tekstu źródłowego lub docelowego.", "error"))
        if job.keep_tracking and not op.anchor_id:
            issues.append(_issue("unanchored_operation", f"Operacja {index} nie ma anchorId; wymaga fallbacku tekstowego albo sidecara OOXML.", "warning"))
    if strategy.mode == "full-docx" and not strategy.requires_full_package:
        issues.append(_issue("strategy_inconsistent", "Strategia full-docx nie została oznaczona jako full-package.", "error"))
    if strategy.requires_sidecar:
        issues.append(_issue("sidecar_not_available", "Plan wymaga przyszłego sidecara OOXML; bieżący endpoint zwraca tylko kontrakt wykonania.", "warning"))
    return {
        "ok": not any(item.get("severity") == "error" for item in issues),
        "issues": issues,
        "summary": summarize_revision_job(job),
        "strategy": asdict(strategy),
    }
