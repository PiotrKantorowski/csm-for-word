// CSM.RevisionSidecar — stdin/stdout JSON sidecar for OOXML revision operations.
// Protocol version: 0.1
// Stdout: single JSON response object only. All logs go to stderr.
//
// Implemented actions (via Clippit/OpenXmlPowerTools):
//   normalize      → RevisionAccepter.AcceptRevisions
//   compare        → WmlComparer.Compare
//   tracked-replace → OpenXmlRegex.Replace(trackRevisions: true, author: ...)
//
// Legacy fallback error codes kept for contract compatibility with earlier iterations:
//   openxml_powertools_engine_not_wired  (returned only when Clippit throws unexpectedly)

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

using CSM.RevisionSidecar;

const string ProtocolVersion = "0.1";
const string EngineLabel     = SidecarEngine.EngineId;

// Actions the sidecar declares — tracked-replace is the primary OOXML action.
string[] supportedActions = ["tracked-replace", "compare", "normalize", "status"];

var jsonOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy        = JsonNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition      = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented               = false,
};

try
{
    using var reader = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8);
    var stdin = await reader.ReadToEndAsync();

    // Empty stdin → respond with ready status (used for health-check pings)
    if (string.IsNullOrWhiteSpace(stdin))
    {
        Write(StatusResponse("ready", allTrue: false,
            "Sidecar protocol harness is reachable. Send a JSON request to execute an action."));
        return 0;
    }

    SidecarRequest? request;
    try
    {
        request = JsonSerializer.Deserialize<SidecarRequest>(stdin, jsonOptions);
    }
    catch (JsonException ex)
    {
        WriteFailure("unknown", "invalid_json", ex.Message);
        return 2;
    }

    if (request is null)
    {
        WriteFailure("unknown", "invalid_json", "Could not deserialize sidecar request.");
        return 2;
    }

    var action = (request.Action ?? "").Trim().ToLowerInvariant();

    if (string.IsNullOrWhiteSpace(action))
    {
        WriteFailure("unknown", "missing_action", "Missing sidecar action.");
        return 2;
    }

    if (!string.Equals(request.ProtocolVersion, ProtocolVersion, StringComparison.Ordinal))
    {
        WriteFailure(action, "protocol_version_mismatch",
            $"Expected protocol_version {ProtocolVersion}, got {request.ProtocolVersion}.");
        return 2;
    }

    if (!supportedActions.Contains(action))
    {
        WriteFailure(action, "unsupported_action", $"Unsupported sidecar action: {action}.");
        return 2;
    }

    // ------------------------------------------------------------------
    // status
    // ------------------------------------------------------------------
    if (action == "status")
    {
        Write(StatusResponse("ready", allTrue: true));
        return 0;
    }

    // ------------------------------------------------------------------
    // Validate DOCX inputs before calling engine
    // ------------------------------------------------------------------
    var validation = SidecarEngine.ValidateDocxInputs(request, action);
    if (!validation.Valid)
    {
        WriteFailure(action, validation.ErrorCode ?? "invalid_docx",
            validation.Message ?? "Invalid DOCX payload.");
        return 2;
    }

    // ------------------------------------------------------------------
    // Dispatch to engine
    // ------------------------------------------------------------------
    if (action == "normalize")
    {
        var docxBytes = SidecarEngine.DecodeDocx(request.DocxBase64!);
        var (docxBase64, errorCode, errorMessage) = SidecarEngine.ExecuteNormalize(docxBytes);
        if (errorCode is not null)
        {
            // Keep legacy error code in comments for contract compat — openxml_powertools_engine_not_wired
            WriteFailure(action, errorCode, errorMessage ?? "normalize failed.");
            return 1;
        }
        Write(SuccessResponse(action, docxBase64!, new Dictionary<string, object?>
        {
            ["engine"] = SidecarEngine.ClippitEngine,
        }));
        return 0;
    }

    if (action == "compare")
    {
        var originalBytes = SidecarEngine.DecodeDocx(request.DocxBase64!);
        var revisedBytes  = SidecarEngine.DecodeDocx(request.RevisedDocxBase64!);
        var author = string.IsNullOrWhiteSpace(request.Author) ? "CSM" : request.Author!;

        var (docxBase64, errorCode, errorMessage) = SidecarEngine.ExecuteCompare(originalBytes, revisedBytes, author);
        if (errorCode is not null)
        {
            WriteFailure(action, errorCode, errorMessage ?? "compare failed.");
            return 1;
        }
        Write(SuccessResponse(action, docxBase64!, new Dictionary<string, object?>
        {
            ["engine"] = SidecarEngine.ClippitEngine,
            ["author"] = author,
        }));
        return 0;
    }

    if (action == "tracked-replace")
    {
        var docxBytes  = SidecarEngine.DecodeDocx(request.DocxBase64!);
        var operations = SidecarEngine.ParseOperations(request.Operations);
        var author     = string.IsNullOrWhiteSpace(request.Author) ? "CSM" : request.Author!;

        var (docxBase64, errorCode, errorMessage, revisionCount) =
            SidecarEngine.ExecuteTrackedReplace(docxBytes, operations, author);

        if (errorCode is not null)
        {
            WriteFailure(action, errorCode, errorMessage ?? "tracked-replace failed.");
            return 1;
        }
        Write(SuccessResponse(action, docxBase64!, new Dictionary<string, object?>
        {
            ["engine"]         = SidecarEngine.ClippitEngine,
            ["revision_count"] = (object?)revisionCount,
            ["author"]         = author,
        }));
        return 0;
    }

    // Should never reach here after the supported-actions guard above.
    WriteFailure(action, "unsupported_action", $"Action {action} fell through dispatch.");
    return 2;
}
catch (JsonException ex)
{
    WriteFailure("unknown", "invalid_json", ex.Message);
    return 2;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"[CSM.RevisionSidecar] unhandled: {ex}");
    WriteFailure("unknown", "unhandled_error", ex.Message);
    return 1;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

void Write(SidecarResponse response)
{
    Console.OutputEncoding = Encoding.UTF8;
    Console.Write(JsonSerializer.Serialize(response, jsonOptions));
}

void WriteFailure(string action, string errorCode, string message)
{
    Write(new SidecarResponse(
        Ok:              false,
        ProtocolVersion: ProtocolVersion,
        Action:          action,
        Status:          "error",
        Engine:          EngineLabel,
        ErrorCode:       errorCode,
        Error:           message
    ));
}

SidecarResponse SuccessResponse(string action, string docxBase64, Dictionary<string, object?> metadata)
{
    return new SidecarResponse(
        Ok:              true,
        ProtocolVersion: ProtocolVersion,
        Action:          action,
        Status:          "completed",
        Engine:          EngineLabel,
        DocxBase64:      docxBase64,
        Metadata:        metadata
    );
}

SidecarResponse StatusResponse(string status, bool allTrue, string? message = null)
{
    return new SidecarResponse(
        Ok:              true,
        ProtocolVersion: ProtocolVersion,
        Action:          "status",
        Status:          status,
        Engine:          EngineLabel,
        Message:         message,
        SupportedActions: supportedActions,
        Capabilities: new Dictionary<string, bool>
        {
            ["normalize"]       = allTrue,
            ["compare"]         = allTrue,
            ["tracked-replace"] = allTrue,
        }
    );
}

// SHA-256 helper kept for potential audit/debug use
static string Sha256Hex(string? value)
{
    if (string.IsNullOrEmpty(value)) return string.Empty;
    return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
}
