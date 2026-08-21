import base64
import io
import os
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from lxml import etree

from api import app

os.environ["CSM_API_TOKEN"] = "test-token"
from redactor import make_replacements_with_controls

ROOT = Path(__file__).resolve().parents[1]
HDR = {"X-CSM-Token": "test-token"}
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _simple_docx(text: str) -> bytes:
    buf = io.BytesIO()
    xml = (
        f"<?xml version='1.0' encoding='UTF-8'?><w:document xmlns:w='{W_NS}'>"
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>"
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            "<?xml version='1.0' encoding='UTF-8'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>"
            "</Relationships>",
        )
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def _visible_docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    return "".join(node.text or "" for node in root.findall(f".//{W}t"))


def test_v0421_versions_and_instruction_doc():
    assert 'from version import APP_VERSION' in read('server/api.py')
    assert 'const APP_VERSION = "1.6"' in read('addin/taskpane.js')
    assert '<Version>1.6</Version>' in read('addin/manifest.xml')
    assert (ROOT / 'Instrukcja_CSM_v1_6.docx').exists()
    assert not (ROOT / 'Instrukcja_CSM_v0_4_1_1.docx').exists()
    assert (ROOT / 'RELEASE-NOTES-v1.6.txt').exists()


def test_v0421_frontend_has_merge_and_clear_controls():
    html = read('addin/taskpane.html')
    js = read('addin/taskpane.js')
    assert 'manualMerge' in html
    assert 'btnClearManualControls' in html
    assert 'merge_placeholders' in js
    assert 'const mergeText = ($("manualMerge")' in js
    assert 'clearManualControls' in js
    assert 'btnClearManualControls' in js


def test_v0421_manual_controls_can_create_merge_list():
    text = 'Jan Nowacki podpisał dokument. J. Nowacki potwierdził.'
    masked, reps = make_replacements_with_controls(text, {'always': [{'value': 'J. Nowacki', 'category': 'PERSON_ALIAS'}]})
    placeholders = {r.placeholder for r in reps}
    assert any(ph.startswith('[OSOBA') for ph in placeholders)


def test_v0421_map_preview_endpoint_still_works():
    client = TestClient(app)
    health = client.get('/health')
    assert health.json()['version'] == '1.6'


def test_v0421_remask_merges_placeholders_in_docx_and_map():
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions
    client = TestClient(app)
    original = base64.b64encode(_build_docx_with_revisions()).decode('ascii')
    prepared = client.post('/v4/current/prepare', headers=HDR, json={'docx_base64': original, 'filename': 'umowa.docx', 'open_file': False}).json()
    preview = client.post('/v4/map/preview', headers=HDR, json={'map_id': prepared['map_id']}).json()
    persons = [r for r in preview['replacements'] if r['category'] == 'PERSON']
    assert len(persons) >= 2
    src = persons[1]['placeholder']
    dst = persons[0]['placeholder']
    remask = client.post('/v4/current/remask-session', headers=HDR, json={
        'map_id': prepared['map_id'],
        'session_id': prepared['session_id'],
        'filename': 'umowa.docx',
        'open_file': False,
        'controls': {'merge_placeholders': [{'source': src, 'target': dst}]},
    })
    assert remask.status_code == 200, remask.text
    data = remask.json()
    raw = Path(data['anon_path']).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml = zf.read('word/document.xml').decode('utf-8')
    assert src not in xml
    assert dst in xml
    merged_preview = client.post('/v4/map/preview', headers=HDR, json={'map_id': data['map_id']}).json()
    placeholders = {r['placeholder'] for r in merged_preview['replacements']}
    assert src not in placeholders
    assert dst in placeholders


def test_v13_placeholder_merge_restores_each_original_surface():
    client = TestClient(app)
    original_docx = _simple_docx("Jan Kowalski oraz Anna Nowak podpisali dokument.")
    original = base64.b64encode(original_docx).decode("ascii")
    prepared = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    ).json()
    preview = client.post("/v4/map/preview", headers=HDR, json={"map_id": prepared["map_id"]}).json()
    person_by_original = {r["original"]: r for r in preview["replacements"] if r["category"] == "PERSON"}
    assert "Jan Kowalski" in person_by_original
    assert "Anna Nowak" in person_by_original

    src = person_by_original["Anna Nowak"]["placeholder"]
    dst = person_by_original["Jan Kowalski"]["placeholder"]
    remask = client.post(
        "/v4/current/remask-session",
        headers=HDR,
        json={
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "filename": "umowa.docx",
            "open_file": False,
            "controls": {"merge_placeholders": [{"source": src, "target": dst}]},
        },
    )
    assert remask.status_code == 200, remask.text
    remasked = remask.json()
    anon_bytes = Path(remasked["anon_path"]).read_bytes()
    anon_text = _visible_docx_text(anon_bytes)
    assert src not in anon_text
    assert anon_text.count(dst) == 2

    restored = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={
            "docx_base64": base64.b64encode(anon_bytes).decode("ascii"),
            "filename": remasked["suggested_filename"],
            "map_id": remasked["map_id"],
            "session_id": remasked["session_id"],
            "open_file": False,
        },
    )
    assert restored.status_code == 200, restored.text
    restored_bytes = Path(restored.json()["restored_path"]).read_bytes()
    restored_text = _visible_docx_text(restored_bytes)
    assert "Jan Kowalski oraz Anna Nowak podpisali dokument." in restored_text
