from __future__ import annotations

import base64
import copy
import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from lxml import etree

try:  # Test imports may use either repo root or server/ on sys.path.
    from engine_types import Finding, Replacement
    from redactor import (
        DocxXmlTooLargeError,
        XmlSecurityError,
        _check_docx_xml_uncompressed_limit,
        _existing_placeholders,
        build_replacement_plan,
        collect_findings,
        collect_findings_with_controls,
        collect_findings_with_controls_report,
        replacements_from_plan,
    )
except ImportError:  # pragma: no cover - package-style import fallback
    from .engine_types import Finding, Replacement
    from .redactor import (
        DocxXmlTooLargeError,
        XmlSecurityError,
        _check_docx_xml_uncompressed_limit,
        _existing_placeholders,
        build_replacement_plan,
        collect_findings,
        collect_findings_with_controls,
        collect_findings_with_controls_report,
        replacements_from_plan,
    )

ENGINE_VERSION = "0.3.2-tc-placeholder-position-rebuild"
DOCX_ZIP_COMPRESSLEVEL_FAST = 1


def _open_docx_output_zip(target) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=DOCX_ZIP_COMPRESSLEVEL_FAST)
    except TypeError:  # pragma: no cover
        return zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
NSMAP = {"w": W_NS}

# User/content-bearing parts. This mirrors the Word package scope from redactor.py
# but is intentionally local to the v3 engine so v0.2.x paths remain unchanged.
DOCX_CONTENT_PART_RE = re.compile(
    r"^(?:word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments|glossary/document)\.xml|"
    r"docProps/(?:core|app|custom)\.xml|customXml/item\d+\.xml)$",
    re.IGNORECASE,
)

TEXT_TAGS = {"t", "delText", "instrText"}
BLOCK_TAGS = {"p", "tbl", "tr", "tc", "footnote", "endnote", "comment"}
REVISION_TAGS = {"ins", "del", "moveFrom", "moveTo"}
FORMATTING_CHANGE_TAGS = {
    "pPrChange",
    "rPrChange",
    "tblPrChange",
    "trPrChange",
    "tcPrChange",
    "sectPrChange",
    "numberingChange",
}
PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9_]{1,60}\]")
_ATTR_SENSITIVE_NAME_RE = re.compile(
    r"(?:^|})(?:author|initials|creator|lastModifiedBy|title|subject|description|keywords|category|company|manager)$",
    re.I,
)
_FORBIDDEN_DOCTYPE_RE = re.compile(rb"<!DOCTYPE\b", re.IGNORECASE)
_FORBIDDEN_ENTITY_RE = re.compile(rb"<!ENTITY\b", re.IGNORECASE)
SEP = "\ue000"
PART_SEP = "\ue000CSM_V3_PART_BOUNDARY\ue001"


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


def _image_redaction_enabled() -> bool:
    return str(os.environ.get("CSM_REDACT_IMAGES", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _part_is_image(name: str) -> bool:
    return bool(IMAGE_PART_RE.match(name or ""))


def _redacted_image_bytes(name: str) -> bytes:
    ext = (name.rsplit(".", 1)[-1] if "." in name else "png").lower()
    data = _REDACTED_IMAGE_BASE64.get(ext) or _REDACTED_IMAGE_BASE64["png"]
    return base64.b64decode(data.encode("ascii"))


def _count_graphical_elements(root: etree._Element) -> Dict[str, int]:
    counts = {"shapes": 0, "text_boxes": 0}
    for el in root.iter():
        lname = _local_name(el.tag)
        if lname in {"drawing", "pict", "object"}:
            counts["shapes"] += 1
        elif lname in {"txbxContent", "textbox"}:
            counts["text_boxes"] += 1
    return counts


def restore_redacted_images_from_original(docx_bytes: bytes, original_docx_bytes: bytes | None) -> Tuple[bytes, Dict[str, int]]:
    """Reinsert original media parts into a restored DOCX, when available.

    CSM masks images in the AI-safe copy because text embedded in pixels cannot be safely
    pseudonymized by the text engine. The original DOCX is already stored in the
    local CSM map/session, so restore can put those media parts back into the
    final jawny copy without ever exposing them to Claude.
    """
    report = {"available_original_images": 0, "restored_images": 0, "missing_original_images": 0}
    if not original_docx_bytes:
        return docx_bytes, report
    try:
        with zipfile.ZipFile(io.BytesIO(original_docx_bytes), "r") as zorig:
            originals = {info.filename: zorig.read(info.filename) for info in zorig.infolist() if _part_is_image(info.filename)}
    except Exception:
        return docx_bytes, report
    report["available_original_images"] = len(originals)
    if not originals:
        return docx_bytes, report
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if _part_is_image(info.filename):
                    if info.filename in originals:
                        data = originals[info.filename]
                        report["restored_images"] += 1
                    else:
                        report["missing_original_images"] += 1
                _zip_writestr_preserving(zout, info, data)
    return out.getvalue(), report


@dataclass
class TextSlot:
    kind: str  # "text" or "attr"
    target: Any
    key: str | None
    start: int
    end: int
    revision_context: str | None = None

    def get(self) -> str:
        if self.kind == "attr":
            return str(self.target.attrib.get(self.key, ""))
        return self.target.text or ""

    def set(self, value: str) -> None:
        if self.kind == "attr":
            self.target.attrib[self.key] = value
        else:
            self.target.text = value


def _local_name(tag: str) -> str:
    if "}" in str(tag):
        return str(tag).rsplit("}", 1)[1]
    return str(tag)


def _reject_unsafe_xml_prefix(data: bytes) -> None:
    prefix = data[:4096]
    if _FORBIDDEN_DOCTYPE_RE.search(prefix):
        raise XmlSecurityError("DOCX XML contains a <!DOCTYPE declaration")
    if _FORBIDDEN_ENTITY_RE.search(prefix):
        raise XmlSecurityError("DOCX XML contains an <!ENTITY declaration")


def _parse_xml(data: bytes) -> etree._Element:
    _reject_unsafe_xml_prefix(data)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=False)
    return etree.fromstring(data, parser=parser)


def _serialize_xml(root: etree._Element) -> bytes:
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=None)


def _zip_writestr_preserving(zout: zipfile.ZipFile, info: zipfile.ZipInfo, data: bytes) -> None:
    # Preserve metadata relevant to ZIP consumers while avoiding mutation of the input ZipInfo.
    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    zi.compress_type = zipfile.ZIP_DEFLATED if info.compress_type == zipfile.ZIP_STORED else info.compress_type
    zi.comment = info.comment
    zi.extra = info.extra
    zi.internal_attr = info.internal_attr
    zi.external_attr = info.external_attr
    zi.create_system = info.create_system
    zout.writestr(zi, data)


def _add_separator(parts: List[str], pos: int) -> int:
    if parts and not parts[-1].endswith(SEP):
        parts.append(SEP)
        pos += len(SEP)
    return pos


def _walk_part_with_tc_awareness(root: etree._Element, include_attributes: bool = True) -> Tuple[List[TextSlot], str]:
    """Return text slots and a detector-friendly plain-text view.

    Separators are inserted at block and revision boundaries. Text split across
    runs inside the same revision remains contiguous, so a name split into
    multiple <w:t> nodes inside one <w:ins> can still be detected. Text from a
    revision is not sewn together with adjacent normal text.
    """
    slots: List[TextSlot] = []
    parts: List[str] = []
    pos = 0

    def walk(el: etree._Element, revision_context: str | None = None) -> None:
        nonlocal pos
        lname = _local_name(el.tag)
        child_revision = revision_context
        is_block = lname in BLOCK_TAGS
        is_revision = lname in REVISION_TAGS
        if is_block or is_revision:
            pos = _add_separator(parts, pos)
        if is_revision:
            child_revision = lname
        if lname in TEXT_TAGS:
            txt = el.text or ""
            if txt:
                start = pos
                parts.append(txt)
                pos += len(txt)
                slots.append(TextSlot("text", el, None, start, pos, child_revision))
        for child in el:
            walk(child, child_revision)
        if is_revision:
            pos = _add_separator(parts, pos)
        # Block end boundary helps avoid joining paragraphs/tables/comments.
        if is_block:
            pos = _add_separator(parts, pos)

    walk(root)

    if include_attributes:
        for el in root.iter():
            for key, value in list(el.attrib.items()):
                if value and _ATTR_SENSITIVE_NAME_RE.search(key):
                    pos = _add_separator(parts, pos)
                    start = pos
                    parts.append(str(value))
                    pos += len(str(value))
                    slots.append(TextSlot("attr", el, key, start, pos, None))
                    pos = _add_separator(parts, pos)

    return slots, "".join(parts)


def _replace_range_in_slots(slots: List[TextSlot], start: int, end: int, replacement: str) -> None:
    first_done = False
    for slot in slots:
        if slot.end <= start or slot.start >= end:
            continue
        txt = slot.get()
        local_start = max(start - slot.start, 0)
        local_end = min(end - slot.start, len(txt))
        before = txt[:local_start]
        after = txt[local_end:]
        if not first_done:
            slot.set(before + replacement + (after if end <= slot.end else ""))
            first_done = True
        else:
            slot.set(after if end <= slot.end else "")


def _count_revisions(root: etree._Element) -> Dict[str, int]:
    counts = {"ins_count": 0, "del_count": 0, "moveFrom_count": 0, "moveTo_count": 0}
    for el in root.iter():
        lname = _local_name(el.tag)
        if lname == "ins":
            counts["ins_count"] += 1
        elif lname == "del":
            counts["del_count"] += 1
        elif lname == "moveFrom":
            counts["moveFrom_count"] += 1
        elif lname == "moveTo":
            counts["moveTo_count"] += 1
    return counts


def _merge_counts(dst: Dict[str, int], src: Dict[str, int]) -> None:
    for key, value in src.items():
        dst[key] = int(dst.get(key, 0) or 0) + int(value or 0)


def _unwrap_element(el: etree._Element) -> None:
    parent = el.getparent()
    if parent is None:
        return
    idx = parent.index(el)
    if el.text:
        # Put direct text into a normal w:r/w:t so it remains visible.
        r = etree.Element(W + "r")
        t = etree.SubElement(r, W + "t")
        t.text = el.text
        parent.insert(idx, r)
        idx += 1
    for child in list(el):
        el.remove(child)
        parent.insert(idx, child)
        idx += 1
    if el.tail:
        if idx > 0 and len(parent):
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def _remove_element(el: etree._Element) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _convert_deleted_text_to_visible_text(el: etree._Element) -> None:
    """Convert <w:delText> descendants to <w:t> before rejecting deletions.

    <w:delText> is only rendered by Word inside a deletion wrapper. When the
    deletion is rejected and the wrapper is unwrapped, the recovered text must
    be ordinary visible text. Preserve xml:space and all other attributes.
    """
    for node in el.iter():
        if _local_name(node.tag) == "delText":
            node.tag = W + "t"


def _reject_formatting_change(el: etree._Element) -> None:
    """Reject a formatting revision by restoring the previous property state.

    Word stores the previous formatting inside the *PrChange element, usually as
    a child whose local-name matches the parent property element (for example
    <w:pPr><w:pPrChange><w:pPr>...</w:pPr></w:pPrChange></w:pPr>).
    Rejection means the parent properties become that previous state, and the
    change marker is removed. If no previous state is present, safely remove the
    change marker only.
    """
    parent = el.getparent()
    if parent is None:
        return
    parent_lname = _local_name(parent.tag)
    old_state = None
    for child in el:
        if _local_name(child.tag) == parent_lname:
            old_state = child
            break
    if old_state is None:
        _remove_element(el)
        return

    # Remove current property children, including the *PrChange marker.
    for child in list(parent):
        parent.remove(child)
    parent.attrib.clear()
    parent.attrib.update(old_state.attrib)
    for child in list(old_state):
        old_state.remove(child)
        parent.append(child)


def _accept_or_reject_root(root: etree._Element, *, accept: bool) -> None:
    # Process deepest first so parent indices remain safe.
    for el in sorted(list(root.iter()), key=lambda e: len(list(e.iterancestors())), reverse=True):
        lname = _local_name(el.tag)
        if lname in FORMATTING_CHANGE_TAGS:
            if accept:
                _remove_element(el)
            else:
                _reject_formatting_change(el)
        elif accept:
            if lname in {"ins", "moveTo"}:
                _unwrap_element(el)
            elif lname in {"del", "moveFrom"}:
                _remove_element(el)
        else:
            if lname in {"ins", "moveTo"}:
                _remove_element(el)
            elif lname in {"del", "moveFrom"}:
                _convert_deleted_text_to_visible_text(el)
                _unwrap_element(el)


def _transform_revisions_in_docx(docx_bytes: bytes, *, accept: bool) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename.lower().endswith(".xml"):
                    try:
                        root = _parse_xml(data)
                        _accept_or_reject_root(root, accept=accept)
                        data = _serialize_xml(root)
                    except XmlSecurityError:
                        raise
                    except Exception:
                        # Non-content package XML that lxml cannot parse is copied unchanged.
                        pass
                _zip_writestr_preserving(zout, info, data)
    return out.getvalue()


def _part_is_content(name: str) -> bool:
    return bool(DOCX_CONTENT_PART_RE.match(name or ""))


def _build_coverage(processed_parts: List[str], graphical_elements: Dict[str, int] | None = None) -> Dict[str, Any]:
    graphics = {"images": 0, "shapes": 0, "text_boxes": 0, "redacted_images": 0}
    if graphical_elements:
        for key, value in graphical_elements.items():
            graphics[key] = int(value or 0)
    return {
        "body": any(n == "word/document.xml" for n in processed_parts),
        "headers": sum(1 for n in processed_parts if re.match(r"word/header\d+\.xml$", n, re.I)),
        "footers": sum(1 for n in processed_parts if re.match(r"word/footer\d+\.xml$", n, re.I)),
        "comments": any(n == "word/comments.xml" for n in processed_parts),
        "footnotes": any(n == "word/footnotes.xml" for n in processed_parts),
        "endnotes": any(n == "word/endnotes.xml" for n in processed_parts),
        "metadata": sum(1 for n in processed_parts if re.match(r"docProps/(?:core|app|custom)\.xml$", n, re.I)),
        "custom_xml": sum(1 for n in processed_parts if n.lower().startswith("customxml/")),
        "graphical_elements": graphics,
    }


def mask_docx_preserving_tc(docx_bytes: bytes, mode: str = "preserve", controls: Dict[str, Any] | None = None) -> Tuple[bytes, List[Replacement], Dict[str, Any]]:
    """Mask a whole DOCX package while preserving tracked-change wrappers.

    In preserve mode the engine edits text nodes in place inside existing
    <w:ins>/<w:del>/<w:moveFrom>/<w:moveTo> wrappers. It does not create new
    revision elements and does not remove existing ones. accept_then_mask and
    reject_then_mask are included as API-compatible modes, but Iteration 1 only
    treats preserve as the acceptance target.
    """
    if mode not in {"preserve", "accept_then_mask", "reject_then_mask"}:
        raise ValueError("Unsupported v3 DOCX mode")
    working = docx_bytes
    if mode == "accept_then_mask":
        working = _transform_revisions_in_docx(working, accept=True)
    elif mode == "reject_then_mask":
        working = _transform_revisions_in_docx(working, accept=False)

    parsed: Dict[str, Tuple[etree._Element, List[TextSlot], str, int, Dict[str, int]]] = {}
    combined_parts: List[str] = []
    processed_parts: List[str] = []
    skipped_parts: List[str] = []
    image_parts: List[str] = []
    redacted_image_parts: List[str] = []
    graphical_elements = {"images": 0, "shapes": 0, "text_boxes": 0, "redacted_images": 0}
    redact_images = _image_redaction_enabled()
    offset = 0
    revision_summary: Dict[str, int | bool] = {"ins_count": 0, "del_count": 0, "moveFrom_count": 0, "moveTo_count": 0, "ins_with_pii": 0, "del_with_pii": 0, "preserved": mode == "preserve"}

    with zipfile.ZipFile(io.BytesIO(working), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        image_parts = [info.filename for info in zin.infolist() if _part_is_image(info.filename)]
        graphical_elements["images"] = len(image_parts)
        for info in zin.infolist():
            name = info.filename
            if not _part_is_content(name):
                continue
            data = zin.read(name)
            try:
                root = _parse_xml(data)
                part_graphics = _count_graphical_elements(root)
                graphical_elements["shapes"] += part_graphics.get("shapes", 0)
                graphical_elements["text_boxes"] += part_graphics.get("text_boxes", 0)
                slots, plain = _walk_part_with_tc_awareness(root, include_attributes=True)
            except XmlSecurityError:
                raise
            except Exception:
                skipped_parts.append(name)
                continue
            rev_counts = _count_revisions(root)
            _merge_counts(revision_summary, rev_counts)  # type: ignore[arg-type]
            parsed[name] = (root, slots, plain, offset, rev_counts)
            combined_parts.append(plain)
            processed_parts.append(name)
            offset += len(plain) + len(PART_SEP)

        combined = PART_SEP.join(combined_parts)
        controls_effects: Dict[str, Any] | None = None
        if controls:
            findings, controls_effects = collect_findings_with_controls_report(combined, controls)
        else:
            findings = collect_findings(combined)
        seen, counts = build_replacement_plan(findings, _existing_placeholders(combined))

        for name, (root, slots, plain, part_offset, rev_counts) in parsed.items():
            part_start = part_offset
            part_end = part_start + len(plain)
            part_findings = [
                Finding(f.category, f.value, f.start - part_start, f.end - part_start)
                for f in findings
                if f.start >= part_start and f.end <= part_end
            ]
            for f in part_findings:
                for slot in slots:
                    if slot.end <= f.start or slot.start >= f.end:
                        continue
                    if slot.revision_context == "ins":
                        revision_summary["ins_with_pii"] = int(revision_summary.get("ins_with_pii", 0) or 0) + 1
                    elif slot.revision_context == "del":
                        revision_summary["del_with_pii"] = int(revision_summary.get("del_with_pii", 0) or 0) + 1
                    break
            for f in sorted(part_findings, key=lambda item: item.start, reverse=True):
                placeholder = seen[(f.category, f.value)]
                _replace_range_in_slots(slots, f.start, f.end, placeholder)

        out = io.BytesIO()
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in parsed:
                    data = _serialize_xml(parsed[info.filename][0])
                elif redact_images and _part_is_image(info.filename):
                    data = _redacted_image_bytes(info.filename)
                    redacted_image_parts.append(info.filename)
                _zip_writestr_preserving(zout, info, data)

    graphical_elements["redacted_images"] = len(redacted_image_parts)
    warnings: List[str] = []
    if image_parts and redact_images:
        warnings.append(f"Obrazy w DOCX: wykryto {len(image_parts)} plik(i) graficzne; w kopii _CSM_anon zasłonięto je lokalnie, ponieważ CSM nie analizuje treści obrazów ani pikseli.")
    elif image_parts:
        warnings.append(f"Obrazy w DOCX: wykryto {len(image_parts)} plik(i) graficzne; redakcja obrazów jest wyłączona i dokument wymaga ręcznej kontroli przed wysłaniem do AI.")

    report = {
        "engine_version": ENGINE_VERSION,
        "processed_parts": processed_parts,
        "skipped_parts": skipped_parts,
        "revisions_summary": revision_summary,
        "coverage": _build_coverage(processed_parts, graphical_elements),
        "image_parts": image_parts[:100],
        "redacted_image_parts": redacted_image_parts[:100],
        "warnings": warnings,
        "user_controls_applied": bool(controls),
    }
    if controls_effects is not None:
        # Per-rule accountability: match counts, suppressed detections, dead rules.
        # Context snippets inside are local-only (session folder + panel).
        report["manual_controls_effects"] = controls_effects
        for rule_warning in controls_effects.get("warnings", []):
            warnings.append(rule_warning)
    return out.getvalue(), replacements_from_plan(seen, counts), report


def _element_text(el: etree._Element) -> str:
    """Return Word-visible text stored in an OOXML subtree."""
    values: List[str] = []
    for node in el.iter():
        if _local_name(node.tag) in TEXT_TAGS and node.text:
            values.append(str(node.text))
    return "".join(values)


def _contains_any_value(text: str, values: Iterable[str]) -> bool:
    haystack = str(text or "")
    return any(v and v in haystack for v in values)


def _nearest_ancestor(el: etree._Element, local_names: set[str]) -> etree._Element | None:
    node = el
    while node is not None:
        if _local_name(node.tag) in local_names:
            return node
        node = node.getparent()
    return None


def _inside_revision(el: etree._Element) -> bool:
    node = el
    while node is not None:
        if _local_name(node.tag) in REVISION_TAGS:
            return True
        node = node.getparent()
    return False


@dataclass
class RevisionContextFragment:
    part_name: str
    kind: str
    value: str
    attrs: Dict[str, str]


def _revision_attrs(el: etree._Element) -> Dict[str, str]:
    return {str(k): str(v) for k, v in el.attrib.items()}


def _collect_original_revision_fragments(original_docx_bytes: bytes, protected_values: Iterable[str]) -> Dict[str, List[RevisionContextFragment]]:
    """Collect revision contexts for individual protected values.

    Collects all revision types so the overlay can fix wrong-author attributes
    on existing wrappers (Case A).  Whether a *new* wrapper is created for plain
    text is controlled in overlay_original_revision_contexts (Case B).
    """
    values = sorted({str(v) for v in protected_values if str(v or "")}, key=len, reverse=True)
    result: Dict[str, List[RevisionContextFragment]] = {}
    if not values:
        return result
    with zipfile.ZipFile(io.BytesIO(original_docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        for info in zin.infolist():
            if not _part_is_content(info.filename):
                continue
            try:
                root = _parse_xml(zin.read(info.filename))
            except Exception:
                continue
            for el in root.iter():
                kind = _local_name(el.tag)
                if kind not in REVISION_TAGS:
                    continue
                text = _element_text(el)
                if not text:
                    continue
                for value in values:
                    count = text.count(value)
                    for _ in range(count):
                        result.setdefault(info.filename, []).append(
                            RevisionContextFragment(info.filename, kind, value, _revision_attrs(el))
                        )
    return result


def _revision_author(el: etree._Element) -> str:
    """Return the w:author attribute of a revision element, or empty string."""
    for key in el.attrib:
        if _local_name(key) == "author":
            return el.attrib[key]
    return ""


def _fragment_author(fragment: RevisionContextFragment) -> str:
    """Return the w:author value stored in a fragment's attrs dict, or empty string."""
    for key, value in fragment.attrs.items():
        if _local_name(key) == "author":
            return value
    return ""


def _revision_value_already_present(root: etree._Element, fragment: RevisionContextFragment) -> bool:
    """Return True only when all matching revision wrappers already have the
    original author/attributes context.

    The old check stopped at the first matching text value. If a correct wrapper
    and a wrong-author wrapper coexisted, overlay skipped the correction and left
    e.g. w:author="Osoba_1" in the restored document. Any wrong-author match is
    therefore treated as "not already present" so the fix pass can update it.
    """
    if not fragment.value:
        return False
    frag_author = _fragment_author(fragment)
    saw_match = False
    for el in root.iter():
        if _local_name(el.tag) == fragment.kind and fragment.value in _element_text(el):
            saw_match = True
            if frag_author and _revision_author(el) != frag_author:
                return False
    return saw_match


def _fix_wrong_author_revision_fragment(root: etree._Element, fragment: RevisionContextFragment) -> bool:
    """Fix ALL revision elements that have the right kind and contain the value but carry
    wrong attributes (typically an anonymised author like 'Osoba_1' instead of the real
    person's name).  Replace every attribute with the correct set from the original fragment.

    Fixing all occurrences in one call is intentional: the outer per-fragment loop calls
    this once per fragment but _revision_value_already_present returns True for subsequent
    fragments of the same value once the first occurrence is correct, so all remaining
    wrong-author instances must be fixed in this single pass.

    Returns True if at least one element was fixed, False when no wrong-author match was found.
    """
    frag_author = _fragment_author(fragment)
    if not frag_author:
        # No author in original → nothing to correct.
        return False
    fixed = False
    for el in root.iter():
        if _local_name(el.tag) == fragment.kind and fragment.value and fragment.value in _element_text(el):
            if _revision_author(el) != frag_author:
                # Replace all attributes with the original ones.
                for key in list(el.attrib.keys()):
                    del el.attrib[key]
                for key, value in fragment.attrs.items():
                    el.set(key, value)
                fixed = True
    if fixed:
        # Deduplicate/assign revision IDs once after all elements are updated.
        _normalise_revision_ids(root)
    return fixed


def _next_revision_id(root: etree._Element) -> int:
    values: List[int] = []
    for el in root.iter():
        if _local_name(el.tag) in REVISION_TAGS or _local_name(el.tag) in FORMATTING_CHANGE_TAGS:
            for key, value in el.attrib.items():
                if _local_name(key) == "id":
                    try:
                        values.append(int(value))
                    except Exception:
                        pass
    return (max(values) + 1) if values else 1


def _normalise_revision_ids(root: etree._Element) -> None:
    """Assign ids to missing/duplicate revision elements, like OpenXmlRegex does."""
    seen: set[str] = set()
    next_id = _next_revision_id(root)
    for el in root.iter():
        if _local_name(el.tag) not in REVISION_TAGS and _local_name(el.tag) not in FORMATTING_CHANGE_TAGS:
            continue
        id_key = None
        for key in el.attrib.keys():
            if _local_name(key) == "id":
                id_key = key
                break
        current = el.attrib.get(id_key) if id_key is not None else None
        if not current or current in seen:
            namespaced_id = W + "id"
            el.set(namespaced_id, str(next_id))
            seen.add(str(next_id))
            next_id += 1
        else:
            seen.add(str(current))


def _clone_text_run(text: str, source_run: etree._Element | None = None, *, deleted: bool = False) -> etree._Element:
    if source_run is not None and _local_name(source_run.tag) == "r":
        run = copy.deepcopy(source_run)
        for child in list(run):
            if _local_name(child.tag) != "rPr":
                run.remove(child)
    else:
        run = etree.Element(W + "r")
    text_tag = "delText" if deleted else "t"
    t = etree.SubElement(run, W + text_tag)
    if text[:1].isspace() or text[-1:].isspace():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return run


def _build_revision_element(fragment: RevisionContextFragment, source_run: etree._Element | None) -> etree._Element:
    kind = fragment.kind
    wrapper = etree.Element(W + kind)
    for key, value in fragment.attrs.items():
        wrapper.set(key, value)
    # Values restored into deleted/moveFrom revisions must be represented as
    # w:delText. Values restored into inserted/moveTo revisions remain w:t.
    deleted = kind in {"del", "moveFrom"}
    wrapper.append(_clone_text_run(fragment.value, source_run, deleted=deleted))
    return wrapper


def _replace_normal_text_with_revision_fragment(root: etree._Element, fragment: RevisionContextFragment) -> bool:
    """Replace a flattened normal-text occurrence with a valid revision run.

    This intentionally acts on the protected value, not the entire original
    revision element. The previous range-wide logic searched for the whole revision
    text, so it failed whenever Claude/Word changed surrounding words while the
    protected value itself remained restored.
    """
    slots, plain = _walk_part_with_tc_awareness(root, include_attributes=False)
    if not fragment.value:
        return False
    start = plain.find(fragment.value)
    while start >= 0:
        end = start + len(fragment.value)
        affected = [slot for slot in slots if slot.kind == "text" and slot.end > start and slot.start < end]
        if affected and all(not slot.revision_context and not _inside_revision(slot.target) for slot in affected):
            first = affected[0]
            last = affected[-1]
            first_run = _nearest_ancestor(first.target, {"r"})
            last_run = _nearest_ancestor(last.target, {"r"})
            if first_run is None or last_run is None:
                return False
            parent = first_run.getparent()
            if parent is None or last_run.getparent() is not parent:
                return False
            try:
                first_index = parent.index(first_run)
                last_index = parent.index(last_run)
            except ValueError:
                return False
            if first_index > last_index:
                return False
            before = first.get()[:max(0, start - first.start)]
            after = last.get()[max(0, end - last.start):]
            insert_at = first_index
            for run in list(parent)[first_index:last_index + 1]:
                parent.remove(run)
            if before:
                parent.insert(insert_at, _clone_text_run(before, first_run))
                insert_at += 1
            parent.insert(insert_at, _build_revision_element(fragment, first_run))
            insert_at += 1
            if after:
                parent.insert(insert_at, _clone_text_run(after, last_run))
            _normalise_revision_ids(root)
            return True
        start = plain.find(fragment.value, start + 1)
    return False




def _replacement_dicts(replacements_payload: Iterable[dict | Replacement]) -> List[Dict[str, str]]:
    replacements: List[Dict[str, str]] = []
    for item in replacements_payload:
        if isinstance(item, Replacement):
            replacements.append({"placeholder": item.placeholder, "original": item.original, "category": item.category})
        else:
            replacements.append({
                "placeholder": str(item.get("placeholder", "")),
                "original": str(item.get("original", "")),
                "category": str(item.get("category", "")),
            })
    return replacements


def build_placeholder_restore_overrides(
    docx_bytes: bytes,
    replacements_payload: Iterable[dict | Replacement],
    merge_map: Dict[str, str],
) -> Dict[str, List[str]]:
    """Build occurrence-level restore originals for merged placeholders.

    Manual merge intentionally shows one placeholder in the AI-safe copy for
    values that the reviewer considers the same entity. A plain placeholder map
    would then restore every occurrence to the target value and lose source
    forms such as initials or inflected aliases. This plan records the original
    value in document order before the placeholder merge is applied.
    """
    if not merge_map:
        return {}
    replacements = _replacement_dicts(replacements_payload)
    original_by_placeholder = {
        r["placeholder"]: r["original"]
        for r in replacements
        if r.get("placeholder") and r.get("original")
    }
    watched = set(merge_map.keys()) | set(merge_map.values())
    watched = {ph for ph in watched if ph in original_by_placeholder}
    if not watched:
        return {}
    token_re = re.compile("|".join(re.escape(ph) for ph in sorted(watched, key=len, reverse=True)))
    overrides: Dict[str, List[str]] = {}
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        for info in zin.infolist():
            if not _part_is_content(info.filename):
                continue
            try:
                root = _parse_xml(zin.read(info.filename))
                slots, _plain = _walk_part_with_tc_awareness(root, include_attributes=True)
            except XmlSecurityError:
                raise
            except Exception:
                continue
            for slot in slots:
                txt = slot.get() or ""
                for match in token_re.finditer(txt):
                    placeholder = match.group(0)
                    final_placeholder = merge_map.get(placeholder, placeholder)
                    if final_placeholder not in original_by_placeholder:
                        continue
                    overrides.setdefault(final_placeholder, []).append(original_by_placeholder[placeholder])
    return {placeholder: originals for placeholder, originals in overrides.items() if len(set(originals)) > 1}


def _collect_original_revision_occurrence_plan(original_docx_bytes: bytes, replacements_payload: Iterable[dict | Replacement]) -> Dict[str, Dict[str, List[RevisionContextFragment | None]]]:
    """Map original occurrence order to revision context, per part and placeholder.

    The important lesson from OpenXmlRegex is that tracked replacements must be
    rebuilt exactly where the replacement target lives. Searching for the clear
    value after restore is ambiguous when the same value occurs both normally and
    inside tracked changes. This plan records, for every occurrence of an
    original value in the original DOCX, whether the corresponding occurrence was
    inside a revision wrapper. Restore can then apply the same occurrence index
    to the placeholder in the anonymized DOCX before replacing it.
    """
    replacements = [r for r in _replacement_dicts(replacements_payload) if r.get("placeholder") and r.get("original")]
    plan: Dict[str, Dict[str, List[RevisionContextFragment | None]]] = {}
    if not replacements:
        return plan
    with zipfile.ZipFile(io.BytesIO(original_docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        for info in zin.infolist():
            if not _part_is_content(info.filename):
                continue
            try:
                root = _parse_xml(zin.read(info.filename))
                slots, plain = _walk_part_with_tc_awareness(root, include_attributes=False)
            except Exception:
                continue
            part_plan: Dict[str, List[RevisionContextFragment | None]] = {}
            for r in replacements:
                placeholder = r["placeholder"]
                original = r["original"]
                occurrence_plan: List[RevisionContextFragment | None] = []
                start = plain.find(original)
                while start >= 0:
                    end = start + len(original)
                    affected = [slot for slot in slots if slot.kind == "text" and slot.end > start and slot.start < end]
                    fragment: RevisionContextFragment | None = None
                    contexts = {slot.revision_context for slot in affected if slot.revision_context}
                    if affected and len(contexts) == 1:
                        kind = next(iter(contexts))
                        # Only plan to rebuild DELETION wrappers (<w:del>, <w:moveFrom>).
                        # Insertion wrappers (<w:ins>) are NOT rebuilt: an insertion that
                        # was accepted by Word or Claude should remain as plain text after
                        # restore.  Rebuilding <w:ins> caused every pseudonymised value to
                        # appear as a tracked insertion in documents written with TC always on.
                        if kind in {"del", "moveFrom"}:
                            ancestor = _nearest_ancestor(affected[0].target, {kind})
                            if ancestor is not None:
                                fragment = RevisionContextFragment(info.filename, kind, original, _revision_attrs(ancestor))
                    occurrence_plan.append(fragment)
                    start = plain.find(original, start + max(1, len(original)))
                if occurrence_plan:
                    part_plan[placeholder] = occurrence_plan
            if part_plan:
                plan[info.filename] = part_plan
    return plan


def _find_nth_occurrence(text: str, needle: str, occurrence_index: int) -> int:
    if not needle or occurrence_index < 0:
        return -1
    start = -1
    pos = 0
    for _ in range(occurrence_index + 1):
        start = text.find(needle, pos)
        if start < 0:
            return -1
        pos = start + len(needle)
    return start


def _replace_nth_placeholder_with_revision_fragment(root: etree._Element, placeholder: str, occurrence_index: int, fragment: RevisionContextFragment) -> bool:
    """Restore one placeholder occurrence as tracked-change OOXML in-place.

    This acts before ordinary restore, while the placeholder is still present.
    It therefore avoids the ambiguity of value-after-restore matching, where
    code could wrap the wrong duplicate value or fail after surrounding edits.
    """
    slots, plain = _walk_part_with_tc_awareness(root, include_attributes=False)
    start = _find_nth_occurrence(plain, placeholder, occurrence_index)
    if start < 0:
        return False
    end = start + len(placeholder)
    affected = [slot for slot in slots if slot.kind == "text" and slot.end > start and slot.start < end]
    if not affected:
        return False
    # If the placeholder is still inside a revision wrapper, normal restore is
    # already correct because it changes <w:t>/<w:delText> in place.
    if any(slot.revision_context or _inside_revision(slot.target) for slot in affected):
        return False
    first = affected[0]
    last = affected[-1]
    first_run = _nearest_ancestor(first.target, {"r"})
    last_run = _nearest_ancestor(last.target, {"r"})
    if first_run is None or last_run is None:
        return False
    parent = first_run.getparent()
    if parent is None or last_run.getparent() is not parent:
        return False
    try:
        first_index = parent.index(first_run)
        last_index = parent.index(last_run)
    except ValueError:
        return False
    if first_index > last_index:
        return False
    before = first.get()[:max(0, start - first.start)]
    after = last.get()[max(0, end - last.start):]
    insert_at = first_index
    for run in list(parent)[first_index:last_index + 1]:
        parent.remove(run)
    if before:
        parent.insert(insert_at, _clone_text_run(before, first_run))
        insert_at += 1
    parent.insert(insert_at, _build_revision_element(fragment, first_run))
    insert_at += 1
    if after:
        parent.insert(insert_at, _clone_text_run(after, last_run))
    _normalise_revision_ids(root)
    return True


def _pre_restore_flattened_revision_placeholders(docx_bytes: bytes, original_docx_bytes: bytes | None, replacements_payload: Iterable[dict | Replacement]) -> Tuple[bytes, Dict[str, Any]]:
    """Restore flattened revision placeholders before ordinary text restore.

    If Word/Claude flattened <w:ins>/<w:del> in the anonymized copy, the safest
    available anchor is still the placeholder. Rebuild the original revision
    context at the placeholder occurrence that corresponds to the same occurrence
    index in the original document, then let ordinary restore handle the rest.
    """
    report: Dict[str, Any] = {
        "available_revision_occurrences": 0,
        "rebuilt_revision_placeholders": 0,
        "rebuilt_by_placeholder": {},
        "processed_parts": [],
        "skipped_parts": [],
    }
    if not original_docx_bytes:
        return docx_bytes, report
    plan = _collect_original_revision_occurrence_plan(original_docx_bytes, replacements_payload)
    report["available_revision_occurrences"] = sum(
        1 for part in plan.values() for fragments in part.values() for fragment in fragments if fragment is not None
    )
    if not plan:
        return docx_bytes, report
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in plan:
                    try:
                        root = _parse_xml(data)
                        changed = False
                        part_plan = plan[info.filename]
                        for placeholder, fragments in part_plan.items():
                            # Process from the end so occurrence indexes remain stable
                            # as placeholders are replaced with clear text.
                            for occurrence_index in range(len(fragments) - 1, -1, -1):
                                fragment = fragments[occurrence_index]
                                if fragment is None:
                                    continue
                                if _replace_nth_placeholder_with_revision_fragment(root, placeholder, occurrence_index, fragment):
                                    changed = True
                                    report["rebuilt_revision_placeholders"] = int(report.get("rebuilt_revision_placeholders", 0) or 0) + 1
                                    counts = report.setdefault("rebuilt_by_placeholder", {})
                                    counts[placeholder] = int(counts.get(placeholder, 0) or 0) + 1
                        if changed:
                            data = _serialize_xml(root)
                        report["processed_parts"].append(info.filename)
                    except XmlSecurityError:
                        raise
                    except Exception:
                        report["skipped_parts"].append(info.filename)
                _zip_writestr_preserving(zout, info, data)
    return out.getvalue(), report


def restore_docx_preserving_tc_with_original_context(
    docx_bytes: bytes,
    replacements_payload: Iterable[dict | Replacement],
    original_docx_bytes: bytes | None = None,
    placeholder_restore_overrides: Dict[str, List[str]] | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """Restore DOCX while rebuilding flattened tracked changes at placeholders.

    This is the context-aware restore path. It first uses the original DOCX only
    as a local structural reference, never exposing it externally, to rebuild
    revision wrappers at placeholder positions. Then it runs the normal restore
    for all remaining placeholders.
    """
    pre_bytes, pre_report = _pre_restore_flattened_revision_placeholders(docx_bytes, original_docx_bytes, replacements_payload)
    restored, report = restore_docx_preserving_tc(
        pre_bytes,
        replacements_payload,
        placeholder_restore_overrides=placeholder_restore_overrides,
    )
    rebuilt_by_placeholder = dict(pre_report.get("rebuilt_by_placeholder", {}) or {})
    rebuilt_total = int(pre_report.get("rebuilt_revision_placeholders", 0) or 0)
    if rebuilt_total:
        report["restored_occurrences"] = int(report.get("restored_occurrences", 0) or 0) + rebuilt_total
        missing = [ph for ph in report.get("missing_placeholders", []) if ph not in rebuilt_by_placeholder]
        report["missing_placeholders"] = missing
        report["missing_total"] = len(missing)
        expected = {r["placeholder"] for r in _replacement_dicts(replacements_payload) if r.get("placeholder")}
        found_count = len(expected - set(missing))
        report["found_total"] = found_count
        report["all_found"] = not missing
    report["pre_revision_context_rebuild"] = pre_report
    return restored, report

def overlay_original_revision_contexts(restored_docx_bytes: bytes, original_docx_bytes: bytes | None, replacements_payload: Iterable[dict | Replacement]) -> Tuple[bytes, Dict[str, Any]]:
    """Reapply original tracked-change wrappers around restored anonymized values.

    Normal restore edits placeholders in place and is enough when the anonymized
    package still contains revision wrappers. This overlay handles the observed
    Word/Claude regression where a placeholder that originally lived inside a
    tracked change returns as plain text after round-tripping. It mechanically
    copies only original revision elements containing protected values back into
    the restored DOCX, and only where the matching text is currently outside any
    revision context.
    """
    report = {"available_fragments": 0, "reapplied_fragments": 0, "processed_parts": [], "skipped_parts": []}
    if not original_docx_bytes:
        return restored_docx_bytes, report
    originals: List[str] = []
    for item in replacements_payload:
        if isinstance(item, Replacement):
            originals.append(str(item.original or ""))
        else:
            originals.append(str(item.get("original", "") or ""))
    fragments = _collect_original_revision_fragments(original_docx_bytes, originals)
    report["available_fragments"] = sum(len(v) for v in fragments.values())
    if not fragments:
        return restored_docx_bytes, report

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(restored_docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename in fragments:
                    try:
                        root = _parse_xml(data)
                        changed = False
                        for fragment in fragments[info.filename]:
                            if _revision_value_already_present(root, fragment):
                                continue
                            # Case A: value is inside a revision of the right kind but
                            # with a wrong author (e.g. anonymised "Osoba_1").  Fix the
                            # attributes in-place rather than rebuilding the whole wrapper.
                            # Applied for both insertion and deletion contexts.
                            if _fix_wrong_author_revision_fragment(root, fragment):
                                report["reapplied_fragments"] = int(report.get("reapplied_fragments", 0) or 0) + 1
                                changed = True
                                continue
                            # Case B: value has been flattened to plain text — wrap it.
                            # Only applied for DELETION contexts (<w:del>, <w:moveFrom>).
                            # Insertion contexts (<w:ins>) are NOT re-created because:
                            #   1. The insertion may have been intentionally accepted by the
                            #      user or Claude during the anonymised phase.
                            #   2. Re-creating <w:ins> wrappers caused every pseudonymised
                            #      value to appear as a tracked insertion when the original
                            #      document was created with Track Changes permanently on
                            #      (all text inside <w:ins> elements).
                            if fragment.kind in {"del", "moveFrom"} and _replace_normal_text_with_revision_fragment(root, fragment):
                                report["reapplied_fragments"] = int(report.get("reapplied_fragments", 0) or 0) + 1
                                changed = True
                        if changed:
                            data = _serialize_xml(root)
                        report["processed_parts"].append(info.filename)
                    except XmlSecurityError:
                        raise
                    except Exception:
                        report["skipped_parts"].append(info.filename)
                _zip_writestr_preserving(zout, info, data)
    return out.getvalue(), report


def restore_docx_preserving_tc(
    docx_bytes: bytes,
    replacements_payload: Iterable[dict | Replacement],
    placeholder_restore_overrides: Dict[str, List[str]] | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    """Restore placeholders in a v3-masked DOCX package without touching revisions."""
    replacements: List[Dict[str, str]] = []
    for item in replacements_payload:
        if isinstance(item, Replacement):
            replacements.append({"placeholder": item.placeholder, "original": item.original, "category": item.category})
        else:
            replacements.append({"placeholder": str(item.get("placeholder", "")), "original": str(item.get("original", "")), "category": str(item.get("category", ""))})
    expected = {r["placeholder"] for r in replacements if r.get("placeholder")}
    found: Dict[str, int] = {ph: 0 for ph in expected}
    restored_occurrences = 0
    processed_parts: List[str] = []
    skipped_parts: List[str] = []
    restore_overrides = {
        str(placeholder): [str(original) for original in originals if str(original)]
        for placeholder, originals in (placeholder_restore_overrides or {}).items()
        if str(placeholder) and isinstance(originals, list)
    }
    override_positions: Dict[str, int] = {placeholder: 0 for placeholder in restore_overrides}
    default_lookup = {r["placeholder"]: r["original"] for r in replacements if r.get("placeholder")}
    replacement_pairs = [
        (r["placeholder"], r["original"])
        for r in replacements
        if r.get("placeholder") and r["placeholder"] not in restore_overrides
    ]

    override_lookup = dict(restore_overrides)
    pair_lookup = {placeholder: original for placeholder, original in replacement_pairs}
    # All placeholders that this map can restore. Matching is done longest-first
    # so that a placeholder never swallows a longer sibling with the same prefix
    # (e.g. "[FIRMA_3]" must not shadow "[FIRMA_3_ALIAS_1]").
    all_placeholders = sorted(
        set(override_lookup) | set(pair_lookup),
        key=len,
        reverse=True,
    )
    placeholder_re = (
        re.compile("|".join(re.escape(ph) for ph in all_placeholders))
        if all_placeholders
        else None
    )

    def _original_for_match(placeholder: str) -> str:
        nonlocal restored_occurrences
        found[placeholder] = found.get(placeholder, 0) + 1
        restored_occurrences += 1
        if placeholder in override_lookup:
            originals = override_lookup.get(placeholder) or []
            idx = override_positions.get(placeholder, 0)
            override_positions[placeholder] = idx + 1
            if idx < len(originals):
                return originals[idx]
            return default_lookup.get(placeholder, "")
        return pair_lookup.get(placeholder, "")

    def _restore_part_slots(slots: List[TextSlot], plain: str) -> bool:
        """Restore placeholders across the contiguous per-part plain view.

        Restoring per individual <w:t> slot fails when Word (or the AI round
        trip) splits a placeholder across several runs inside the same revision
        wrapper, e.g. "[FIRMA_3" in one run and "]" in the next. That left the
        truncated fragment visible and undetectable (it has no closing bracket).
        Here we search the contiguous plain view, which already stitches runs
        within a single revision context, and splice each match across every
        affected slot using the same range logic used during masking.
        """
        if placeholder_re is None:
            return False
        matches = list(placeholder_re.finditer(plain))
        if not matches:
            return False
        # Resolve replacements in document (forward) order so occurrence-ordered
        # override originals are consumed in the correct sequence, then splice
        # from the end so slot boundaries stay valid as we edit in place.
        resolved = [(m.start(), m.end(), _original_for_match(m.group(0))) for m in matches]
        for start, end, original in reversed(resolved):
            _replace_range_in_slots(slots, start, end, original)
        return True

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        _check_docx_xml_uncompressed_limit(zin)
        with _open_docx_output_zip(out) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if _part_is_content(info.filename):
                    try:
                        root = _parse_xml(data)
                        slots, plain = _walk_part_with_tc_awareness(root, include_attributes=True)
                        if _restore_part_slots(slots, plain):
                            data = _serialize_xml(root)
                        processed_parts.append(info.filename)
                    except XmlSecurityError:
                        raise
                    except Exception:
                        skipped_parts.append(info.filename)
                _zip_writestr_preserving(zout, info, data)

    found_placeholders = {ph for ph, count in found.items() if count > 0}
    missing = sorted(expected - found_placeholders)

    # Unknown placeholders after restore are placeholders that remain in the output
    # but were not part of this map. Keep this simple and package-wide.
    unknown = set()
    try:
        with zipfile.ZipFile(io.BytesIO(out.getvalue()), "r") as zf:
            for name in zf.namelist():
                if not _part_is_content(name):
                    continue
                raw = zf.read(name)
                try:
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
                for ph in PLACEHOLDER_RE.findall(text):
                    if ph not in expected:
                        unknown.add(ph)
    except Exception:
        pass

    report = {
        "expected_total": len(expected),
        "found_total": len(found_placeholders),
        "missing_total": len(missing),
        "missing_placeholders": missing,
        "unknown_total": len(unknown),
        "unknown_placeholders": sorted(unknown),
        "restored_occurrences": restored_occurrences,
        "all_found": not missing,
        "processed_parts": processed_parts,
        "skipped_parts": skipped_parts,
        "engine_version": ENGINE_VERSION,
        "placeholder_restore_overrides_applied": {
            placeholder: override_positions.get(placeholder, 0)
            for placeholder in sorted(restore_overrides)
        },
    }
    return out.getvalue(), report
