from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")


def test_v4_actions_are_contextual_by_document_kind() -> None:
    assert "function inferFilenameKind" in JS
    assert '"anon"' in JS and '"restored"' in JS
    assert "function applyV4ActionAvailability" in JS
    assert 'const prepareDisabled = kind === "anon"' in JS
    assert 'const fallback = canUseLastSavedAnonFallback(ctx)' in JS
    assert 'const restoreDisabled = kind === "restored" || (kind !== "anon" && !fallback.ok)' in JS
    assert 'setButtonDisabled("btnV4Prepare", prepareDisabled' in JS
    assert 'setButtonDisabled("btnV4Restore", restoreDisabled' in JS
    assert 'setStepDisabled("step2", prepareDisabled)' in JS
    assert 'setStepDisabled("step4", restoreDisabled)' in JS
    assert ".step.disabled" in HTML
    assert 'bindClickableStep("step2", v4PrepareDocxCopy)' not in JS
    assert 'Kroki pracy z dokumentem' not in HTML


def test_v4_prepare_and_restore_validate_document_kind_before_api_call() -> None:
    prepare = JS[JS.index("async function v4PrepareDocxCopy"):JS.index("async function v4RestoreDocxCopy")]
    restore = JS[JS.index("async function v4RestoreDocxCopy"):JS.index("async function v4RestoreManualDocxCopy")]
    assert 'requireDocumentKindForV4("original", "prepare")' in prepare
    assert 'requireDocumentKindForV4("anon", "restore")' not in restore
    prepare_api_idx = prepare.find('apiPostHeavy("/v4/current/prepare"')
    if prepare_api_idx < 0:
        prepare_api_idx = prepare.index('apiPost("/v4/current/prepare"')
    assert prepare.index('requireDocumentKindForV4("original", "prepare")') < prepare_api_idx
    assert 'restoreFromLastSavedAnonPath' in restore
    assert 'apiPostHeavy("/v4/session/restore-last"' in JS or 'apiPost("/v4/session/restore-last"' in JS


def test_v4_success_messages_are_simple_and_green_for_prepare() -> None:
    assert "function buildPrepareSuccessMessage" in JS
    assert 'setNotice("good", buildPrepareSuccessMessage(data))' in JS
    assert "Kontrola roundtrip" in JS  # kept only in technical status, not primary notice
    prepare_notice_pos = JS.index('setNotice("good", buildPrepareSuccessMessage(data))')
    status_pos = JS.index('setStatus(`v1.6 prepare zakończony.')
    assert prepare_notice_pos < status_pos


def test_frontend_retries_backend_base_between_127_and_localhost() -> None:
    assert "API_BASE_CANDIDATES" in JS
    assert '"http://127.0.0.1:8787"' in JS
    assert '"http://localhost:8787"' in JS
    assert "fetchFromAnyApiBase" in JS
    assert "rememberApiBase(base)" in JS
    assert "Uruchom CSM → START" in JS


def test_operations_force_fresh_backend_check_not_stale_server_ok_flag() -> None:
    """Word can keep the task pane alive while CSM is restarted.

    A stale in-memory serverOk=true must not let restore/prepare proceed without
    a fresh /health + /auth_check, otherwise the user sees Failed to fetch after
    pressing START in the desktop launcher.
    """
    ensure = JS[JS.index("async function ensureServerReadyForOperation"):JS.index("async function loadRuntimeTokenFromStaticFile")]
    assert "serverOk = false" in ensure
    assert "return await checkServer()" in ensure
    assert "if (serverOk) return true" not in ensure


def test_taskpane_closes_after_server_side_document_close() -> None:
    """When CSM closes the source/anon Word document via COM, the stale taskpane
    should close too instead of staying visible and showing connection errors.
    """
    assert "function closeCsmTaskpane" in JS
    assert "Office.context && Office.context.ui" in JS
    assert "closeContainer" in JS
    assert "function closeCsmTaskpaneSoon" in JS

    prepare = JS[JS.index("async function v4PrepareDocxCopy"):JS.index("async function preRestoreRevisionAwareRangePass")]
    restore = JS[JS.index("async function v4RestoreDocxCopy"):JS.index("async function v4RestoreManualDocxCopy")]
    manual_restore = JS[JS.index("async function v4RestoreManualDocxCopy"):JS.index("async function mainAction")]

    assert 'closeCsmTaskpaneSoon("zamknięcie oryginału po prepare"' in prepare
    assert 'closeCsmTaskpaneSoon("zamknięcie pliku anon po restore"' in restore
    assert 'closeCsmTaskpaneSoon("zamknięcie pliku anon po ręcznym restore"' in manual_restore
