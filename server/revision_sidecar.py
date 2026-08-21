from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List
import base64
import io
import json
import os
import shlex
import shutil
import subprocess
import zipfile

SIDECAR_PROTOCOL_VERSION = "0.1"
SIDECAR_ENV_CMD = "CSM_REVISION_SIDECAR_CMD"
SIDECAR_ENV_TIMEOUT = "CSM_REVISION_SIDECAR_TIMEOUT_SECONDS"
SUPPORTED_ACTIONS = {"tracked-replace", "compare", "normalize"}


class RevisionSidecarError(RuntimeError):
    """Base error for the OOXML revision sidecar adapter."""


class RevisionSidecarUnavailable(RevisionSidecarError):
    """Raised when the sidecar is not configured or cannot be executed."""


class RevisionSidecarProtocolError(RevisionSidecarError):
    """Raised when the sidecar returns malformed data."""


@dataclass
class RevisionSidecarStatus:
    available: bool
    configured: bool
    protocol_version: str
    command: str = ""
    executable: str = ""
    reason: str = ""
    mode: str = "subprocess-json"
    reachable: bool = False
    probe_status: str = "not_requested"
    engine: str = ""
    capabilities: Dict[str, bool] | None = None
    supported_actions: List[str] | None = None


@dataclass
class RevisionSidecarRequest:
    action: str
    docx_base64: str = ""
    revised_docx_base64: str = ""
    operations: List[Dict[str, Any]] | None = None
    author: str = "CSM"
    strategy: Dict[str, Any] | None = None
    map_id: str = ""
    created_at: str = ""
    protocol_version: str = SIDECAR_PROTOCOL_VERSION

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["operations"] = list(self.operations or [])
        payload["strategy"] = dict(self.strategy or {})
        payload["created_at"] = self.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return payload


def _hash_text(value: str) -> str:
    return sha256((value or "").encode("utf-8")).hexdigest()


def _sidecar_command() -> str:
    return os.environ.get(SIDECAR_ENV_CMD, "").strip()


def _split_command(command: str) -> List[str]:
    if not command:
        return []
    posix = os.name != "nt"
    tokens = shlex.split(command, posix=posix)
    if not posix:
        # shlex non-POSIX mode preserves surrounding quote characters in tokens.
        # Strip matched surrounding quotes so subprocess receives bare paths.
        tokens = [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'") else t
                  for t in tokens]
    return tokens


def _normalize_bool_capabilities(value: Any) -> Dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, bool] = {}
    for key, flag in value.items():
        if isinstance(key, str):
            normalized[key] = bool(flag)
    return normalized


def _normalize_supported_actions(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if str(item).strip()})


def _probe_sidecar_status(command: str) -> Dict[str, Any]:
    argv = _split_command(command)
    if not argv:
        raise RevisionSidecarUnavailable("Nie wskazano programu pomocniczego do zachowania śledzenia zmian.")
    payload = {"protocol_version": SIDECAR_PROTOCOL_VERSION, "action": "status"}
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=_sidecar_timeout(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RevisionSidecarUnavailable("Nie odnaleziono programu pomocniczego do zachowania śledzenia zmian.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RevisionSidecarError("Przekroczono limit czasu sprawdzania mechanizmu zachowania śledzenia zmian.") from exc
    if proc.returncode != 0:
        raise RevisionSidecarError(f"Sprawdzenie mechanizmu zachowania śledzenia zmian zakończyło się kodem {proc.returncode}.")
    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RevisionSidecarProtocolError("Mechanizm zachowania śledzenia zmian nie zwrócił poprawnej odpowiedzi technicznej.") from exc
    if not isinstance(result, dict):
        raise RevisionSidecarProtocolError("Mechanizm zachowania śledzenia zmian zwrócił odpowiedź techniczną w nieoczekiwanym formacie.")
    if result.get("protocol_version") != SIDECAR_PROTOCOL_VERSION:
        raise RevisionSidecarProtocolError("Niezgodna wersja komunikacji technicznej mechanizmu zachowania śledzenia zmian.")
    if result.get("ok") is False or result.get("success") is False:
        message = result.get("error") or result.get("message") or result.get("status") or "sidecar_reported_failure"
        raise RevisionSidecarError(f"Sidecar reported failure during status probe: {message}")
    return result


def get_sidecar_status(*, probe: bool = False) -> RevisionSidecarStatus:
    command = _sidecar_command()
    if not command:
        return RevisionSidecarStatus(
            available=False,
            configured=False,
            protocol_version=SIDECAR_PROTOCOL_VERSION,
            reason=f"Nie ustawiono zmiennej {SIDECAR_ENV_CMD}; funkcje wykonawcze zwracają tylko plan techniczny i nie modyfikują DOCX.",
        )
    argv = _split_command(command)
    executable = argv[0] if argv else ""
    if not executable:
        return RevisionSidecarStatus(
            available=False,
            configured=True,
            protocol_version=SIDECAR_PROTOCOL_VERSION,
            command=command,
            reason="Konfiguracja programu pomocniczego jest pusta po odczytaniu.",
        )
    resolved = shutil.which(executable) or (executable if Path(executable).exists() else "")
    if not resolved:
        return RevisionSidecarStatus(
            available=False,
            configured=True,
            protocol_version=SIDECAR_PROTOCOL_VERSION,
            command=command,
            executable=executable,
            reason="Nie odnaleziono programu pomocniczego do zachowania śledzenia zmian.",
        )

    base = RevisionSidecarStatus(
        available=True,
        configured=True,
        protocol_version=SIDECAR_PROTOCOL_VERSION,
        command=command,
        executable=resolved,
        reason="Program pomocniczy jest podłączony do lokalnej komunikacji technicznej.",
        probe_status="not_requested",
    )
    if not probe:
        return base

    try:
        response = _probe_sidecar_status(command)
    except RevisionSidecarError as exc:
        base.available = False
        base.reachable = False
        base.probe_status = "failed"
        base.reason = str(exc)
        return base

    base.available = True
    base.reachable = True
    base.probe_status = "ok"
    base.engine = str(response.get("engine") or "")
    base.capabilities = _normalize_bool_capabilities(response.get("capabilities"))
    base.supported_actions = _normalize_supported_actions(response.get("supported_actions"))
    base.reason = response.get("message") or response.get("status") or "Mechanizm zachowania śledzenia zmian odpowiedział prawidłowo."
    return base


def sidecar_status_dict(*, probe: bool = False) -> Dict[str, Any]:
    return asdict(get_sidecar_status(probe=probe))


def build_sidecar_request(
    *,
    action: str,
    docx_base64: str = "",
    revised_docx_base64: str = "",
    operations: List[Dict[str, Any]] | None = None,
    author: str = "CSM",
    strategy: Dict[str, Any] | None = None,
    map_id: str = "",
) -> Dict[str, Any]:
    selected_action = (action or "").strip().lower()
    if selected_action not in SUPPORTED_ACTIONS:
        raise ValueError(f"Unsupported sidecar action: {action}")
    req = RevisionSidecarRequest(
        action=selected_action,
        docx_base64=docx_base64 or "",
        revised_docx_base64=revised_docx_base64 or "",
        operations=list(operations or []),
        author=author or "CSM",
        strategy=dict(strategy or {}),
        map_id=map_id or "",
    )
    payload = req.to_payload()
    payload["input"] = {
        "docx_base64_sha256": _hash_text(docx_base64 or ""),
        "revised_docx_base64_sha256": _hash_text(revised_docx_base64 or "") if revised_docx_base64 else "",
        "docx_base64_length": len(docx_base64 or ""),
        "revised_docx_base64_length": len(revised_docx_base64 or ""),
        "operations_count": len(operations or []),
    }
    return payload


def _sidecar_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get(SIDECAR_ENV_TIMEOUT, "30") or 30))
    except Exception:
        return 30.0



def _validate_result_docx_base64(value: Any, *, action: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RevisionSidecarProtocolError(
            f"Mechanizm zachowania śledzenia zmian zgłosił sukces akcji {action}, ale nie zwrócił pliku DOCX."
        )
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise RevisionSidecarProtocolError(
            f"Mechanizm zachowania śledzenia zmian zwrócił nieprawidłowy plik DOCX dla akcji {action}."
        ) from exc
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            if "word/document.xml" not in set(zf.namelist()):
                raise RevisionSidecarProtocolError(
                    f"Mechanizm zachowania śledzenia zmian zwrócił DOCX bez wymaganej treści dokumentu dla akcji {action}."
                )
    except RevisionSidecarProtocolError:
        raise
    except zipfile.BadZipFile as exc:
        raise RevisionSidecarProtocolError(
            f"Mechanizm zachowania śledzenia zmian zwrócił plik, który nie jest poprawnym DOCX/ZIP dla akcji {action}."
        ) from exc


def _validate_success_result(payload: Dict[str, Any], result: Dict[str, Any]) -> None:
    action = (payload.get("action") or result.get("action") or "").strip().lower()
    if action in SUPPORTED_ACTIONS:
        _validate_result_docx_base64(result.get("docx_base64"), action=action)


def invoke_sidecar(payload: Dict[str, Any]) -> Dict[str, Any]:
    status = get_sidecar_status()
    if not status.available:
        raise RevisionSidecarUnavailable(status.reason)
    argv = _split_command(status.command)
    if not argv:
        raise RevisionSidecarUnavailable("Nie wskazano programu pomocniczego do zachowania śledzenia zmian.")
    try:
        proc = subprocess.run(
            argv,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=_sidecar_timeout(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RevisionSidecarUnavailable("Nie odnaleziono programu pomocniczego do zachowania śledzenia zmian.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RevisionSidecarError("Przekroczono limit czasu wykonania mechanizmu zachowania śledzenia zmian.") from exc
    if proc.returncode != 0:
        raise RevisionSidecarError(f"Mechanizm zachowania śledzenia zmian zakończył pracę kodem {proc.returncode}.")
    try:
        result = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RevisionSidecarProtocolError("Mechanizm zachowania śledzenia zmian nie zwrócił poprawnej odpowiedzi technicznej.") from exc
    if not isinstance(result, dict):
        raise RevisionSidecarProtocolError("Mechanizm zachowania śledzenia zmian zwrócił odpowiedź techniczną w nieoczekiwanym formacie.")
    if result.get("protocol_version") not in {None, SIDECAR_PROTOCOL_VERSION}:
        raise RevisionSidecarProtocolError("Niezgodna wersja komunikacji technicznej mechanizmu zachowania śledzenia zmian.")
    if result.get("ok") is False or result.get("success") is False:
        code = result.get("error_code") or result.get("status") or "sidecar_reported_failure"
        message = result.get("error") or result.get("message") or code
        raise RevisionSidecarError(f"Sidecar reported failure ({code}): {message}")
    _validate_success_result(payload, result)
    return result


__all__ = [
    "SIDECAR_PROTOCOL_VERSION",
    "SIDECAR_ENV_CMD",
    "SUPPORTED_ACTIONS",
    "RevisionSidecarError",
    "RevisionSidecarUnavailable",
    "RevisionSidecarProtocolError",
    "build_sidecar_request",
    "get_sidecar_status",
    "invoke_sidecar",
    "sidecar_status_dict",
]
