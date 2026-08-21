from engine_types import Finding
import bielik_detector
import redactor
from bielik_detector import collect_bielik_findings, parse_bielik_response


def test_bielik_detector_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CSMW_ENABLE_BIELIK", raising=False)
    assert collect_bielik_findings("Anna Lis i kod Akwedukt-R24.") == []


def test_bielik_response_parser_accepts_json_array_in_fence():
    raw = '```json\n[{"text": "Akwedukt-R24", "category": "OTHER"}]\n```'
    assert parse_bielik_response(raw) == [{"text": "Akwedukt-R24", "category": "OTHER"}]


def test_bielik_detector_accepts_only_exact_local_spans(monkeypatch):
    monkeypatch.setenv("CSMW_ENABLE_BIELIK", "1")
    monkeypatch.setenv("CSMW_BIELIK_CHUNK_CHARS", "2000")
    text = "Nazwa kodowa Akwedukt-R24 jest poufna. Akwedukt-R24 wraca w zalaczniku."

    def fake_complete(_chunk):
        return (
            '[{"text":"Akwedukt-R24","category":"OTHER"},'
            '{"text":"Nie ma mnie w tekscie","category":"OTHER"}]'
        )

    monkeypatch.setattr(bielik_detector, "_complete_chunk", fake_complete)
    findings = collect_bielik_findings(text)

    assert all(f.value == "Akwedukt-R24" for f in findings)
    assert [(f.start, f.end) for f in findings] == [(13, 25), (39, 51)]
    assert all(f.category == "BIELIK_PII" for f in findings)


def test_bielik_findings_do_not_flow_into_standard_masking(monkeypatch):
    def fail_if_called(_text):
        raise AssertionError("standard masking must not call Bielik")

    monkeypatch.setattr(redactor, "collect_bielik_findings", fail_if_called)

    masked, _replacements = redactor.make_replacements("Neutralny tekst bez danych.")

    assert masked == "Neutralny tekst bez danych."


def test_bielik_findings_are_available_for_deep_review_only(monkeypatch):
    text = "Sekret techniczny sk-test-123456 powinien zostać sprawdzony."
    start = text.index("sk-test-123456")

    monkeypatch.setattr(
        redactor,
        "collect_bielik_findings",
        lambda _text: [Finding("SECRET", "sk-test-123456", start, start + len("sk-test-123456"))],
    )

    findings = redactor.collect_bielik_deep_review_findings(text, [])

    assert [(f.category, f.value) for f in findings] == [("SECRET", "sk-test-123456")]
