using System.Text.Json.Serialization;

namespace CSM.RevisionSidecar;

/// <summary>Incoming stdin JSON request from the Python backend.</summary>
internal sealed record SidecarRequest(
    [property: JsonPropertyName("protocol_version")] string? ProtocolVersion,
    [property: JsonPropertyName("action")]           string? Action,
    [property: JsonPropertyName("docx_base64")]      string? DocxBase64,
    [property: JsonPropertyName("revised_docx_base64")] string? RevisedDocxBase64,
    [property: JsonPropertyName("operations")]       List<Dictionary<string, System.Text.Json.JsonElement>>? Operations,
    [property: JsonPropertyName("author")]           string? Author,
    [property: JsonPropertyName("map_id")]           string? MapId
);

/// <summary>Outgoing stdout JSON response to the Python backend.</summary>
internal sealed record SidecarResponse(
    [property: JsonPropertyName("ok")]               bool Ok,
    [property: JsonPropertyName("protocol_version")] string ProtocolVersion,
    [property: JsonPropertyName("action")]           string Action,
    [property: JsonPropertyName("status")]           string? Status               = null,
    [property: JsonPropertyName("engine")]           string? Engine               = null,
    [property: JsonPropertyName("message")]          string? Message              = null,
    [property: JsonPropertyName("error_code")]       string? ErrorCode            = null,
    [property: JsonPropertyName("error")]            string? Error                = null,
    [property: JsonPropertyName("docx_base64")]      string? DocxBase64           = null,
    [property: JsonPropertyName("supported_actions")] IReadOnlyList<string>? SupportedActions = null,
    [property: JsonPropertyName("capabilities")]     IReadOnlyDictionary<string, bool>? Capabilities = null,
    [property: JsonPropertyName("metadata")]         IReadOnlyDictionary<string, object?>? Metadata = null,
    [property: JsonPropertyName("input")]            IReadOnlyDictionary<string, object?>? Input = null
);

/// <summary>Parsed and validated single replacement operation.</summary>
internal sealed record ParsedOperation(
    string Pattern,
    string Replacement,
    string AnchorId,
    string EntityType
);

/// <summary>Internal validation result.</summary>
internal sealed record ValidationResult(bool Valid, string? ErrorCode, string? Message);
