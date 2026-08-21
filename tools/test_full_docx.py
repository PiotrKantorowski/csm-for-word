"""Test sidecar tracked-replace against a DOCX with all document parts."""
import io, zipfile, base64, json, subprocess, os, shlex

SIDECAR_CMD = os.environ.get("CSM_REVISION_SIDECAR_CMD", "dotnet run --project sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj --")

ns_ct = "http://schemas.openxmlformats.org/package/2006/content-types"
ns_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ns_wrel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def make_full_docx() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Types xmlns='" + ns_ct + "'>"
            "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
            "<Override PartName='/word/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'/>"
            "<Override PartName='/word/header1.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'/>"
            "<Override PartName='/word/footer1.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml'/>"
            "<Override PartName='/word/footnotes.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'/>"
            "<Override PartName='/word/endnotes.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml'/>"
            "<Override PartName='/word/comments.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml'/>"
            "</Types>")
        zf.writestr("_rels/.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='" + ns_rel + "'>"
            "<Relationship Id='rId1' Type='" + ns_wrel + "/officeDocument' Target='word/document.xml'/>"
            "</Relationships>")
        zf.writestr("word/_rels/document.xml.rels",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<Relationships xmlns='" + ns_rel + "'>"
            "<Relationship Id='rId1' Type='" + ns_wrel + "/styles' Target='styles.xml'/>"
            "<Relationship Id='rId2' Type='" + ns_wrel + "/header' Target='header1.xml'/>"
            "<Relationship Id='rId3' Type='" + ns_wrel + "/footer' Target='footer1.xml'/>"
            "<Relationship Id='rId4' Type='" + ns_wrel + "/footnotes' Target='footnotes.xml'/>"
            "<Relationship Id='rId5' Type='" + ns_wrel + "/endnotes' Target='endnotes.xml'/>"
            "<Relationship Id='rId6' Type='" + ns_wrel + "/comments' Target='comments.xml'/>"
            "</Relationships>")
        zf.writestr("word/styles.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:styles xmlns:w='" + ns_w + "'>"
            "<w:style w:type='paragraph' w:default='1' w:styleId='Normal'><w:name w:val='Normal'/></w:style>"
            "</w:styles>")
        zf.writestr("word/document.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:document xmlns:w='" + ns_w + "' xmlns:r='" + ns_wrel + "'>"
            "<w:body>"
            "<w:p><w:r><w:t>Umowa najmu: Jan Kowalski jako najemca.</w:t></w:r></w:p>"
            "<w:sectPr>"
            "<w:headerReference w:type='default' r:id='rId2'/>"
            "<w:footerReference w:type='default' r:id='rId3'/>"
            "</w:sectPr>"
            "</w:body></w:document>")
        zf.writestr("word/header1.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:hdr xmlns:w='" + ns_w + "'>"
            "<w:p><w:r><w:t>Naglek: Jan Kowalski</w:t></w:r></w:p>"
            "</w:hdr>")
        zf.writestr("word/footer1.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:ftr xmlns:w='" + ns_w + "'>"
            "<w:p><w:r><w:t>Stopka: Jan Kowalski</w:t></w:r></w:p>"
            "</w:ftr>")
        zf.writestr("word/footnotes.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:footnotes xmlns:w='" + ns_w + "'>"
            "<w:footnote w:type='normal' w:id='1'>"
            "<w:p><w:r><w:t>Przypis: Jan Kowalski</w:t></w:r></w:p>"
            "</w:footnote>"
            "</w:footnotes>")
        zf.writestr("word/endnotes.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:endnotes xmlns:w='" + ns_w + "'>"
            "<w:endnote w:type='normal' w:id='1'>"
            "<w:p><w:r><w:t>Przypis koncowy: Jan Kowalski</w:t></w:r></w:p>"
            "</w:endnote>"
            "</w:endnotes>")
        zf.writestr("word/comments.xml",
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:comments xmlns:w='" + ns_w + "'>"
            "<w:comment w:id='0' w:author='Test' w:date='2026-01-01T00:00:00Z'>"
            "<w:p><w:r><w:t>Komentarz: Jan Kowalski</w:t></w:r></w:p>"
            "</w:comment>"
            "</w:comments>")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    docx_b64 = make_full_docx()
    print(f"Input DOCX base64 length: {len(docx_b64)}")

    payload = {
        "protocol_version": "0.1",
        "action": "tracked-replace",
        "docx_base64": docx_b64,
        "author": "CSM Test",
        "operations": [
            {"anchor_id": "CSM_ANCHOR:1", "original_text": "Jan Kowalski", "replacement_text": "[OSOBA_1]"}
        ]
    }

    proc = subprocess.run(
        shlex.split(SIDECAR_CMD),
        input=json.dumps(payload), text=True, capture_output=True, timeout=60
    )
    result = json.loads(proc.stdout)
    print(f"RC={proc.returncode} ok={result.get('ok')} status={result.get('status')}")

    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}")
        print(f"STDERR: {proc.stderr[:500]}")
        return 1

    raw = base64.b64decode(result["docx_base64"])
    with open(os.path.join(os.path.dirname(__file__), "test_full_docx_output.docx"), "wb") as f:
        f.write(raw)
    print("Output DOCX written to test_full_docx_output.docx")

    parts_checked = []
    all_pass = True
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for part_name in sorted(zf.namelist()):
            if not part_name.endswith(".xml"):
                continue
            content = zf.read(part_name).decode("utf-8", errors="replace")
            has_ins = "w:ins" in content
            has_del = "w:del" in content
            has_orig = "Jan Kowalski" in content
            has_repl = "[OSOBA_1]" in content
            note = ""
            if part_name in ("word/document.xml", "word/header1.xml", "word/footer1.xml",
                             "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"):
                # Tracked changes: w:ins + w:del must be present.
                # Original text may still appear inside <w:del> — that is correct.
                # The replacement must appear in the output.
                pass_part = has_ins and has_del and has_repl
                if not pass_part:
                    all_pass = False
                    note = " <<< FAIL"
                else:
                    note = " [OK]"
            if has_ins or has_del or has_orig or has_repl:
                parts_checked.append(part_name)
                print(f"  {part_name}: w:ins={has_ins} w:del={has_del} orig_in_del={has_orig} repl_present={has_repl}{note}")

    print()
    print("RESULT:", "ALL PARTS PASS" if all_pass else "SOME PARTS FAILED")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
