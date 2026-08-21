// CSM.RevisionSidecar.Tests — 10 tests as specified in CLAUDE_CODE_CSM_ITER9_SIDECAR_OPENXML_TASK.md
// Tests call SidecarEngine methods directly (no subprocess overhead).
// All tests require the Clippit NuGet package to be restored (dotnet restore).

using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;
using CSM.RevisionSidecar;
using Xunit;

namespace CSM.RevisionSidecar.Tests;

public sealed class SidecarEngineTests
{
    // ------------------------------------------------------------------
    // Minimal DOCX factory
    // ------------------------------------------------------------------

    private static byte[] MinimalDocx(string bodyText = "Hello CSM")
    {
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            // Clippit (WmlDocument, WmlComparer) requires proper MIME types + styles part
            AddEntry(zip, "[Content_Types].xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>" +
                "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>" +
                "<Default Extension='xml' ContentType='application/xml'/>" +
                "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>" +
                "<Override PartName='/word/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'/>" +
                "</Types>");

            AddEntry(zip, "_rels/.rels",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>" +
                "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>" +
                "</Relationships>");

            AddEntry(zip, "word/_rels/document.xml.rels",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>" +
                "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles' Target='styles.xml'/>" +
                "</Relationships>");

            AddEntry(zip, "word/styles.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:styles xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>" +
                "<w:style w:type='paragraph' w:default='1' w:styleId='Normal'>" +
                "<w:name w:val='Normal'/></w:style>" +
                "</w:styles>");

            AddEntry(zip, "word/document.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>" +
                "<w:body><w:p><w:r><w:t>" + SecurityEncodeXml(bodyText) + "</w:t></w:r></w:p>" +
                "<w:sectPr/></w:body></w:document>");
        }
        return ms.ToArray();
    }

    private static void AddEntry(ZipArchive zip, string name, string content)
    {
        var entry = zip.CreateEntry(name);
        using var writer = new StreamWriter(entry.Open(), Encoding.UTF8);
        writer.Write(content);
    }

    private static string SecurityEncodeXml(string s) =>
        s.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;");

    private static string ToBase64(byte[] bytes) => Convert.ToBase64String(bytes);

    private static bool IsValidDocx(string base64)
    {
        try
        {
            var raw = Convert.FromBase64String(base64);
            using var zip = new ZipArchive(new MemoryStream(raw), ZipArchiveMode.Read);
            return zip.GetEntry("word/document.xml") is not null;
        }
        catch { return false; }
    }

    private static string GetDocumentXml(string base64)
    {
        var raw = Convert.FromBase64String(base64);
        using var zip = new ZipArchive(new MemoryStream(raw), ZipArchiveMode.Read);
        var entry = zip.GetEntry("word/document.xml")!;
        using var reader = new StreamReader(entry.Open());
        return reader.ReadToEnd();
    }

    private static string GetZipEntryText(string base64, string entryName)
    {
        var raw = Convert.FromBase64String(base64);
        using var zip = new ZipArchive(new MemoryStream(raw), ZipArchiveMode.Read);
        var entry = zip.GetEntry(entryName)!;
        using var reader = new StreamReader(entry.Open());
        return reader.ReadToEnd();
    }

    private static byte[] MinimalDocxWithHeaderAndFooter(string bodyText, string headerText, string footerText)
    {
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            AddEntry(zip, "[Content_Types].xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>" +
                "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>" +
                "<Default Extension='xml' ContentType='application/xml'/>" +
                "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>" +
                "<Override PartName='/word/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'/>" +
                "<Override PartName='/word/header1.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'/>" +
                "<Override PartName='/word/footer1.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml'/>" +
                "</Types>");

            AddEntry(zip, "_rels/.rels",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>" +
                "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>" +
                "</Relationships>");

            AddEntry(zip, "word/_rels/document.xml.rels",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>" +
                "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles' Target='styles.xml'/>" +
                "<Relationship Id='rId2' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/header' Target='header1.xml'/>" +
                "<Relationship Id='rId3' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer' Target='footer1.xml'/>" +
                "</Relationships>");

            AddEntry(zip, "word/styles.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:styles xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>" +
                "<w:style w:type='paragraph' w:default='1' w:styleId='Normal'>" +
                "<w:name w:val='Normal'/></w:style>" +
                "</w:styles>");

            AddEntry(zip, "word/document.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>" +
                "<w:body><w:p><w:r><w:t>" + SecurityEncodeXml(bodyText) + "</w:t></w:r></w:p>" +
                "<w:sectPr><w:headerReference w:type='default' r:id='rId2'/><w:footerReference w:type='default' r:id='rId3'/></w:sectPr>" +
                "</w:body></w:document>");

            AddEntry(zip, "word/header1.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:hdr xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>" +
                "<w:p><w:r><w:t>" + SecurityEncodeXml(headerText) + "</w:t></w:r></w:p></w:hdr>");

            AddEntry(zip, "word/footer1.xml",
                "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>" +
                "<w:ftr xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>" +
                "<w:p><w:r><w:t>" + SecurityEncodeXml(footerText) + "</w:t></w:r></w:p></w:ftr>");
        }
        return ms.ToArray();
    }

    // ------------------------------------------------------------------
    // 1. status_returns_capabilities
    // ------------------------------------------------------------------

    [Fact]
    public void status_returns_capabilities()
    {
        // The status action is handled in Program.cs dispatch, but we can verify
        // the StatusResponse would be correctly formed by checking the constants.
        Assert.Equal("CSM.RevisionSidecar", SidecarEngine.EngineId);
        Assert.Equal("Clippit/OpenXmlPowerTools", SidecarEngine.ClippitEngine);
        // Capabilities are set to true in StatusResponse(allTrue: true) in Program.cs
        // This test verifies the engine identity strings are correct.
    }

    // ------------------------------------------------------------------
    // 2. normalize_rejects_invalid_base64
    // ------------------------------------------------------------------

    [Fact]
    public void normalize_rejects_invalid_base64()
    {
        var v = SidecarEngine.ValidateDocxBase64("!!!not-base64!!!", "docx_base64");
        Assert.False(v.Valid);
        Assert.Equal("invalid_docx_base64", v.ErrorCode);
    }

    // ------------------------------------------------------------------
    // 3. normalize_rejects_non_docx_zip
    // ------------------------------------------------------------------

    [Fact]
    public void normalize_rejects_non_docx_zip()
    {
        // Valid ZIP but missing word/document.xml
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            var e = zip.CreateEntry("readme.txt");
            using var w = new StreamWriter(e.Open());
            w.Write("not a docx");
        }
        var b64 = ToBase64(ms.ToArray());
        var v = SidecarEngine.ValidateDocxBase64(b64, "docx_base64");
        Assert.False(v.Valid);
        Assert.Equal("missing_document_xml", v.ErrorCode);
    }

    // ------------------------------------------------------------------
    // 4. normalize_returns_valid_docx_when_supported
    // ------------------------------------------------------------------

    [Fact]
    public void normalize_returns_valid_docx_when_supported()
    {
        // Document with a simple tracked insertion — RevisionAccepter should accept it.
        // We use a plain document here; Clippit handles the accept internally.
        var docxBytes = MinimalDocx("Jan Kowalski podpisał umowę.");
        var (docxBase64, errorCode, errorMessage) = SidecarEngine.ExecuteNormalize(docxBytes);

        Assert.Null(errorCode);
        Assert.Null(errorMessage);
        Assert.NotNull(docxBase64);
        Assert.True(IsValidDocx(docxBase64!));
    }

    // ------------------------------------------------------------------
    // 5. compare_rejects_missing_original
    // ------------------------------------------------------------------

    [Fact]
    public void compare_rejects_missing_original()
    {
        var req = new SidecarRequest(
            ProtocolVersion: "0.1",
            Action: "compare",
            DocxBase64: null,
            RevisedDocxBase64: ToBase64(MinimalDocx("revised")),
            Operations: null,
            Author: "CSM",
            MapId: ""
        );
        var v = SidecarEngine.ValidateDocxInputs(req, "compare");
        Assert.False(v.Valid);
        Assert.Equal("missing_docx_base64", v.ErrorCode);
    }

    // ------------------------------------------------------------------
    // 6. compare_returns_valid_docx_when_supported
    // ------------------------------------------------------------------

    [Fact]
    public void compare_returns_valid_docx_when_supported()
    {
        var original = MinimalDocx("Original text here.");
        var revised  = MinimalDocx("Revised text here.");
        var (docxBase64, errorCode, errorMessage) =
            SidecarEngine.ExecuteCompare(original, revised, "CSM Test");

        Assert.Null(errorCode);
        Assert.Null(errorMessage);
        Assert.NotNull(docxBase64);
        Assert.True(IsValidDocx(docxBase64!));
    }

    // ------------------------------------------------------------------
    // 7. tracked_replace_rejects_empty_operations
    // ------------------------------------------------------------------

    [Fact]
    public void tracked_replace_rejects_empty_operations()
    {
        var ops = new List<ParsedOperation>();
        var (_, errorCode, errorMessage, _) =
            SidecarEngine.ExecuteTrackedReplace(MinimalDocx(), ops, "CSM");

        Assert.Equal("missing_operations", errorCode);
        Assert.NotNull(errorMessage);
    }

    // ------------------------------------------------------------------
    // 8. tracked_replace_returns_valid_docx
    // ------------------------------------------------------------------

    [Fact]
    public void tracked_replace_returns_valid_docx()
    {
        var docx = MinimalDocx("Jan Kowalski podpisał umowę.");
        var ops  = new List<ParsedOperation>
        {
            new ParsedOperation("Jan Kowalski", "[[CSM_PERSON_1]]", "CSM_ANCHOR:1", "PERSON"),
        };
        var (docxBase64, errorCode, _, _) =
            SidecarEngine.ExecuteTrackedReplace(docx, ops, "CSM");

        Assert.Null(errorCode);
        Assert.NotNull(docxBase64);
        Assert.True(IsValidDocx(docxBase64!));
    }

    // ------------------------------------------------------------------
    // 9. tracked_replace_result_contains_w_ins_and_w_del
    // ------------------------------------------------------------------

    [Fact]
    public void tracked_replace_result_contains_w_ins_and_w_del()
    {
        var docx = MinimalDocx("Jan Kowalski podpisał umowę.");
        var ops  = new List<ParsedOperation>
        {
            new ParsedOperation("Jan Kowalski", "[[CSM_PERSON_1]]", "CSM_ANCHOR:1", "PERSON"),
        };
        var (docxBase64, errorCode, _, revisionCount) =
            SidecarEngine.ExecuteTrackedReplace(docx, ops, "CSM");

        Assert.Null(errorCode);
        Assert.True(revisionCount > 0, "Expected at least one tracked revision.");

        var xml = GetDocumentXml(docxBase64!);
        Assert.Contains("w:ins", xml);
        Assert.Contains("w:del", xml);
    }

    // ------------------------------------------------------------------
    // 10. tracked_replace_preserves_valid_zip_and_word_document_xml
    // ------------------------------------------------------------------

    [Fact]
    public void tracked_replace_preserves_valid_zip_and_word_document_xml()
    {
        var docx = MinimalDocx("Strony postanawiają zawrzeć umowę.");
        var ops  = new List<ParsedOperation>
        {
            new ParsedOperation("Strony", "[[CSM_ENTITY_1]]", "CSM_ANCHOR:2", "PARTY"),
        };
        var (docxBase64, errorCode, _, _) =
            SidecarEngine.ExecuteTrackedReplace(docx, ops, "CSM");

        Assert.Null(errorCode);
        Assert.NotNull(docxBase64);

        // Verify ZIP structure
        var raw = Convert.FromBase64String(docxBase64!);
        using var zip = new ZipArchive(new MemoryStream(raw), ZipArchiveMode.Read);

        var entry = zip.GetEntry("word/document.xml");
        Assert.NotNull(entry);

        // Verify document.xml is valid XML
        using var reader = new StreamReader(entry!.Open());
        var xmlText = reader.ReadToEnd();
        var doc = XDocument.Parse(xmlText); // throws if invalid
        Assert.NotNull(doc.Root);
    }

    // ------------------------------------------------------------------
    // 11. tracked_replace_covers_headers_and_footers
    // ------------------------------------------------------------------

    [Fact]
    public void tracked_replace_covers_headers_and_footers()
    {
        var docx = MinimalDocxWithHeaderAndFooter(
            "Treść główna bez danych.",
            "Nagłówek: Jan Kowalski",
            "Stopka: Jan Kowalski");
        var ops = new List<ParsedOperation>
        {
            new ParsedOperation("Jan Kowalski", "[[CSM_PERSON_1]]", "CSM_ANCHOR:HF", "PERSON"),
        };

        var (docxBase64, errorCode, _, revisionCount) =
            SidecarEngine.ExecuteTrackedReplace(docx, ops, "CSM");

        Assert.Null(errorCode);
        Assert.NotNull(docxBase64);
        Assert.True(revisionCount >= 2, "Expected replacements in header and footer.");

        var headerXml = GetZipEntryText(docxBase64!, "word/header1.xml");
        var footerXml = GetZipEntryText(docxBase64!, "word/footer1.xml");
        Assert.Contains("w:ins", headerXml);
        Assert.Contains("w:del", headerXml);
        Assert.Contains("w:ins", footerXml);
        Assert.Contains("w:del", footerXml);
    }

}
