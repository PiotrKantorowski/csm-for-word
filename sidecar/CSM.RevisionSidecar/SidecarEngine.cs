using Clippit;
using Clippit.Word;
using DocumentFormat.OpenXml.Packaging;
using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace CSM.RevisionSidecar;

/// <summary>
/// Core engine for OOXML sidecar operations.
/// Uses Clippit (the maintained .NET 6+/8 fork of OpenXmlPowerTools) for:
///   - normalize  → RevisionAccepter.AcceptRevisions
///   - compare    → WmlComparer.Compare
///   - tracked-replace → OpenXmlRegex.Replace(trackRevisions: true)
/// </summary>
internal static class SidecarEngine
{
    internal const string EngineId = "CSM.RevisionSidecar";
    internal const string ClippitEngine = "Clippit/OpenXmlPowerTools";

    // -----------------------------------------------------------------------
    // normalize
    // -----------------------------------------------------------------------

    /// <summary>
    /// Accept all tracked revisions in the document and return the clean DOCX.
    /// </summary>
    internal static (string? DocxBase64, string? ErrorCode, string? ErrorMessage) ExecuteNormalize(
        byte[] docxBytes)
    {
        try
        {
            var source = new WmlDocument("input.docx", docxBytes);
            var result = RevisionAccepter.AcceptRevisions(source);
            return (Convert.ToBase64String(result.DocumentByteArray), null, null);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[CSM.RevisionSidecar] normalize error: {ex}");
            return (null, "normalize_failed", ex.Message);
        }
    }

    // -----------------------------------------------------------------------
    // compare
    // -----------------------------------------------------------------------

    /// <summary>
    /// Compare two DOCX documents and return a DOCX with tracked-change markup.
    /// </summary>
    internal static (string? DocxBase64, string? ErrorCode, string? ErrorMessage) ExecuteCompare(
        byte[] originalBytes,
        byte[] revisedBytes,
        string author)
    {
        try
        {
            var source1 = new WmlDocument("original.docx", originalBytes);
            var source2 = new WmlDocument("revised.docx", revisedBytes);
            var settings = new WmlComparerSettings
            {
                AuthorForRevisions = string.IsNullOrWhiteSpace(author) ? "CSM" : author,
            };
            var result = WmlComparer.Compare(source1, source2, settings);
            return (Convert.ToBase64String(result.DocumentByteArray), null, null);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[CSM.RevisionSidecar] compare error: {ex}");
            return (null, "compare_failed", ex.Message);
        }
    }

    // -----------------------------------------------------------------------
    // tracked-replace
    // -----------------------------------------------------------------------

    /// <summary>
    /// Apply literal-text replacements as tracked changes using OpenXmlRegex.Replace.
    /// Returns (docxBase64, errorCode, errorMessage, revisionCount).
    /// </summary>
    internal static (string? DocxBase64, string? ErrorCode, string? ErrorMessage, int RevisionCount) ExecuteTrackedReplace(
        byte[] docxBytes,
        IReadOnlyList<ParsedOperation> operations,
        string author)
    {
        if (operations.Count == 0)
            return (null, "missing_operations", "tracked-replace requires at least one operation.", 0);

        try
        {
            var source = new WmlDocument("input.docx", docxBytes);
            int revisionCount = 0;

            using var memDoc = new OpenXmlMemoryStreamDocument(source);
            using (var wDoc = memDoc.GetWordprocessingDocument())
            {
                var textParts = GetTextBearingParts(wDoc).ToList();

                foreach (var part in textParts)
                {
                    var xDoc = part.GetXDocument();
                    var paragraphs = xDoc.Descendants(W.p).ToList();
                    if (paragraphs.Count == 0)
                        continue;

                    foreach (var op in operations)
                    {
                        if (string.IsNullOrEmpty(op.Pattern))
                            continue;

                        // Always treat Pattern as literal text (not regex from user input).
                        var regex = new Regex(
                            Regex.Escape(op.Pattern),
                            RegexOptions.CultureInvariant);

                        revisionCount += OpenXmlRegex.Replace(
                            paragraphs,
                            regex,
                            op.Replacement,
                            doReplacement: (_, _) => true,
                            trackRevisions: true,
                            author: string.IsNullOrWhiteSpace(author) ? "CSM" : author);
                    }

                    part.PutXDocument();
                }
            }

            var result = memDoc.GetModifiedWmlDocument();
            return (Convert.ToBase64String(result.DocumentByteArray), null, null, revisionCount);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[CSM.RevisionSidecar] tracked-replace error: {ex}");
            return (null, "tracked_replace_failed", ex.Message, 0);
        }
    }

    // -----------------------------------------------------------------------
    // DOCX validation helpers (used by Program.cs dispatch)
    // -----------------------------------------------------------------------

    internal static IEnumerable<OpenXmlPart> GetTextBearingParts(WordprocessingDocument wDoc)
    {
        var mainPart = wDoc.MainDocumentPart;
        if (mainPart is null)
            yield break;

        yield return mainPart;

        foreach (var part in mainPart.HeaderParts)
            yield return part;

        foreach (var part in mainPart.FooterParts)
            yield return part;

        if (mainPart.FootnotesPart is not null)
            yield return mainPart.FootnotesPart;

        if (mainPart.EndnotesPart is not null)
            yield return mainPart.EndnotesPart;

        if (mainPart.WordprocessingCommentsPart is not null)
            yield return mainPart.WordprocessingCommentsPart;
    }

    internal static ValidationResult ValidateDocxInputs(SidecarRequest request, string action)
    {
        var first = ValidateDocxBase64(request.DocxBase64, "docx_base64");
        if (!first.Valid)
            return first;

        if (action == "compare")
        {
            var second = ValidateDocxBase64(request.RevisedDocxBase64, "revised_docx_base64");
            if (!second.Valid)
                return second;
        }

        if (action == "tracked-replace" && (request.Operations is null || request.Operations.Count == 0))
            return new ValidationResult(false, "missing_operations",
                "tracked-replace requires at least one operation.");

        return new ValidationResult(true, null, null);
    }

    internal static ValidationResult ValidateDocxBase64(string? value, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(value))
            return new ValidationResult(false, "missing_" + fieldName, $"Missing {fieldName}.");

        byte[] raw;
        try
        {
            raw = Convert.FromBase64String(value);
        }
        catch (FormatException)
        {
            return new ValidationResult(false, "invalid_" + fieldName,
                $"{fieldName} is not valid base64.");
        }

        try
        {
            using var ms = new MemoryStream(raw);
            using var archive = new ZipArchive(ms, ZipArchiveMode.Read, leaveOpen: false);
            if (archive.GetEntry("word/document.xml") is null)
                return new ValidationResult(false, "missing_document_xml",
                    $"{fieldName} is missing word/document.xml.");
        }
        catch (InvalidDataException)
        {
            return new ValidationResult(false, "invalid_docx_zip",
                $"{fieldName} is not a valid DOCX/ZIP package.");
        }

        return new ValidationResult(true, null, null);
    }

    // -----------------------------------------------------------------------
    // Operation parsing
    // -----------------------------------------------------------------------

    /// <summary>
    /// Parse raw operation dictionaries from the JSON request.
    /// Accepts both "pattern"/"replacement" (task spec) and
    /// "original_text"/"replacement_text" (Python engine format).
    /// </summary>
    internal static IReadOnlyList<ParsedOperation> ParseOperations(
        IEnumerable<Dictionary<string, JsonElement>>? rawOps)
    {
        var result = new List<ParsedOperation>();
        if (rawOps is null)
            return result;

        foreach (var op in rawOps)
        {
            string pattern = ReadString(op, "pattern")
                ?? ReadString(op, "original_text")
                ?? "";

            if (string.IsNullOrEmpty(pattern))
                continue;

            string replacement = ReadString(op, "replacement")
                ?? ReadString(op, "replacement_text")
                ?? "";

            string anchorId    = ReadString(op, "anchor_id")   ?? "";
            string entityType  = ReadString(op, "entity_type") ?? "";

            result.Add(new ParsedOperation(pattern, replacement, anchorId, entityType));
        }

        return result;
    }

    private static string? ReadString(Dictionary<string, JsonElement> dict, string key)
    {
        if (dict.TryGetValue(key, out var el) && el.ValueKind == JsonValueKind.String)
            return el.GetString();
        return null;
    }

    // -----------------------------------------------------------------------
    // DOCX bytes helper
    // -----------------------------------------------------------------------

    internal static byte[] DecodeDocx(string base64) => Convert.FromBase64String(base64);
}
