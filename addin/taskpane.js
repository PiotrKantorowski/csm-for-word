const DEFAULT_LOCAL_API_BASE = "http://127.0.0.1:8787";
function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}
const CONFIGURED_API_BASE = (typeof window !== "undefined") ? normalizeApiBase(window.CSM_API_BASE) : "";
const API_BASE = CONFIGURED_API_BASE || DEFAULT_LOCAL_API_BASE;
const configuredApiCandidates = (typeof window !== "undefined" && Array.isArray(window.CSM_API_BASE_CANDIDATES))
  ? window.CSM_API_BASE_CANDIDATES.map(normalizeApiBase).filter(Boolean)
  : [];
const API_BASE_CANDIDATES = Array.from(new Set([
  ...configuredApiCandidates,
  API_BASE,
  DEFAULT_LOCAL_API_BASE,
  "http://localhost:8787",
]));
const APP_VERSION = "1.6";
const MAP_SETTING_KEY = "claudeSafeMode.mapId";
const MODE_SETTING_KEY = "claudeSafeMode.enabled";
const SESSION_SETTING_KEY = "claudeSafeMode.sessionId";
const LAST_RESTORE_SETTING_KEY = "claudeSafeMode.lastRestore";
const LAST_SUMMARY_SETTING_KEY = "claudeSafeMode.lastSummary";
const MODE_KIND_SETTING_KEY = "claudeSafeMode.modeKind";
const DATA_CLEAR_AFTER_RESTORE_SETTING_KEY = "claudeSafeMode.dataClearAfterRestore";
const V4_LAST_MAP_SETTING_KEY = "CSM_V4_LAST_MAP_ID";
const V4_LAST_ANON_PATH_KEY = "CSM_V4_LAST_ANON_PATH";
const V4_LAST_SESSION_ID_KEY = "CSM_V4_LAST_SESSION_ID";
const V4_LAST_SOURCE_FILENAME_KEY = "CSM_V4_LAST_SOURCE_FILENAME";
const V4_LAST_SOURCE_PATH_KEY = "CSM_V4_LAST_SOURCE_PATH";
const V4_LAST_PREPARED_AT_KEY = "CSM_V4_LAST_PREPARED_AT";
const MANUAL_CONTROLS_STORAGE_KEY = "CSM_MANUAL_CONTROLS_V1";
const DOCUMENT_PROFILE_SETTING_KEY = "CSM_DOCUMENT_PROFILE";
const DOCUMENT_PROFILE_STORAGE_KEY = "CSM_DOCUMENT_PROFILE_LAST";
const UNCERTAIN_REVIEW_STORAGE_KEY = "CSM_UNCERTAIN_REVIEW_DECISIONS_V1";
const OFFICE_AUTO_SHOW_TASKPANE_KEY = "Office.AutoShowTaskpaneWithDocument";
const SUPPORT_EMAIL = "csm@kancelariakantorowski.pl";
const SUPPORT_HINT = `Jeśli coś nie działa, napisz na ${SUPPORT_EMAIL} — pomoże nam to rozwiązać Twój problem.`;

let restoreInProgress = false;
let autoRestoreAttempted = false;
let serverOk = false;
let GBielikConfirmedOn = false;  // sticky: once ON never flips to OFF on transient failures
let busy = false;
let lastHealth = null;
let lastSummary = null;
let lastRevisionSidecarStatus = null;
let lastMappingPreview = null;
let lastUncertainReviewCandidates = [];
let trackedChangesConsentPending = false;
let dataClearAfterRestore = false;
let installPaths = { maps: "", backups: "" };
let activeApiBase = API_BASE;
let lastDocumentContext = { kind: "unknown", filename: "" };

const BUSY_BUTTON_IDS = ["btnV4Prepare", "btnV4Restore", "btnV4PrepareBielik", "btnV4RestoreManual", "btnMain", "btnRestore", "btnCheck", "btnEmergency", "btnClearAcknowledged", "btnTechStatus", "btnRefreshStatus", "btnRevisionSidecarStatus", "btnPreviewMap", "btnCopyMappings", "btnDownloadMappings", "btnSaveManualControls", "btnLoadManualControls", "btnExportManualControls", "btnImportManualControls", "btnApplyManualControls", "btnClearManualControls", "btnReviewUncertain", "btnUncertainApply", "btnUncertainSkip", "btnUncertainSelectAll"];

const CATEGORY_LABELS = {
  PERSON: "osoby", PERSON_NLP: "osoby (NLP)", PERSON_ALIAS: "odmiany osób", EMAIL: "e-maile", PHONE: "telefony",
  COMPANY: "spółki / organizacje", COMPANY_NLP: "organizacje (NLP)", COMPANY_ALIAS: "aliasy spółek", COMPANY_CODE: "skróty nazw",
  CONTRACTOR: "kontrahenci", CONTRACTOR_ALIAS: "aliasy kontrahentów", ALIAS: "aliasy stron",
  DOMAIN: "domeny", DOMAIN_ALIAS: "aliasy domen", URL: "adresy URL", PROJECT: "projekty / systemy",
  PESEL: "PESEL", NIP: "NIP", REGON: "REGON", KRS: "KRS", IBAN: "rachunki / IBAN",
  IDCARD_PL: "dowody osobiste", PASSPORT_PL: "paszporty", ADDRESS: "adresy", ADDRESS_NLP: "lokalizacje (NLP)", POSTCODE_PL: "kody pocztowe",
  COURT: "sądy", SYGNATURA: "sygnatury", REPERTORIUM: "repertoria notarialne", DECYZJA_ADM: "decyzje administracyjne", KW: "księgi wieczyste", SECRET: "sekrety / klucze",
  BIELIK_PII: "wykryte przez AI (Bielik)", ACCOUNT_ID: "identyfikatory kont", LOGIN: "loginy", PROJECT: "projekty / systemy"
};

function $(id) { return document.getElementById(id); }

// ─── Module accessors ────────────────────────────────────────────────────────

function stateMachine() {
  return window.CSMStateMachine || null;
}

function wordBridge() {
  return window.CSMWordBridge || null;
}

function revisionBridge() {
  return window.CSMRevisionBridge || null;
}

function requireRevisionBridge() {
  const bridge = revisionBridge();
  if (!bridge) throw new Error("revision_bridge.js nie jest załadowany. Zamknij i otwórz ponownie panel dodatku w Wordzie.");
  return bridge;
}

function requireBridge() {
  const bridge = wordBridge();
  if (!bridge) throw new Error("word-bridge.js nie jest załadowany. Zamknij i otwórz ponownie panel dodatku w Wordzie.");
  return bridge;
}

// ─── State machine wrappers ──────────────────────────────────────────────────

function readSafeModeSnapshot() {
  const sm = stateMachine();
  if (sm && typeof sm.readStateSnapshot === "function") {
    try { return sm.readStateSnapshot(); } catch (_) {}
  }
  // Legacy read-only fallback for documents opened with a pre-v3 panel.
  const enabled = getSetting(MODE_SETTING_KEY) === "true";
  return {
    state: enabled ? "MASKED" : "CLEAN",
    mapId: getSetting(MAP_SETTING_KEY) || "",
    sessionId: getSetting(SESSION_SETTING_KEY) || "",
    lastTransition: "",
    backupPath: "",
    isClean: !enabled,
    isMasked: enabled,
    isBusy: false,
    legacyFallback: true
  };
}

function isSafeModeActive() {
  const snapshot = readSafeModeSnapshot();
  return snapshot.state === "MASKED" || snapshot.state === "MASKING" || snapshot.state === "RESTORING";
}

function activeMapId() {
  return readSafeModeSnapshot().mapId || "";
}

function activeSessionId() {
  return readSafeModeSnapshot().sessionId || "";
}

async function ensureDocumentStateReady() {
  const sm = stateMachine();
  if (sm && typeof sm.ensureCleanState === "function") {
    return await sm.ensureCleanState();
  }
  return readSafeModeSnapshot();
}

async function markDocumentMasking(metadata = {}) {
  const sm = stateMachine();
  if (!sm || typeof sm.markMasking !== "function") return readSafeModeSnapshot();
  return await sm.markMasking(metadata);
}

async function markDocumentMasked(metadata = {}) {
  const sm = stateMachine();
  if (!sm || typeof sm.markMasked !== "function") return readSafeModeSnapshot();
  return await sm.markMasked(metadata);
}

async function markDocumentRestoring(metadata = {}) {
  const sm = stateMachine();
  if (!sm || typeof sm.markRestoring !== "function") return readSafeModeSnapshot();
  return await sm.markRestoring(Object.assign({ keepExisting: true }, metadata || {}));
}

async function markDocumentRestored(metadata = {}) {
  const sm = stateMachine();
  if (!sm || typeof sm.markRestored !== "function") return readSafeModeSnapshot();
  return await sm.markRestored(metadata);
}

async function markDocumentError(metadata = {}) {
  const sm = stateMachine();
  if (!sm || typeof sm.markError !== "function") return readSafeModeSnapshot();
  try { return await sm.markError(Object.assign({ keepExisting: true }, metadata || {})); } catch (_) { return readSafeModeSnapshot(); }
}

async function markDocumentClean(reason = "clean") {
  const sm = stateMachine();
  if (!sm || typeof sm.markClean !== "function") return readSafeModeSnapshot();
  return await sm.markClean(reason);
}

async function beginDocumentRestore(mapId, reason) {
  const sm = stateMachine();
  if (!sm) return readSafeModeSnapshot();
  let snapshot = readSafeModeSnapshot();
  if (snapshot.state === "CLEAN" || snapshot.state === "RESTORED") {
    await markDocumentMasking({ reason: "restore-bootstrap", sessionId: currentSessionId() });
    await markDocumentMasked({ reason: "restore-bootstrap-map", mapId: mapId || "", sessionId: currentSessionId() });
    snapshot = readSafeModeSnapshot();
  } else if (snapshot.state === "ERROR") {
    await markDocumentMasked({ reason: "restore-from-error", mapId: mapId || snapshot.mapId || "", sessionId: currentSessionId() });
    snapshot = readSafeModeSnapshot();
  }
  if (snapshot.state === "MASKED") {
    return await markDocumentRestoring({ reason: reason || "restore-start", mapId: mapId || snapshot.mapId || "", keepExisting: true });
  }
  return snapshot;
}

async function completeDocumentRestore(reason = "restore-complete") {
  const snapshot = readSafeModeSnapshot();
  if (snapshot.state === "MASKED") {
    await markDocumentRestoring({ reason: "restore-finalize", keepExisting: true });
  }
  const current = readSafeModeSnapshot();
  if (current.state === "RESTORING") {
    return await markDocumentRestored({ reason });
  }
  return current;
}

// ─── UI helpers ──────────────────────────────────────────────────────────────

function reportPanelError(error, context) {
  const message = (error && error.message) ? error.message : String(error || "nieznany błąd");
  const prefix = context ? `${context}: ` : "";
  try {
    const statusEl = document.getElementById("status");
    if (statusEl) statusEl.textContent = `Błąd panelu: ${prefix}${message}`;
    const notices = document.getElementById("notices");
    if (notices) notices.innerHTML = `<div class="notice danger">${escapeHtml(withSupportHint(`Błąd panelu dodatku: ${prefix + message}. Zamknij i otwórz ponownie panel. Jeśli problem wraca, uruchom CSM → STOP, potem START.`))}</div>`;
    const titleEl = document.getElementById("stateTitle");
    const descEl = document.getElementById("stateDesc");
    const dot = document.getElementById("stateDot");
    if (titleEl) titleEl.textContent = "Błąd panelu dodatku";
    if (descEl) descEl.textContent = "Kliknięcie nie zostało obsłużone prawidłowo. Szczegóły są w statusie technicznym.";
    if (dot) dot.className = "dot danger";
  } catch (_) {}
}

window.addEventListener("error", (event) => {
  reportPanelError(event.error || event.message, "JavaScript");
});

window.addEventListener("unhandledrejection", (event) => {
  reportPanelError(event.reason, "Promise");
});

function bindButton(id, handler) {
  const el = $(id);
  if (!el) return false;
  if (el.dataset.csmBound === "1") return true;
  el.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    // Visual "I registered your click" feedback — stays on until the handler resolves.
    el.classList.add("is-pressing");
    try {
      showButtonLoading(el, true);
      console.info(`[CSM] click: ${id}`);
      await handler(event);
      console.info(`[CSM] done : ${id}`);
    } catch (error) {
      console.error(`[CSM] error in ${id}:`, error);
      reportPanelError(error, id);
    } finally {
      if (!busy) showButtonLoading(el, false);
      el.classList.remove("is-pressing");
    }
  });
  el.dataset.csmBound = "1";
  return true;
}

function bindClickableStep(id, handler) {
  const el = $(id);
  if (!el) return false;
  if (el.dataset.csmBound === "1") return true;
  const run = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const relatedButton = id === "step2" ? $("btnV4Prepare") : (id === "step4" ? $("btnV4Restore") : null);
    if (relatedButton && relatedButton.disabled) {
      setNotice("info", relatedButton.title || "Ta operacja nie jest dostępna dla aktualnego dokumentu.");
      return;
    }
    try {
      await handler(event);
    } catch (error) {
      reportPanelError(error, id);
    }
  };
  el.addEventListener("click", run);
  el.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") run(event);
  });
  el.dataset.csmBound = "1";
  return true;
}

function bindButtons() {
  const bindings = [
    bindButton("btnMain", mainAction),
    bindButton("btnRestore", () => disableSafeMode()),
    bindButton("btnCheck", checkServer),
    bindButton("btnEmergency", emergencyRestoreOriginal),
    bindButton("btnClearAcknowledged", acknowledgeDataClearAfterRestore),
    bindButton("btnRefreshStatus", () => refreshDocumentState()),
    bindButton("btnTechStatus", showTechnicalStatus),
    bindButton("btnRevisionSidecarStatus", () => checkRevisionSidecarStatus({ show: true })),
    bindButton("btnV4Prepare", v4PrepareDocxCopy),
    bindButton("btnV4PrepareBielik", () => v4PrepareDocxCopy({ reviewMode: "bielik" })),
    bindButton("btnV4Restore", v4RestoreDocxCopy),
    bindButton("btnV4RestoreManual", v4RestoreManualDocxCopy),
    bindButton("btnCopyAnonReport", copyAnonymizationReport),
    bindButton("btnDownloadAnonReport", downloadAnonymizationReport),
    bindButton("btnQualityCheck", toggleQualityPanel),
    bindButton("btnPreviewMap", previewCurrentMap),
    bindButton("btnCopyMappings", copyMappingPreview),
    bindButton("btnDownloadMappings", downloadMappingPreview),
    bindButton("btnSaveManualControls", saveManualControlsPreset),
    bindButton("btnLoadManualControls", loadManualControlsPreset),
    bindButton("btnExportManualControls", exportManualControlsPreset),
    bindButton("btnImportManualControls", importManualControlsPreset),
    bindButton("btnApplyManualControls", remaskWithManualControls),
    bindButton("btnClearManualControls", clearManualControls),
    bindButton("btnPreviewControls", previewManualControlsEffects),
    bindButton("btnSaveRulesClient", () => saveManualRulesToLevel("client")),
    bindButton("btnSaveRulesGlobal", () => saveManualRulesToLevel("global")),
    bindButton("btnShowSavedRules", showSavedManualRules),
    bindButton("btnReviewUncertain", () => openUncertainReviewModal(null, true)),
    bindButton("btnUncertainApply", applySelectedUncertainReviewCandidates),
    bindButton("btnUncertainSkip", skipUncertainReviewModal),
    bindButton("btnUncertainSelectAll", toggleAllUncertainReviewCandidates),
    // The visible step-by-step panel was removed for a simpler UI. The main buttons above keep the same workflow.
    // service panel buttons (launcher integration)
    bindButton("btnSvcStart",    svcStart),
    bindButton("btnSvcStop",     svcStop),
    bindButton("btnSvcRepair",   svcRepair),
    bindButton("btnSvcClean",    svcClean),
    bindButton("btnSvcDiagnose",  svcDiagnose),
    bindButton("btnSvcUninstall", svcUninstall),
  ];
  const profile = $("documentProfile");
  if (profile && !profile.dataset.csmBound) {
    profile.addEventListener("change", () => { persistSelectedDocumentProfile(profile.value, "user-change"); });
    profile.dataset.csmBound = "1";
    setDocumentProfileUi(getSetting(DOCUMENT_PROFILE_SETTING_KEY) || safeLocalStorageGet(DOCUMENT_PROFILE_STORAGE_KEY) || profile.value || "auto");
  }
  const clientField = $("manualRulesClient");
  if (clientField && !clientField.dataset.csmBound) {
    clientField.addEventListener("change", persistManualRulesClientId);
    clientField.dataset.csmBound = "1";
  }
  restoreManualRulesClientId();
  bindManualRuleListActions();
  renderManualRuleLists();
  const ok = bindings.every(Boolean);
  if (!ok) {
    setStatus("Panel załadowany, ale nie wszystkie przyciski zostały znalezione. Odśwież lub dodaj ponownie dodatek w Wordzie.");
  }
  return ok;
}

// ─── API helpers ─────────────────────────────────────────────────────────────

function apiHeaders(extra = {}) {
  const token = (window.CSM_TOKEN || "").trim();
  const headers = Object.assign({ "Content-Type": "application/json" }, extra || {});
  if (token) headers["X-CSM-Token"] = token;
  return headers;
}

function rememberApiBase(base) {
  if (!base) return;
  activeApiBase = base;
  try { window.localStorage && window.localStorage.setItem("CSM_ACTIVE_API_BASE", base); } catch (_) {}
}

function apiBaseCandidates() {
  const values = [];
  try {
    const stored = window.localStorage && window.localStorage.getItem("CSM_ACTIVE_API_BASE");
    if (stored) values.push(stored);
  } catch (_) {}
  values.push(activeApiBase || API_BASE);
  API_BASE_CANDIDATES.forEach((base) => values.push(base));
  return Array.from(new Set(values.filter(Boolean)));
}

function apiBaseLabel() {
  return activeApiBase || API_BASE;
}

async function fetchFromAnyApiBase(path, options = {}, timeoutMs = 5000) {
  const bases = apiBaseCandidates();
  let lastError = null;
  for (const base of bases) {
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    let timer = null;
    try {
      const opts = Object.assign({}, options || {});
      if (controller) {
        opts.signal = controller.signal;
        timer = setTimeout(() => controller.abort(), timeoutMs);
      }
      const res = await fetch(`${base}${path}`, opts);
      if (timer) clearTimeout(timer);
      rememberApiBase(base);
      return res;
    } catch (error) {
      if (timer) clearTimeout(timer);
      lastError = error;
      console.warn(`[CSM] API ${base}${path} nie odpowiedziało`, error);
    }
  }
  throw lastError || new Error("Nie udało się połączyć z lokalnym API CSM.");
}

async function ensureServerReadyForOperation() {
  // Do not trust a stale in-memory flag here. Word can keep a task pane alive
  // while the user restarts CSM in the desktop launcher. In that situation
  // serverOk may still be true even though the backend process on 8787 was
  // stopped and replaced. Re-check /health and /auth_check before every
  // document-changing operation so the user can press CSM → START and then
  // retry the same button without recreating the anonymized copy.
  setStatus("Sprawdzam świeże połączenie z lokalnym silnikiem CSM...");
  serverOk = false;
  return await checkServer();
}

async function loadRuntimeTokenFromStaticFile() {
  try {
    const res = await fetch(`csm-token.js?ts=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return false;
    const js = await res.text();
    const m = js.match(/window\.CSM_TOKEN\s*=\s*['"]([^'"]+)['"]/);
    if (m && m[1]) {
      window.CSM_TOKEN = m[1].trim();
      return true;
    }
  } catch (_) {}
  return false;
}

async function loadRuntimeTokenFromBackend() {
  try {
    const res = await fetchFromAnyApiBase(`/auth/bootstrap?ts=${Date.now()}`, { cache: "no-store" }, 3500);
    if (!res.ok) return false;
    const data = await res.json();
    if (data && data.token) {
      window.CSM_TOKEN = String(data.token).trim();
      console.info(`[CSM] Token API zsynchronizowany z lokalnego backendu (${apiBaseLabel()}).`);
      return Boolean(window.CSM_TOKEN);
    }
  } catch (error) {
    console.warn("[CSM] Nie udało się pobrać tokenu z backendu.", error);
  }
  return false;
}

async function loadRuntimeTokenFresh(options = {}) {
  const backendFirst = Boolean(options.backendFirst);
  if (backendFirst && await loadRuntimeTokenFromBackend()) return true;
  if (await loadRuntimeTokenFromStaticFile()) return true;
  if (await loadRuntimeTokenFromBackend()) return true;
  return Boolean((window.CSM_TOKEN || "").trim());
}

function authErrorMessage() {
  return "Brak autoryzacji lokalnego API. CSM spróbował odświeżyć token automatycznie. Jeśli komunikat wraca, zamknij Worda, użyj CSM → STOP, potem CSM → START i otwórz panel dodatku ponownie.";
}

async function postJson(path, payload) {
  return await fetchFromAnyApiBase(path, {
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify(payload || {})
  }, 15000);
}

// Helper: translate a raw network/fetch error into a user-readable message.
// WebView2 (Word task pane) often reports ECONNREFUSED as an AbortError with
// the unhelpful message "signal is aborted without reason" instead of a clear
// "Failed to fetch".  We normalise all such errors here.
function _csmNetworkErrorMessage(networkError, elapsedMs, timeoutMs) {
  const msg = (networkError && (networkError.message || String(networkError))) || "";
  const isAbort = (networkError && networkError.name === "AbortError") ||
                  msg.toLowerCase().includes("abort") ||
                  msg.toLowerCase().includes("signal");
  if (isAbort && elapsedMs >= (timeoutMs || 120000) - 2000) {
    // Timed-out waiting for the server to finish processing (large document?)
    return `Operacja przekroczyła limit czasu (${Math.round(elapsedMs / 1000)} s). Serwer CSM mógł nie zdążyć przetworzyć dużego dokumentu. Spróbuj ponownie — przy kolejnej próbie serwer może odpowiedzieć szybciej.`;
  }
  if (isAbort) {
    // Short abort = server not running or WebView2 killed the connection
    return `Nie można połączyć się z lokalnym silnikiem CSM (${apiBaseLabel()}). Sprawdź, czy CSM jest uruchomiony: otwórz skrót „CSM – START" na pulpicie lub w menu Start, poczekaj na komunikat „gotowy do pracy" i kliknij przycisk ponownie.`;
  }
  // Generic network error (Failed to fetch, ERR_CONNECTION_REFUSED, etc.)
  return `Brak połączenia z lokalnym silnikiem CSM (${apiBaseLabel()}). Uruchom CSM → START, poczekaj na komunikat „gotowy do pracy", a potem kliknij ten sam przycisk ponownie.`;
}

// Single-shot POST — no retry loop, long timeout (120 s).
// Must be used for all mutating operations (prepare, restore) so that a slow
// server does NOT receive the same request twice. The retry loop in
// fetchFromAnyApiBase is fine for cheap reads/health-checks but causes a
// "two documents opened" bug for operations that call os.startfile() on the
// backend: a 15 s abort triggers a second identical request on the next base
// URL (127.0.0.1 → localhost, same physical server), and both complete.
async function postJsonNoRetry(path, payload, timeoutMs = 120000) {
  const base = activeApiBase || (apiBaseCandidates()[0] || API_BASE);
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  let timer = null;
  try {
    const opts = {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify(payload || {}),
    };
    if (controller) {
      opts.signal = controller.signal;
      timer = setTimeout(() => controller.abort(), timeoutMs);
    }
    const res = await fetch(`${base}${path}`, opts);
    if (timer) clearTimeout(timer);
    rememberApiBase(base);
    return res;
  } catch (error) {
    if (timer) clearTimeout(timer);
    throw error;
  }
}

async function apiPostHeavy(path, payload, timeoutMs = 120000) {
  await loadRuntimeTokenFresh();
  const t0 = Date.now();
  let res;
  try {
    res = await postJsonNoRetry(path, payload, timeoutMs);
    if (res.status === 401) {
      console.warn(`[CSM] apiPostHeavy ${path}: HTTP 401, odświeżam token z backendu i ponawiam żądanie.`);
      if (await loadRuntimeTokenFresh({ backendFirst: true })) {
        res = await postJsonNoRetry(path, payload, timeoutMs);
      }
    }
  } catch (networkError) {
    const elapsed = Date.now() - t0;
    console.error(`[CSM] apiPostHeavy ${path}: network error after ${elapsed}ms`, networkError);
    throw new Error(_csmNetworkErrorMessage(networkError, elapsed, timeoutMs));
  }
  console.info(`[CSM] apiPostHeavy ${path}: HTTP ${res.status} in ${Date.now() - t0}ms`);
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data.detail || "";
    } catch (_) {}
    const err = new Error(res.status === 401 ? authErrorMessage() : `HTTP ${res.status}${detail ? ": " + detail : ""}`);
    err.status = res.status;
    throw err;
  }
  return await res.json();
}

async function getJson(path) {
  return await fetchFromAnyApiBase(path, {
    method: "GET",
    headers: apiHeaders(),
    cache: "no-store"
  }, 10000);
}

async function apiGet(path) {
  await loadRuntimeTokenFresh();
  const t0 = Date.now();
  let res;
  try {
    res = await getJson(path);
    if (res.status === 401) {
      console.warn(`[CSM] apiGet ${path}: HTTP 401, odświeżam token z backendu i ponawiam żądanie.`);
      if (await loadRuntimeTokenFresh({ backendFirst: true })) {
        res = await getJson(path);
      }
    }
  } catch (networkError) {
    const elapsed = Date.now() - t0;
    console.error(`[CSM] apiGet ${path}: network error after ${elapsed}ms`, networkError);
    throw new Error(_csmNetworkErrorMessage(networkError, elapsed, 15000));
  }
  console.info(`[CSM] apiGet ${path}: HTTP ${res.status} in ${Date.now() - t0}ms`);
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data.detail || "";
    } catch (_) {}
    const err = new Error(res.status === 401 ? authErrorMessage() : `HTTP ${res.status}${detail ? ": " + detail : ""}`);
    err.status = res.status;
    throw err;
  }
  return await res.json();
}

async function apiPost(path, payload) {
  await loadRuntimeTokenFresh();
  const t0 = Date.now();
  let res;
  try {
    res = await postJson(path, payload);
    if (res.status === 401) {
      console.warn(`[CSM] apiPost ${path}: HTTP 401, odświeżam token z backendu i ponawiam żądanie.`);
      if (await loadRuntimeTokenFresh({ backendFirst: true })) {
        res = await postJson(path, payload);
      }
    }
  } catch (networkError) {
    const elapsed = Date.now() - t0;
    console.error(`[CSM] apiPost ${path}: network error after ${elapsed}ms`, networkError);
    throw new Error(_csmNetworkErrorMessage(networkError, elapsed, 15000));
  }
  console.info(`[CSM] apiPost ${path}: HTTP ${res.status} in ${Date.now() - t0}ms`);
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data.detail || "";
    } catch (_) {}
    const err = new Error(res.status === 401 ? authErrorMessage() : `HTTP ${res.status}${detail ? ": " + detail : ""}`);
    err.status = res.status;
    throw err;
  }
  return await res.json();
}

async function apiPostService(path, payload, timeoutMs = 6000) {
  await loadRuntimeTokenFresh();
  const t0 = Date.now();
  let res;
  try {
    res = await fetchFromAnyApiBase(path, {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify(payload || {})
    }, timeoutMs);
    if (res.status === 401) {
      console.warn(`[CSM] apiPostService ${path}: HTTP 401, odświeżam token z backendu i ponawiam żądanie.`);
      if (await loadRuntimeTokenFresh({ backendFirst: true })) {
        res = await fetchFromAnyApiBase(path, {
          method: "POST",
          headers: apiHeaders(),
          body: JSON.stringify(payload || {})
        }, timeoutMs);
      }
    }
  } catch (networkError) {
    console.error(`[CSM] apiPostService ${path}: network error after ${Date.now() - t0}ms`, networkError);
    const err = new Error(
      "Nie mam połączenia z lokalnym silnikiem CSM. Z poziomu dodatku Word nie da się uruchomić programu Windows, gdy lokalne API jest całkowicie wyłączone. Uruchom skrót CSM - START z pulpitu lub menu Start, poczekaj kilka sekund i kliknij ponownie."
    );
    err.isConnectionError = true;
    throw err;
  }
  console.info(`[CSM] apiPostService ${path}: HTTP ${res.status} in ${Date.now() - t0}ms`);
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data.detail || "";
    } catch (_) {}
    const err = new Error(res.status === 401 ? authErrorMessage() : `HTTP ${res.status}${detail ? ": " + detail : ""}`);
    err.status = res.status;
    throw err;
  }
  return await res.json();
}

async function getLatestBackupMapId() {
  try {
    const data = await apiPost("/backup_latest", {});
    return data && data.map_id ? data.map_id : "";
  } catch (_) {
    return "";
  }
}

function backupFolderLabel(mapId) {
  if (installPaths.backups) return `${installPaths.backups}\\${mapId}`;
  return `(katalog instalacji)\\backups\\${mapId}`;
}

function mapsDir() {
  return installPaths.maps || "C:\\CSM\\maps";
}

async function backupStatusText(mapId) {
  if (!mapId) return "brak mapy";
  try {
    const data = await apiPost("/backup_latest", { map_id: mapId });
    const m = data.manifest || {};
    const kind = m.has_original_docx ? "pełny plik Word" : (m.has_original_ooxml ? "struktura Worda" : (m.has_original_text ? "tekst" : "metadane"));
    return `kopia awaryjna: ${kind}, folder ${backupFolderLabel(mapId)}`;
  } catch (_) {
    return `kopia awaryjna: niepotwierdzona, mapa ${mapId}`;
  }
}

// ─── UI state ────────────────────────────────────────────────────────────────

function setStatus(message, includeSupport = false) {
  const el = $("status");
  if (el) el.textContent = includeSupport ? withSupportHint(message) : message;
}

function showButtonLoading(buttonOrId, value) {
  const el = typeof buttonOrId === "string" ? $(buttonOrId) : buttonOrId;
  if (!el) return;
  if (!el.dataset.csmOriginalLabel) el.dataset.csmOriginalLabel = el.textContent || "";
  if (value) {
    el.setAttribute("aria-busy", "true");
    el.innerHTML = `<span class="spinner" aria-hidden="true"></span>${escapeHtml(el.dataset.csmOriginalLabel || "Operacja")}`;
  } else {
    el.removeAttribute("aria-busy");
    el.textContent = el.dataset.csmOriginalLabel || el.textContent || "";
  }
}

// ── Progress bar simulation ───────────────────────────────────────────────────
// The backend processes documents synchronously and doesn't stream progress.
// We simulate progress with an exponential decay curve: p = 90*(1-e^(-t/τ)).
// This reaches ~22% at 1s, ~39% at 2s, ~63% at 4s, ~83% at 8s, ~90% at 10s.
// On completion we jump to 100% with a smooth 300ms transition.

let _progressRaf = null;
let _progressStartMs = 0;
const _PROGRESS_TAU = 5000; // ms — tune to typical operation duration

const ETA_MSGS = [
  [0,   ""],
  [5,   "kilka sekund…"],
  [20,  "przetwarzam…"],
  [50,  "prawie gotowe…"],
  [80,  "finalizuję…"],
  [95,  "zaraz…"],
];

function _etaText(pct) {
  let msg = "";
  for (const [threshold, label] of ETA_MSGS) {
    if (pct >= threshold) msg = label;
  }
  return msg;
}

function _setProgressUi(pct, transitioning = false) {
  const bar  = $("progressBar");
  const pctEl = $("progressPct");
  const wrap = $("progressBarWrap");
  const etaEl = $("progressEta");
  if (!bar) return;
  if (transitioning) {
    bar.style.transition = "width 0.3s ease-out";
  } else {
    bar.style.transition = "width 0.18s linear";
  }
  bar.style.width = pct + "%";
  if (wrap) {
    wrap.setAttribute("aria-valuenow", pct);
    // Shift bar color: dark grey → green at 100%
    if (pct >= 100) bar.style.background = "#16a34a";
    else bar.style.background = "#111827";
  }
  if (pctEl) pctEl.textContent = pct + "%";
  if (etaEl) etaEl.textContent = pct < 100 ? _etaText(pct) : "gotowe ✓";
}

function startProgressBar() {
  if (_progressRaf) { cancelAnimationFrame(_progressRaf); _progressRaf = null; }
  _progressStartMs = performance.now();
  _setProgressUi(0);

  function tick() {
    const t = performance.now() - _progressStartMs;
    const pct = Math.round(90 * (1 - Math.exp(-t / _PROGRESS_TAU)));
    _setProgressUi(Math.min(pct, 90));
    if (pct < 90) {
      _progressRaf = requestAnimationFrame(tick);
    }
  }
  _progressRaf = requestAnimationFrame(tick);
}

function finishProgressBar() {
  if (_progressRaf) { cancelAnimationFrame(_progressRaf); _progressRaf = null; }
  _setProgressUi(100, true);
  // Reset bar after the card hides so it's fresh next time
  setTimeout(() => { _setProgressUi(0); }, 600);
}

function setBusy(value, message, activeButtonId = "") {
  busy = value;
  BUSY_BUTTON_IDS.forEach(id => {
    const el = $(id);
    if (!el) return;
    el.disabled = value;
    showButtonLoading(el, Boolean(value && activeButtonId && id === activeButtonId));
  });
  const progressCard = $("progressCard");
  const progressTitle = $("progressTitle");
  const progressText = $("progressText");
  if (progressCard) {
    if (value) progressCard.classList.remove("hidden");
    else progressCard.classList.add("hidden");
  }
  if (progressTitle) progressTitle.textContent = value ? "Operacja w toku…" : "";
  if (progressText) progressText.textContent = value
    ? (message || "Poczekaj chwilę. Word i lokalny silnik CSM przetwarzają dokument.")
    : "";
  // Progress bar animation
  if (value) startProgressBar();
  else finishProgressBar();
  if (!value) applyV4ActionAvailability(lastDocumentContext);
  // Pulsing yellow dot while the operation is running, so the user sees the
  // panel is alive even when the body of a long step doesn't update the UI.
  if (value && message) setState("busy", `<span class="spinner"></span>${message}`, "Nie zamykaj Worda w trakcie operacji.", true);
}

function setState(kind, title, desc, html = false) {
  const dot = $("stateDot");
  const titleEl = $("stateTitle");
  const descEl = $("stateDesc");
  if (dot) dot.className = `dot ${kind || ""}`;
  if (titleEl) { html ? (titleEl.innerHTML = title) : (titleEl.textContent = title); }
  if (descEl) descEl.textContent = desc || "";
}

function withSupportHint(typeOrText, maybeText) {
  const type = (maybeText === undefined) ? "danger" : typeOrText;
  const text = (maybeText === undefined) ? typeOrText : maybeText;
  if (!text) return text;
  if (type !== "danger") return text;
  if (String(text).includes(SUPPORT_EMAIL)) return text;
  return `${text}

${SUPPORT_HINT}`;
}

function setNotice(type, text) {
  const el = $("notices");
  if (!el) return;
  const finalText = withSupportHint(type, text);
  el.innerHTML = finalText ? `<div class="notice ${type}">${escapeHtml(finalText)}</div>` : "";
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c] || c));
}

function setVisible(id, visible) {
  const el = $(id);
  if (!el) return;
  visible ? el.classList.remove("hidden") : el.classList.add("hidden");
}

function setTrackingConsentControls(_visible) {
  trackedChangesConsentPending = false;
}

function setClearDataAcknowledgementControl(visible) {
  setVisible("btnClearAcknowledged", visible);
}

function isDataClearAfterRestore() {
  return Boolean(dataClearAfterRestore || getSetting(DATA_CLEAR_AFTER_RESTORE_SETTING_KEY) === "true");
}

async function setDataClearAfterRestore(value) {
  dataClearAfterRestore = Boolean(value);
  try { await saveSetting(DATA_CLEAR_AFTER_RESTORE_SETTING_KEY, value ? "true" : "false"); } catch (_) {}
}

function restoredDocumentClearWarningText() {
  return "Dane przywrócone. Dokument jest w wersji jawnej.\n" +
    "Jeśli chcesz kontynuować pracę z Claude, kliknij „Przygotuj dla Claude (tryb bezpieczny)”.\n" +
    "Jeśli praca jest zakończona, możesz zapisać i zamknąć dokument po ręcznej kontroli.";
}

// ─── Session ─────────────────────────────────────────────────────────────────

function makeSessionId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function currentSessionId() {
  let id = sessionStorage.getItem("claudeSafeMode.currentSessionId");
  if (!id) {
    id = makeSessionId();
    sessionStorage.setItem("claudeSafeMode.currentSessionId", id);
  }
  return id;
}

function stepState(activeStep, doneSteps = []) {
  [1,2,3,4].forEach(n => {
    const el = $(`step${n}`);
    if (!el) return;
    el.className = "step";
    if (doneSteps.includes(n)) el.classList.add("done");
    if (activeStep === n) el.classList.add("active");
  });
}

// ─── Settings ────────────────────────────────────────────────────────────────

function saveSetting(key, value) {
  return new Promise((resolve, reject) => {
    Office.context.document.settings.set(key, value);
    Office.context.document.settings.saveAsync((result) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) resolve();
      else reject(result.error);
    });
  });
}

function getSetting(key) {
  return Office.context.document.settings.get(key);
}

// ─── Server check ────────────────────────────────────────────────────────────

function revisionSidecarActionLabel(name) {
  const labels = {
    "tracked-replace": "zachowanie śledzenia zmian przy podmianie danych",
    "compare": "porównanie dwóch wersji dokumentu",
    "normalize": "uporządkowanie zmian w dokumencie",
    "status": "sprawdzenie gotowości modułu",
  };
  return labels[name] || name;
}

function formatRevisionSidecarStatus(data) {
  const status = (data && data.sidecar_status) || {};
  const actions = Array.isArray(data && data.supported_actions)
    ? data.supported_actions.map(revisionSidecarActionLabel).join(", ")
    : "brak danych";
  const availability = status.available ? "gotowy" : "niegotowy";
  const configured = status.configured ? "podłączony" : "niepodłączony";
  const command = status.command_configured ? "tak" : "nie";
  const executable = status.executable_resolved ? "tak" : "nie";
  const reachable = status.reachable ? "tak" : (status.probe_status === "not_requested" ? "nie sprawdzano" : "nie");
  const caps = status.capabilities && typeof status.capabilities === "object"
    ? Object.entries(status.capabilities).map(([name, enabled]) => `${revisionSidecarActionLabel(name)}: ${enabled ? "tak" : "nie"}`).join(", ")
    : "brak danych";
  return `Mechanizm zachowania śledzenia zmian: ${availability} (${configured})
Wersja połączenia lokalnego: ${(data && data.protocol_version) || status.protocol_version || "?"}
Program pomocniczy wskazany w konfiguracji: ${command}
Program pomocniczy odnaleziony: ${executable}
Sprawdzenie uruchomienia: ${status.probe_status === "ok" ? "udane" : (status.probe_status === "failed" ? "nieudane" : "nie sprawdzano")}
Moduł odpowiada: ${reachable}
Obsługiwane funkcje: ${caps}
Zakres działania: ${actions}
Opis: ${status.reason || "brak"}`;
}

async function checkRevisionSidecarStatus(options = {}) {
  const show = options.show !== false;
  try {
    const data = await apiGet("/v2/revision/sidecar/status");
    lastRevisionSidecarStatus = data;
    if (show) setStatus(formatRevisionSidecarStatus(data));
    return data;
  } catch (error) {
    lastRevisionSidecarStatus = { error: error.message || String(error) };
    if (show) setStatus(`Nie udało się sprawdzić mechanizmu zachowania śledzenia zmian. ${error.message || error}`);
    return null;
  }
}

async function checkServer() {
  try {
    await loadRuntimeTokenFresh();
    const res = await fetchFromAnyApiBase("/health", { cache: "no-store" }, 5000);
    const data = await res.json();
    lastHealth = data;
    if (data.status !== "ok") throw new Error("Backend zwrócił nieprawidłowy status.");
    if (data.paths) installPaths = { maps: data.paths.maps || "", backups: data.paths.backups || "" };
    try {
      await apiPost("/auth_check", {});
    } catch (authErr) {
      serverOk = false;
      setState("danger", "Token bezpieczeństwa nie działa", `Uruchom ponownie CSM - START i odśwież dodatek w Wordzie. ${SUPPORT_HINT}`);
      setNotice("danger", authErrorMessage());
      setStatus(`Lokalny pseudonimizator działa, ale token API jest niepoprawny.\n${authErr.message || authErr}`);
      return false;
    }
    serverOk = true;
    setStatus(`Lokalny pseudonimizator: ${data.status}, wersja ${data.version || "?"}. Token API: ok.`);
    setNotice("", "");
    _updateBielikBadge(data.nlp);
    await refreshDocumentState();
    return true;
  } catch (e) {
    serverOk = false;
    setState("danger", "Lokalny silnik nie działa", `Kliknij skrót CSM - START, a potem wróć do Worda. ${SUPPORT_HINT}`);
    setNotice("danger", `Nie mogę połączyć się z lokalnym pseudonimizatorem. ${e.message || e}`);
    setStatus(`Nie mogę połączyć się z lokalnym pseudonimizatorem. Uruchom CSM - START.\n${e.message || e}`);
    return false;
  }
}

// ─── Tracked changes ─────────────────────────────────────────────────────────

async function readTrackedChangesRisk() {
  try {
    const mode = await requireBridge().readTrackingMode();
    const normalized = String(mode || "unknown");
    return { hasTracking: normalized.toLowerCase() !== "off", mode: normalized, unknown: normalized === "unknown" };
  } catch (_) {
    return { hasTracking: true, mode: "unknown", unknown: true };
  }
}

async function readDocxRevisionRisk(originalDocxBase64) {
  if (!originalDocxBase64) return { hasTracking: false, revisionFiles: [] };
  try {
    const report = await apiPost("/docx_revision_report", { docx_base64: originalDocxBase64 });
    return {
      hasTracking: Boolean(report && report.has_tracked_changes),
      revisionFiles: (report && report.revision_files) || [],
      unknown: false
    };
  } catch (e) {
    return { hasTracking: true, revisionFiles: [], unknown: true, error: e && e.message ? e.message : String(e || "nieznany błąd") };
  }
}

function showTrackedChangesPreservationNotice(mode, detail = "") {
  setTrackingConsentControls(false);
  setClearDataAcknowledgementControl(false);
  setState("warn", "Dokument zawiera śledzenie zmian", "Pseudonimizuję bez akceptowania, odrzucania ani spłaszczania zmian.");
  setNotice("info",
    "Dokument zawiera śledzenie zmian albo włączony tryb śledzenia. " +
    "CSM spróbuje spseudonimizować dane z zachowaniem historii redakcyjnej. " +
    "Aplikacja nie zaakceptuje, nie odrzuci ani nie spłaszczy zmian. " +
    "Jeżeli nie będzie można wykonać operacji bezpiecznie, pseudonimizacja zostanie przerwana i dokument nie zostanie oznaczony jako gotowy dla Claude.\n\n" +
    `Aktualny tryb śledzenia zmian Word: ${mode || "unknown"}.` +
    `${detail ? "\n" + detail : ""}`
  );
  setStatus(`Wykryto śledzenie zmian. Uruchamiam tryb zachowania rewizji. Tryb Word: ${mode || "unknown"}.`);
}

async function acknowledgeDataClearAfterRestore() {
  await setDataClearAfterRestore(false);
  setClearDataAcknowledgementControl(false);
  setNotice("info", "Zakończono cykl pracy na jawnej wersji dokumentu. Dokument zawiera prawdziwe dane — nie uruchamiaj Claude bez ponownej pseudonimizacji.");
  await refreshDocumentState(false);
}

async function readTrackingModeLabel() {
  try { return await requireBridge().readTrackingMode(); } catch (_) { return "unknown"; }
}

// ─── Word API wrappers (bridge-only, Iteration 5) ────────────────────────────

async function getBodyOoxml() {
  return await requireBridge().readBodyOoxml();
}

async function replaceBodyWithOoxml(ooxml, options = {}) {
  return await requireBridge().replaceBodyWithOoxml(ooxml, options || {});
}

async function collectOoxmlParts() {
  return await requireBridge().collectOoxmlParts();
}

async function replaceOoxmlParts(parts, options = {}) {
  return await requireBridge().replaceOoxmlParts(parts, options || {});
}

async function applySearchReplacePairs(pairs, options = {}) {
  const result = await requireBridge().applySearchReplacePairs(pairs, options || {});
  if (!result.canControlTracking && !(options && options.requireTrackControl)) {
    setNotice("warn", "Nie udało się odczytać lub tymczasowo wyłączyć trybu śledzenia zmian. Po operacji sprawdź, czy Word nie oznaczył podstawień jako nowych zmian.");
  }
  return result;
}

async function getCompressedDocumentBase64WithTimeout(ms = 8000) {
  const result = await requireBridge().getCompressedDocumentBase64({
    timeoutMs: ms,
    timeoutMessage: "Word nie zwrócił pełnego pliku w wyznaczonym czasie. Przechodzę do bezpiecznego trybu awaryjnego."
  });
  if (!result || result.length < 20) {
    throw new Error("Word zwrócił pusty lub nieprawidłowy plik DOCX. Zapisz dokument (Ctrl+S) i spróbuj ponownie.");
  }
  return result;
}

async function getDocumentText() {
  return await requireBridge().readBodyText();
}

async function replaceBodyWithText(text, options = {}) {
  return await requireBridge().replaceBodyWithText(text, options || {});
}

// ─── Restore report helpers ──────────────────────────────────────────────────

function restoreReportNotice(report, replacementsPayload) {
  if (!report) return "Dane zostały przywrócone z lokalnej mapy podstawień.";
  const restored = Number(report.restored_occurrences || 0);
  const missing = Number(report.missing_total || 0);
  const leftovers = Number(report.leftover_total_after_restore || 0);
  const unknown = Number(report.unknown_total || 0);

  if (!missing && !leftovers && !unknown) {
    return `Dane przywrócono. Przywrócono ${restored} wystąpień; nie wykryto brakujących placeholderów.`;
  }

  let detail = "";
  if (missing && report.missing_placeholders && replacementsPayload) {
    const lookup = Object.fromEntries((replacementsPayload || []).map((r) => [r.placeholder, r]));
    const lines = (report.missing_placeholders || []).slice(0, 10).map((ph) => {
      const row = lookup[ph] || {};
      const original = row.original || "(nieznana wartość)";
      const category = CATEGORY_LABELS[row.category] || row.category || "kategoria nieznana";
      return `• ${ph} [${category}] → ${original}`;
    });
    detail = `\n\nBrakujące dane (nie przywrócono):\n${lines.join("\n")}`;
    if ((report.missing_placeholders || []).length > 10) {
      detail += `\n… oraz ${(report.missing_placeholders || []).length - 10} kolejnych.`;
    }
  }

  let leftoverDetail = "";
  if (leftovers && report.leftover_placeholders_after_restore) {
    leftoverDetail = `\n\nPlaceholdery nadal widoczne po przywróceniu: ${(report.leftover_placeholders_after_restore || []).slice(0, 10).join(", ")}`;
  }

  return (
    `Przywrócono ${restored} wystąpień. Uwaga: ${missing} placeholder(ów) z mapy ` +
    `nie odnaleziono w dokumencie — odpowiadające im dane nie zostały przywrócone. ` +
    `Nieznane placeholdery: ${unknown}; placeholdery widoczne po przywróceniu: ${leftovers}.` +
    detail +
    leftoverDetail +
    `\n\nJeśli to efekt celowej zmiany przez Claude, możesz zignorować ostrzeżenie po ręcznej kontroli. ` +
    `W razie wątpliwości użyj kopii awaryjnej z folderu ${backupFolderLabel("…")}.`
  );
}

function restoreReportNoticeLevel(report, usedFallback) {
  if (usedFallback) return "warn";
  if (!report) return "good";
  if (Number(report.missing_total || 0) > 0) return "danger";
  if (Number(report.leftover_total_after_restore || 0) > 0 || Number(report.unknown_total || 0) > 0) return "warn";
  return "good";
}

function restoreHasUnresolvedPlaceholders(report) {
  if (!report) return false;
  return Number(report.leftover_total_after_restore || 0) > 0 || Number(report.unknown_total || 0) > 0;
}

async function keepSafeModeActiveAfterFailedRestore(mapId, message) {
  try { if (mapId) await markDocumentMasked({ mapId, reason: "restore-failed-keep-masked", sessionId: currentSessionId() }); } catch (_) { try { await markDocumentError({ reason: "restore-failed", keepExisting: true }); } catch (_) {} }
  try { if (!getSetting(MODE_KIND_SETTING_KEY)) await saveSetting(MODE_KIND_SETTING_KEY, "parts"); } catch (_) {}
  await setDataClearAfterRestore(false);
  stepState(4, [1,2,3]);
  setState("danger", "Przywracanie nie zostało zakończone", "Placeholdery nadal są widoczne albo raport wskazuje nierozwiązane placeholdery. Tryb Claude pozostaje aktywny.");
  setNotice("danger", message || "Nie udało się potwierdzić pełnego przywrócenia danych. Mapa pozostaje aktywna, aby można było ponowić przywracanie.");
  $("btnMain") && $("btnMain").classList.add("hidden");
  $("btnRestore") && ($("btnRestore").textContent = "Ponów przywrócenie wersji jawnej");
  $("btnRestore") && $("btnRestore").classList.remove("hidden");
  $("btnEmergency") && $("btnEmergency").classList.remove("hidden");
  setClearDataAcknowledgementControl(false);
  setStatus(`Przywracanie nie zostało zakończone. Tryb Claude pozostaje aktywny, a mapa pozostaje przypisana do dokumentu: ${mapId || "brak"}.\nNie zapisuj dokumentu jako finalnego. Ponów przywracanie albo użyj kopii awaryjnej po ręcznej decyzji.`);
}

// ─── Document analysis helpers ───────────────────────────────────────────────

function containsClaudeSafePlaceholder(text) {
  return /\[[A-ZĄĆĘŁŃÓŚŹŻ_]+_\d+(?:_[A-Z0-9_]+)?\]/.test(String(text || ""));
}

function ooxmlContainsRevisionMarkup(value) {
  return /<(?:[a-zA-Z0-9]+:)?(?:ins|del|moveFrom|moveTo|pPrChange|rPrChange|tblPrChange|trPrChange|tcPrChange)\b|<(?:[a-zA-Z0-9]+:)?delText\b/.test(String(value || ""));
}

function partsContainRevisionMarkup(parts) {
  return Object.values(parts || {}).some((value) => ooxmlContainsRevisionMarkup(value));
}

function countOccurrences(text, needle) {
  const source = String(text || "");
  const token = String(needle || "");
  if (!token) return 0;
  let count = 0;
  let pos = 0;
  while (true) {
    const idx = source.indexOf(token, pos);
    if (idx < 0) break;
    count += 1;
    pos = idx + token.length;
  }
  return count;
}

function visiblePlaceholders(text) {
  return Array.from(new Set((String(text || "").match(/\[[A-ZĄĆĘŁŃÓŚŹŻ_]+_\d+(?:_[A-Z0-9_]+)?\]/g) || [])));
}

function buildRangePairs(replacements, direction) {
  const seen = new Set();
  const pairs = [];
  for (const r of replacements || []) {
    const from = direction === "restore" ? r.placeholder : r.original;
    const to = direction === "restore" ? r.original : r.placeholder;
    if (!from || !to) continue;
    const key = `${from}${to}`;
    if (seen.has(key)) continue;
    seen.add(key);
    pairs.push({ from: String(from), to: String(to), category: r.category || "" });
  }
  pairs.sort((a, b) => b.from.length - a.from.length);
  return pairs;
}

function buildRangeRestoreReport(replacements, beforeText, afterText) {
  // missing: placeholders from the map that were found in beforeText but remain in afterText.
  // Placeholders absent from beforeText are NOT counted as missing — they may have been
  // successfully restored in headers/footers which getDocumentText() does not return.
  const missingSet = new Set();
  let restored = 0;
  for (const r of replacements || []) {
    if (!r || !r.placeholder) continue;
    const beforeCount = countOccurrences(beforeText, r.placeholder);
    const afterCount = countOccurrences(afterText, r.placeholder);
    if (beforeCount > 0) {
      restored += Math.max(0, beforeCount - afterCount);
      if (afterCount > 0) missingSet.add(r.placeholder);
    }
  }
  const leftovers = visiblePlaceholders(afterText);
  return {
    restored_occurrences: restored,
    missing_total: missingSet.size,
    missing_placeholders: Array.from(missingSet),
    unknown_total: 0,
    unknown_placeholders: [],
    leftover_total_after_restore: leftovers.length,
    leftover_placeholders_after_restore: leftovers
  };
}

async function maskVisibleTextByRange(originalDocxBase64, bodyScan, options = {}) {
  const reviewMode = selectedReviewMode(options.reviewMode);
  const beforeText = await getDocumentText();
  const scan = bodyScan || await apiPost("/scan", { text: beforeText, ...reviewModePayload(reviewMode) });
  if (Number(scan.entities_count || 0) <= 0) {
    throw new Error("Tryb zakresowy nie wykrył danych w widocznej treści dokumentu.");
  }
  const data = await apiPost("/mask", { text: beforeText, original_docx_base64: originalDocxBase64, ...reviewModePayload(reviewMode) });
  const restoreMap = await apiPost("/restore", { map_id: data.map_id });
  const replacements = (restoreMap && restoreMap.replacements) || [];
  const pairs = buildRangePairs(replacements, "mask");
  const applied = await applySearchReplacePairs(pairs, { requireTrackControl: Boolean(options.requireTrackControl), preserveRevisionContext: true });
  await verifyVisibleAnonymizationApplied(beforeText, data, "Tryb zakresowy Word", scan.entities_count || data.entities_count || 0);
  if (!applied || Number(applied.replaced || 0) <= 0) {
    throw new Error("Tryb zakresowy Word nie podmienił żadnego zakresu tekstu.");
  }
  data.range_applied = applied.replaced;
  data.range_applied_clean = Number(applied.replacedClean || 0);
  data.range_applied_tracked = Number(applied.replacedTracked || 0);
  data.range_two_pass = Boolean(applied.twoPass);
  data.category_counts = data.category_counts || {};
  return { data, replacements, applied, beforeText };
}


async function persistRevisionMapForCurrentDocument(mapId, mode = "anonymize") {
  const revBridge = revisionBridge();
  if (!revBridge || typeof revBridge.upsertRevisionMap !== "function") {
    return { ok: false, skipped: true, reason: "revision_bridge.js unavailable" };
  }
  if (!mapId) return { ok: false, skipped: true, reason: "missing map_id" };
  try {
    let anchors = [];
    if (typeof revBridge.inspectRevisionAnchors === "function") {
      try {
        const audit = await revBridge.inspectRevisionAnchors();
        anchors = Array.isArray(audit && audit.anchors) ? audit.anchors : [];
      } catch (_) {
        anchors = [];
      }
    }
    const planEndpoint = mode === "restore" ? "/v2/revision/restore" : "/v2/revision/anonymize";
    const plan = await apiPost(planEndpoint, {
      map_id: mapId,
      anchors,
      keep_tracking: true,
      author: "CSM"
    });
    const persisted = await revBridge.upsertRevisionMap({
      mapId: plan.map_id || mapId,
      map_id: plan.map_id || mapId,
      mode: plan.mode || mode,
      operations: plan.operations || [],
      anchors: plan.anchors || anchors,
      schemaVersion: (plan.summary && plan.summary.schema_version) || undefined,
      engineVersion: plan.engine_version || undefined,
      documentMetadata: plan.document_metadata || {},
      customXmlPayload: plan.custom_xml_payload || ""
    });
    return {
      ok: true,
      mapId: plan.map_id || mapId,
      namespace: persisted.namespace || "",
      customXmlPartId: persisted.customXmlPartId || "",
      settingsSaved: Boolean(persisted.settings && persisted.settings.saved),
      customPropertiesSaved: Boolean(persisted.customProperties && persisted.customProperties.saved),
      operationsCount: Number((plan.summary && plan.summary.operations_count) || (plan.operations || []).length || 0),
      anchorsCount: Number((plan.summary && plan.summary.anchors_count) || (plan.anchors || []).length || 0)
    };
  } catch (error) {
    return { ok: false, skipped: false, reason: error && error.message ? error.message : String(error) };
  }
}

async function documentHasVisiblePlaceholder() {
  try {
    return containsClaudeSafePlaceholder(await getDocumentText());
  } catch (_) {
    return false;
  }
}

async function clearSafeModeSettingsForRetry() {
  try { await markDocumentError({ reason: "prepare-failed", keepExisting: true }); } catch (_) {}
  try { await saveSetting(MODE_KIND_SETTING_KEY, ""); } catch (_) {}
  try { await saveSetting(LAST_SUMMARY_SETTING_KEY, ""); } catch (_) {}
}

async function verifyVisibleAnonymizationApplied(beforeText, data, modeLabel, requiredVisibleEntities = 0) {
  const totalEntities = Number(data && data.entities_count || 0);
  const visibleRequired = Number(requiredVisibleEntities || 0);
  if (!totalEntities && !visibleRequired) return true;
  const afterText = await getDocumentText();
  const hasPlaceholder = containsClaudeSafePlaceholder(afterText);
  const changed = String(afterText || "") !== String(beforeText || "");
  if (visibleRequired > 0 && !hasPlaceholder) {
    throw new Error(`${modeLabel || "Tryb pseudonimizacji"} wykrył dane w widocznej treści, ale po operacji nie widać placeholderów. Word nie zastosował bezpiecznie podmiany; dokument nie zostanie oznaczony jako gotowy dla Claude.`);
  }
  if (visibleRequired > 0 && !changed) {
    throw new Error(`${modeLabel || "Tryb pseudonimizacji"} wykrył dane w widocznej treści, ale Word nie zmienił treści głównej. Word nie zastosował bezpiecznie podmiany; dokument nie zostanie oznaczony jako gotowy dla Claude.`);
  }
  return true;
}

async function clearSafeModeSettingsAfterRestore() {
  await completeDocumentRestore("restore-complete");
  await saveSetting(LAST_RESTORE_SETTING_KEY, new Date().toISOString());
  await saveSetting(MODE_KIND_SETTING_KEY, "");
}

// ─── Summary helpers ─────────────────────────────────────────────────────────

function buildSummary(data) {
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const report = data.anonymization_report || data.anonymizationReport || null;
  const residualRisks = report && Array.isArray(report.residual_risks) ? report.residual_risks : [];
  const manualReview = report && Array.isArray(report.manual_review_items) ? report.manual_review_items : [];
  const categoryCounts = (report && report.category_counts) || data.category_counts || data.categoryCounts || {};
  const total = Number(data.entities_count || (report && report.entities_unique) || 0);
  const warningCount = warnings.length + residualRisks.length;
  const roundtrip = (data.negotiation_report && data.negotiation_report.immediate_roundtrip) || null;
  const reportBielik = (report && report.bielik) || {};
  return {
    mapId: data.map_id || "",
    sessionId: data.session_id || "",
    entities: total,
    warnings: warningCount,
    categoryCounts,
    rawWarnings: warnings,
    anonymizationReport: report,
    residualRisks,
    manualReview,
    reportPreparePath: data.report_prepare_path || "",
    replacementsPreview: data.replacements_preview || [],
    roundtrip,
    reviewMode: data.review_mode || (report && report.review_mode) || "standard",
    bielikUsed: Boolean(data.bielik_used || reportBielik.bielik_used),
    bielikFindingsCount: Number(data.bielik_findings_count || reportBielik.bielik_findings_count || 0),
    bielikTimeout: Boolean(data.bielik_timeout || reportBielik.bielik_timeout),
    uncertainReviewCandidates: Array.isArray(data.uncertain_review_candidates) ? data.uncertain_review_candidates : []
  };
}

/** Compute quality level from summary: 0=green, 1=amber, 2=red */
function qualityLevel(summary) {
  const risks = (summary.residualRisks || []).length;
  const manual = (summary.manualReview || []).length;
  const warns = (summary.rawWarnings || []).length;
  if (risks > 3 || warns > 5) return 2;
  if (risks > 0 || manual > 0 || warns > 0) return 1;
  return 0;
}


function uncertainReviewDecisionMap() {
  try {
    const raw = safeLocalStorageGet(UNCERTAIN_REVIEW_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) { return {}; }
}

function rememberUncertainReviewDecision(mapId, decision) {
  const id = String(mapId || "").trim();
  if (!id) return;
  const data = uncertainReviewDecisionMap();
  data[id] = { decision: decision || "seen", at: new Date().toISOString() };
  safeLocalStorageSet(UNCERTAIN_REVIEW_STORAGE_KEY, JSON.stringify(data));
}

function hasSeenUncertainReview(mapId) {
  const id = String(mapId || "").trim();
  if (!id) return false;
  return Boolean(uncertainReviewDecisionMap()[id]);
}

function normalizeUncertainReviewCandidates(candidates) {
  const seen = new Set();
  return (Array.isArray(candidates) ? candidates : []).map((item, index) => {
    const value = String(item && item.value || "").trim();
    const category = normalizeManualCategory(item && (item.suggested_category || item.category), "MANUAL");
    const key = `${value.toLocaleLowerCase()}|${category}`;
    if (!value || seen.has(key)) return null;
    seen.add(key);
    return {
      id: `uncertain-${index}`,
      value,
      category,
      reason: String(item.reason || "wątpliwy element po kontroli CSM"),
      confidence: String(item.confidence || "medium"),
      context: String(item.context || "").slice(0, 220),
    };
  }).filter(Boolean).slice(0, 25);
}

function renderUncertainReviewCallout(summary) {
  const callout = $("uncertainReviewCallout");
  if (!callout) return;
  const candidates = normalizeUncertainReviewCandidates(summary && summary.uncertainReviewCandidates);
  lastUncertainReviewCandidates = candidates;
  callout.classList.toggle("hidden", !candidates.length);
  const btn = $("btnReviewUncertain");
  if (btn && candidates.length) btn.textContent = `Przejrzyj wątpliwe elementy (${candidates.length})`;
}

function renderUncertainReviewList(candidates) {
  const list = $("uncertainReviewList");
  if (!list) return;
  const rows = normalizeUncertainReviewCandidates(candidates);
  if (!rows.length) {
    list.innerHTML = `<div class="quality-ok">Brak wątpliwych elementów do wyboru.</div>`;
    return;
  }
  list.innerHTML = rows.map((c, i) => `
    <label class="uncertain-item">
      <input type="checkbox" data-uncertain-index="${i}" checked />
      <span>
        <span class="uncertain-value">${escapeHtml(c.value)}</span>
        <span class="uncertain-meta">Typ: ${escapeHtml(CATEGORY_LABELS[c.category] || c.category)} · pewność: ${escapeHtml(c.confidence)} · ${escapeHtml(c.reason)}</span>
        ${c.context ? `<span class="uncertain-context">…${escapeHtml(c.context)}…</span>` : ""}
      </span>
    </label>`).join("");
}

function openUncertainReviewModal(summary, force) {
  const source = summary || lastSummary || loadSummary() || {};
  const candidates = normalizeUncertainReviewCandidates(source.uncertainReviewCandidates || lastUncertainReviewCandidates);
  lastUncertainReviewCandidates = candidates;
  if (!candidates.length) {
    if (force) setNotice("info", "Brak wątpliwych elementów do ręcznego wyboru.");
    return false;
  }
  if (!force && hasSeenUncertainReview(source.mapId)) return false;
  renderUncertainReviewList(candidates);
  const modal = $("uncertainReviewModal");
  if (!modal) return false;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  const first = modal.querySelector('input[data-uncertain-index]');
  if (first) first.focus();
  return true;
}

function closeUncertainReviewModal() {
  const modal = $("uncertainReviewModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function skipUncertainReviewModal() {
  const summary = lastSummary || loadSummary() || {};
  rememberUncertainReviewDecision(summary.mapId, "skipped");
  closeUncertainReviewModal();
  setNotice("warn", "Pominięto dodatkową pseudonimizację wątpliwych elementów. Przed wysłaniem do AI przejrzyj plik _CSM_anon.docx ręcznie.");
}

function toggleAllUncertainReviewCandidates() {
  const modal = $("uncertainReviewModal");
  if (!modal) return;
  const boxes = Array.from(modal.querySelectorAll('input[data-uncertain-index]'));
  if (!boxes.length) return;
  const shouldCheck = boxes.some(b => !b.checked);
  boxes.forEach(b => { b.checked = shouldCheck; });
}

async function applySelectedUncertainReviewCandidates() {
  const summary = lastSummary || loadSummary() || {};
  const candidates = normalizeUncertainReviewCandidates(summary.uncertainReviewCandidates || lastUncertainReviewCandidates);
  const modal = $("uncertainReviewModal");
  const selected = [];
  if (modal) {
    modal.querySelectorAll('input[data-uncertain-index]:checked').forEach(input => {
      const idx = parseInt(input.getAttribute("data-uncertain-index"), 10);
      if (Number.isFinite(idx) && candidates[idx]) selected.push(candidates[idx]);
    });
  }
  if (!selected.length) {
    setNotice("warn", "Nie zaznaczono żadnego elementu. Możesz pominąć kontrolę albo zaznaczyć wartości do dodania.");
    return;
  }
  selected.forEach(c => appendLineToTextarea("manualAlways", `${c.value} => ${c.category || "MANUAL"}`));
  renderManualRuleLists();
  rememberUncertainReviewDecision(summary.mapId, "applied");
  const promote = $("uncertainSaveToClient");
  if (promote && promote.checked && manualRulesClientId()) {
    try {
      await promoteRulesToClient(selected.map(c => ({ value: c.value, category: c.category || "MANUAL" })));
      setNotice("info", `Zapisano ${selected.length} reguł także dla klienta „${manualRulesClientId()}”.`);
    } catch (error) {
      setNotice("warn", `Reguły dodano do sesji, ale nie udało się ich zapisać dla klienta: ${error.message || error}`);
    }
  }
  closeUncertainReviewModal();
  setNotice("info", `Dodano ${selected.length} wątpliwych elementów do reguł. Tworzę nową kopię _CSM_anon z rozszerzoną mapą.`);
  await remaskWithManualControls();
}

// Append "always" rules to the client's saved rule set (additive, deduplicated).
async function promoteRulesToClient(alwaysRules) {
  const clientId = manualRulesClientId();
  if (!clientId) throw new Error("Brak nazwy klienta w polu reguł.");
  const current = await apiGet(`/v4/rules?client_id=${encodeURIComponent(clientId)}`);
  const saved = current.client || {};
  const merged = [...(saved.always || [])];
  const seen = new Set(merged.map(x => String((x && x.value) || x).toLowerCase()));
  (alwaysRules || []).forEach(item => {
    const key = String(item.value || "").toLowerCase();
    if (key && !seen.has(key)) { seen.add(key); merged.push(item); }
  });
  await apiPost("/v4/rules", { level: "client", client_id: clientId, controls: { always: merged, never: saved.never || [], category_overrides: saved.category_overrides || {} } });
}

function scheduleUncertainReviewPrompt(summary) {
  const candidates = normalizeUncertainReviewCandidates(summary && summary.uncertainReviewCandidates);
  if (!candidates.length || hasSeenUncertainReview(summary && summary.mapId)) return;
  setTimeout(() => {
    try { openUncertainReviewModal(summary, false); } catch (error) { reportPanelError(error, "uncertain review modal"); }
  }, 250);
}

/** Toggle quality panel open/closed */
function toggleQualityPanel() {
  const panel = $("qualityPanel");
  const btn = $("btnQualityCheck");
  if (!panel) return;
  const open = !panel.classList.contains("hidden");
  panel.classList.toggle("hidden", open);
  if (btn) {
    btn.textContent = open ? "Szczegóły ▾" : "Zwiń ▴";
    btn.setAttribute("aria-expanded", String(!open));
  }
}

function showSummary(summary) {
  if (!summary) return;
  lastSummary = summary;
  const card = $("summaryCard");
  if (card) card.classList.remove("hidden");
  renderUncertainReviewCallout(summary);

  // ── Entity count ──────────────────────────────────────────────────
  const entEl = $("mEntities");
  if (entEl) entEl.textContent = `${summary.entities || 0} wartości`;

  // ── Quality banner ────────────────────────────────────────────────
  const banner = $("qualityBanner");
  const bannerText = $("qualityBannerText");
  if (banner && bannerText) {
    banner.classList.remove("hidden", "green", "amber", "red");
    const level = qualityLevel(summary);
    const risks = (summary.residualRisks || []).length;
    const manual = (summary.manualReview || []).length;
    const warns = (summary.rawWarnings || []).length;
    const total = risks + manual + warns;

    if (level === 0) {
      banner.classList.add("green");
      bannerText.textContent = "Anonimizacja wygląda poprawnie — nie wykryto wątpliwości.";
    } else if (level === 1) {
      banner.classList.add("amber");
      bannerText.textContent = `Wykryto ${total} pozycj${total === 1 ? "ę" : total < 5 ? "e" : "i"} do sprawdzenia przed wysyłką do Claude.`;
    } else {
      banner.classList.add("red");
      bannerText.textContent = `Anonimizacja może być niepełna — ${total} pozycji wymaga kontroli.`;
    }
  }

  // ── Quality panel content (built once, shown on toggle) ───────────
  const details = $("qualityDetails");
  if (details) {
    const report = summary.anonymizationReport || {};
    const risks = summary.residualRisks || [];
    const manual = summary.manualReview || [];
    const warns = summary.rawWarnings || [];
    const coverage = report.coverage || {};
    const rt = summary.roundtrip || null;
    const sections = [];

    // Residual risks
    if (risks.length) {
      sections.push(
        `<div class="quality-section">` +
        `<div class="quality-section-title">Ryzyka pozostałe (${risks.length})</div>` +
        risks.map(x => `<div class="quality-item risk">${escapeHtml(x)}</div>`).join("") +
        `</div>`
      );
    }

    // Manual review items
    if (manual.length) {
      sections.push(
        `<div class="quality-section">` +
        `<div class="quality-section-title">Uwagi do kontroli (${manual.length})</div>` +
        manual.map(x => `<div class="quality-item">${escapeHtml(x)}</div>`).join("") +
        `</div>`
      );
    }

    // Server warnings
    if (warns.length) {
      sections.push(
        `<div class="quality-section">` +
        `<div class="quality-section-title">Ostrzeżenia serwera (${warns.length})</div>` +
        warns.map(x => `<div class="quality-item">${escapeHtml(x)}</div>`).join("") +
        `</div>`
      );
    }

    // Roundtrip test
    if (rt !== null) {
      const rtOk = rt && rt.identical;
      sections.push(
        `<div class="quality-section">` +
        `<div class="quality-section-title">Test roundtrip (prepare→restore)</div>` +
        `<div class="quality-item ${rtOk ? "" : "risk"}">${rtOk ? "✅ Identyczny po odwróceniu — mapa jest spójna." : "⚠ Wystąpiły różnice — sprawdź raport przed użyciem."}</div>` +
        `</div>`
      );
    }

    // Coverage
    const coverageBits = [];
    if (coverage.body) coverageBits.push("treść główna");
    if (Number(coverage.headers || 0)) coverageBits.push("nagłówki");
    if (Number(coverage.footers || 0)) coverageBits.push("stopki");
    if (coverage.comments) coverageBits.push("komentarze");
    if (coverage.footnotes) coverageBits.push("przypisy dolne");
    if (coverage.endnotes) coverageBits.push("przypisy końcowe");
    if (coverageBits.length) {
      sections.push(
        `<div class="quality-section">` +
        `<div class="quality-section-title">Zakres skanowania</div>` +
        `<div class="quality-item">${escapeHtml(coverageBits.join(", "))}</div>` +
        `</div>`
      );
    }

    if (!sections.length) {
      sections.push(`<div class="quality-ok">✅ Brak zidentyfikowanych wątpliwości. Przejrzyj dokument przed przekazaniem do Claude.</div>`);
    }

    if (report.recommendation) {
      sections.push(`<div class="small" style="margin-top:6px;color:var(--muted)">${escapeHtml(report.recommendation)}</div>`);
    }

    details.innerHTML = sections.join("");
  }

  // ── Report path ───────────────────────────────────────────────────
  const pathNotice = $("reportPathNotice");
  if (pathNotice) {
    const reportPath = (summary.anonymizationReport && summary.anonymizationReport.report_prepare_path) || summary.reportPreparePath || "";
    pathNotice.textContent = reportPath ? `Raport: ${reportPath}` : "Raport prepare jest zapisywany w folderze sesji CSM jako report_prepare.json.";
  }

  // ── Category badges ───────────────────────────────────────────────
  const badges = $("categoryBadges");
  if (badges) {
    const entries = Object.entries(summary.categoryCounts || {}).filter(([,v]) => Number(v) > 0).sort((a,b) => b[1]-a[1]).slice(0, 12);
    badges.innerHTML = entries.length
      ? entries.map(([k,v]) => `<span class="badge ${Number(v) > 5 ? "blue" : "blue"}">${escapeHtml(CATEGORY_LABELS[k] || k)}&nbsp;${v}</span>`).join(" ")
      : "";
  }

  // Auto-open quality panel when there are issues
  const panel = $("qualityPanel");
  const btn = $("btnQualityCheck");
  if (panel && btn) {
    const level = qualityLevel(summary);
    if (level > 0) {
      panel.classList.remove("hidden");
      btn.textContent = "Zwiń ▴";
      btn.setAttribute("aria-expanded", "true");
    } else {
      panel.classList.add("hidden");
      btn.textContent = "Szczegóły ▾";
      btn.setAttribute("aria-expanded", "false");
    }
  }

  scheduleUncertainReviewPrompt(summary);
}


function normalizeDocumentProfileValue(value) {
  const profile = String(value || "auto").trim();
  return ["auto", "pleadings", "contracts"].includes(profile) ? profile : "auto";
}

function setDocumentProfileUi(value) {
  const profile = normalizeDocumentProfileValue(value);
  const el = $("documentProfile");
  if (el && el.value !== profile) el.value = profile;
  safeLocalStorageSet(DOCUMENT_PROFILE_STORAGE_KEY, profile);
  updateProfileHint();
  return profile;
}

async function persistSelectedDocumentProfile(value, reason = "user") {
  const profile = setDocumentProfileUi(value);
  try { await saveSettingBestEffort(DOCUMENT_PROFILE_SETTING_KEY, profile); } catch (_) {}
  safeLocalStorageSet(DOCUMENT_PROFILE_STORAGE_KEY, profile);
  return profile;
}

function selectedDocumentProfile() {
  const el = $("documentProfile");
  const value = el && el.value ? String(el.value) : (getSetting(DOCUMENT_PROFILE_SETTING_KEY) || safeLocalStorageGet(DOCUMENT_PROFILE_STORAGE_KEY) || "auto");
  return normalizeDocumentProfileValue(value);
}

function selectedDocumentProfileLabel() {
  const labels = { auto: "Auto / domyślny", pleadings: "Pismo procesowe", contracts: "Umowa" };
  return labels[selectedDocumentProfile()] || labels.auto;
}

function selectedReviewMode(forcedMode) {
  if (forcedMode) return String(forcedMode).trim().toLowerCase();
  const light = $("reviewModeLight");
  return light && light.checked ? "light" : "standard";
}

function reviewModeLabel(mode) {
  const value = selectedReviewMode(mode);
  if (value === "bielik") return "Bielik";
  if (value === "light") return "dokładniejsza kontrola";
  return "szybka anonimizacja";
}

function reviewModePayload(forcedMode) {
  return { review_mode: selectedReviewMode(forcedMode) };
}

function updateProfileHint() {
  const hints = {
    auto: "Auto / domyślny: pełny zestaw bazowych detektorów i standardowy raport ryzyk.",
    pleadings: "Pismo procesowe: CSM szczególnie eksponuje osoby, sądy, sygnatury, adresy i numery identyfikacyjne.",
    contracts: "Umowa: CSM szczególnie eksponuje kontrahentów, spółki, NIP/REGON/KRS/CEIDG, rachunki bankowe, adresy i reprezentantów."
  };
  const hint = $("profileHint");
  if (hint) hint.textContent = hints[selectedDocumentProfile()] || hints.auto;
}

function appendLineToTextarea(id, line) {
  const el = $(id);
  if (!el) return;
  const value = String(line || "").trim();
  if (!value) return;
  const existing = (el.value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (!existing.some(x => x.toLocaleLowerCase() === value.toLocaleLowerCase())) existing.push(value);
  el.value = existing.join("\n");
}

// value = wewnętrzna (angielska) nazwa kategorii wysyłana do backendu (bez zmian),
// label = polski tekst widoczny w selektorze i spójny z placeholderem w dokumencie.
const MANUAL_CATEGORY_OPTIONS = [
  { value: "PERSON", label: "OSOBA" },
  { value: "CONTRACTOR", label: "FIRMA" },
  { value: "COMPANY", label: "FIRMA" },
  { value: "ADDRESS", label: "ADRES" },
  { value: "BANK_ACCOUNT", label: "RACHUNEK_BANKOWY" },
  { value: "NIP", label: "NIP" },
  { value: "REGON", label: "REGON" },
  { value: "KRS", label: "KRS" },
  { value: "CEIDG", label: "CEIDG" },
  { value: "PESEL", label: "PESEL" },
  { value: "IDCARD_PL", label: "DOWOD_OSOBISTY" },
  { value: "PASSPORT", label: "PASZPORT" },
  { value: "COURT", label: "SAD" },
  { value: "SYGNATURA", label: "SYGNATURA" },
  { value: "EMAIL", label: "EMAIL" },
  { value: "PHONE", label: "TELEFON" },
  { value: "MANUAL", label: "MANUAL" },
];

function normalizeManualCategory(value, fallback) {
  const normalized = String(value || "").trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  return normalized || String(fallback || "MANUAL").toUpperCase();
}

function mappingPreviewPlaceholders(exceptPlaceholder) {
  const box = $("mappingPreview");
  if (!box) return [];
  const excluded = String(exceptPlaceholder || "").trim();
  const found = [];
  box.querySelectorAll("button[data-placeholder]").forEach(btn => {
    const p = String(btn.getAttribute("data-placeholder") || "").trim();
    if (p && p !== excluded && !found.includes(p)) found.push(p);
  });
  return found.sort((a, b) => a.localeCompare(b, "pl"));
}

const MANUAL_CATEGORY_CUSTOM_VALUE = "__CUSTOM__";

// Modal picker replaces window.prompt(): the user always chooses from a curated
// <select> (categories or existing placeholders), so typos/nonexistent targets
// can no longer reach the rule list. Resolves to the chosen string, or null on cancel.
function openManualRulePicker({ title, hint, options, initial, allowCustom }) {
  return new Promise(resolve => {
    const modal = $("manualRulePicker");
    const select = $("manualRulePickerSelect");
    const custom = $("manualRulePickerCustom");
    const confirmBtn = $("manualRulePickerConfirm");
    const cancelBtn = $("manualRulePickerCancel");
    if (!modal || !select || !confirmBtn || !cancelBtn) {
      // Defensive fallback if the modal markup is missing: pick the initial/first option.
      resolve(initial || (options[0] && options[0].value) || null);
      return;
    }
    const titleEl = $("manualRulePickerTitle");
    const hintEl = $("manualRulePickerHint");
    if (titleEl) titleEl.textContent = title || "Wybierz";
    if (hintEl) hintEl.textContent = hint || "";
    const opts = options.slice();
    if (allowCustom) opts.push({ value: MANUAL_CATEGORY_CUSTOM_VALUE, label: "Inna kategoria..." });
    select.innerHTML = opts.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label || o.value)}</option>`).join("");
    if (initial && opts.some(o => o.value === initial)) select.value = initial;
    if (custom) { custom.value = ""; custom.classList.add("hidden"); }

    const syncCustom = () => {
      if (!custom) return;
      const isCustom = allowCustom && select.value === MANUAL_CATEGORY_CUSTOM_VALUE;
      custom.classList.toggle("hidden", !isCustom);
      if (isCustom) custom.focus();
    };

    let cleanup;
    const finish = value => { cleanup(); resolve(value); };
    const onConfirm = () => {
      if (allowCustom && select.value === MANUAL_CATEGORY_CUSTOM_VALUE) {
        const typed = normalizeManualCategory(custom && custom.value, "");
        if (!typed) { setNotice("warn", "Wpisz nazwę własnej kategorii albo wybierz z listy."); return; }
        finish(typed);
        return;
      }
      finish(select.value);
    };
    const onCancel = () => finish(null);
    const onKey = e => { if (e.key === "Escape") onCancel(); else if (e.key === "Enter" && document.activeElement !== custom) { e.preventDefault(); onConfirm(); } };
    const onBackdrop = e => { if (e.target === modal) onCancel(); };
    cleanup = () => {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      confirmBtn.removeEventListener("click", onConfirm);
      cancelBtn.removeEventListener("click", onCancel);
      select.removeEventListener("change", syncCustom);
      document.removeEventListener("keydown", onKey);
      modal.removeEventListener("click", onBackdrop);
    };
    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
    select.addEventListener("change", syncCustom);
    document.addEventListener("keydown", onKey);
    modal.addEventListener("click", onBackdrop);
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    syncCustom();
    select.focus();
  });
}

async function promptForManualCategory(currentCategory) {
  const current = normalizeManualCategory(currentCategory, "MANUAL");
  const options = MANUAL_CATEGORY_OPTIONS.map(c => ({ value: c.value, label: c.label }));
  const choice = await openManualRulePicker({
    title: "Zmień typ ukrywanej danej",
    hint: "Wybierz docelową kategorię z listy. Możesz też wpisać własną (opcja „Inna kategoria...”).",
    options,
    initial: MANUAL_CATEGORY_OPTIONS.some(c => c.value === current) ? current : "PERSON",
    allowCustom: true,
  });
  if (choice === null) return null;
  return normalizeManualCategory(choice, current);
}

async function promptForMergeTarget(sourcePlaceholder) {
  const options = mappingPreviewPlaceholders(sourcePlaceholder);
  if (!options.length) {
    setNotice("warn", "Brak innych placeholderów w bieżącym podglądzie — nie ma z czym scalić. Najpierw pokaż listę ukrytych danych.");
    return null;
  }
  const choice = await openManualRulePicker({
    title: `Scal ${sourcePlaceholder} z...`,
    hint: "Wybierz istniejący placeholder docelowy z bieżącego podglądu. Nie da się wpisać nieistniejącego.",
    options: options.map(p => ({ value: p, label: p })),
    initial: options[0],
    allowCustom: false,
  });
  if (choice === null) return null;
  const target = String(choice || "").trim();
  if (!/^\[[A-Z0-9_]+\]$/.test(target)) return "";
  return target;
}

async function addManualRuleFromMapping(action, value, category, placeholder) {
  const rawValue = String(value || "").trim();
  const rawCategory = normalizeManualCategory(category, "MANUAL");
  const rawPlaceholder = String(placeholder || "").trim();
  if (action === "never" && rawValue) {
    appendLineToTextarea("manualNever", rawValue);
    setNotice("good", "Dodano regułę: nigdy nie anonimizuj tej wartości. Zastosuj reguły, aby utworzyć nową kopię _CSM_anon.");
  } else if (action === "always" && rawValue) {
    appendLineToTextarea("manualAlways", `${rawValue} => ${rawCategory || "MANUAL"}`);
    setNotice("good", "Dodano regułę: zawsze anonimizuj tę wartość. Zastosuj reguły, aby utworzyć nową kopię _CSM_anon.");
  } else if (action === "category" && rawValue) {
    const targetCategory = await promptForManualCategory(rawCategory);
    if (!targetCategory) { setNotice("warn", "Nie dodano reguły zmiany kategorii."); return; }
    appendLineToTextarea("manualCategory", `${rawValue} => ${targetCategory}`);
    setNotice("good", `Dodano regułę zmiany kategorii na ${targetCategory}. Zastosuj reguły, aby utworzyć nową kopię _CSM_anon.`);
  } else if (action === "merge" && rawPlaceholder) {
    const targetPlaceholder = await promptForMergeTarget(rawPlaceholder);
    if (!targetPlaceholder) { setNotice("warn", "Nie dodano scalania. Wskaż poprawny placeholder docelowy, np. [OSOBA_3]."); return; }
    if (targetPlaceholder === rawPlaceholder) { setNotice("warn", "Nie dodano scalania placeholdera samego do siebie."); return; }
    appendLineToTextarea("manualMerge", `${rawPlaceholder} => ${targetPlaceholder}`);
    setNotice("good", `Dodano scalanie: ${rawPlaceholder} => ${targetPlaceholder}. Zastosuj reguły, aby utworzyć nową kopię _CSM_anon.`);
  }
  renderManualRuleLists();
}

function renderMappingActions(r) {
  const original = escapeHtml(r.original || "");
  const category = escapeHtml(r.category || "MANUAL");
  const placeholder = escapeHtml(r.placeholder || "");
  return `<div class="negotiation-actions" style="gap:4px;flex-wrap:wrap">
    <button class="ghost" data-map-action="never" data-value="${original}" data-category="${category}" data-placeholder="${placeholder}">Nie ukrywaj</button>
    <button class="ghost" data-map-action="always" data-value="${original}" data-category="${category}" data-placeholder="${placeholder}">Zawsze ukrywaj</button>
    <button class="ghost" data-map-action="category" data-value="${original}" data-category="${category}" data-placeholder="${placeholder}">Zmień typ</button>
    <button class="ghost" data-map-action="merge" data-value="${original}" data-category="${category}" data-placeholder="${placeholder}">Scal z...</button>
  </div>`;
}

function bindMappingPreviewActionButtons() {
  const box = $("mappingPreview");
  if (!box) return;
  box.querySelectorAll("button[data-map-action]").forEach(btn => {
    btn.addEventListener("click", () => addManualRuleFromMapping(btn.getAttribute("data-map-action"), btn.getAttribute("data-value"), btn.getAttribute("data-category"), btn.getAttribute("data-placeholder")));
  });
}

// A "never" line may start with "!" — an explicitly confirmed (forced) rule.
// Only forced rules may unmask checksum-validated detections (PESEL, NIP, IBAN...).
function parseNeverLine(line) {
  const trimmed = String(line || "").trim();
  if (trimmed.startsWith("!")) {
    const value = trimmed.slice(1).trim();
    return value ? { value, force: true } : null;
  }
  return trimmed || null;
}

function neverItemValue(item) {
  return typeof item === "string" ? item : String((item && item.value) || "");
}

function neverItemForced(item) {
  return Boolean(item && typeof item === "object" && item.force);
}

function readManualControlsFromPanel() {
  const alwaysText = ($("manualAlways") && $("manualAlways").value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const neverText = ($("manualNever") && $("manualNever").value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const categoryText = ($("manualCategory") && $("manualCategory").value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const mergeText = ($("manualMerge") && $("manualMerge").value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const always = alwaysText.map(line => {
    const m = line.match(/^(.+?)\s*=>\s*([A-Za-z0-9_]+)$/);
    return m ? { value: m[1].trim(), category: m[2].trim().toUpperCase() } : { value: line, category: "MANUAL" };
  });
  const never = neverText.map(parseNeverLine).filter(Boolean);
  const category_overrides = {};
  categoryText.forEach(line => {
    const m = line.match(/^(.+?)\s*=>\s*([A-Za-z0-9_]+)$/);
    if (m) category_overrides[m[1].trim()] = m[2].trim().toUpperCase();
  });
  const merge_placeholders = [];
  mergeText.forEach(line => {
    const m = line.match(/^(\[[A-Za-z0-9_]+\])\s*=>\s*(\[[A-Za-z0-9_]+\])$/);
    if (m && m[1] !== m[2]) merge_placeholders.push({ source: m[1], target: m[2] });
  });
  return { always, never, category_overrides, merge_placeholders };
}

// The four textareas remain the single source of truth (and the exact backend
// contract). removeManualRuleLine deletes one line (0-based index) from a textarea
// and re-renders the visible lists, so users can drop a single rule without the
// blanket "Wyczyść reguły".
function removeManualRuleLine(id, index) {
  const el = $(id);
  if (!el) return;
  const lines = (el.value || "").split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (index < 0 || index >= lines.length) return;
  lines.splice(index, 1);
  el.value = lines.join("\n");
  renderManualRuleLists();
}

function ruleRowHtml(id, index, textHtml) {
  return `<div class="rule-row"><span class="rule-row-text">${textHtml}</span>` +
    `<button type="button" class="ghost rule-row-remove" data-rule-remove="${escapeHtml(id)}" data-rule-index="${index}" aria-label="Usuń tę regułę">Usuń</button></div>`;
}

// Renders each textarea's lines into its visible list. Reuses the same parsing as
// readManualControlsFromPanel so the display can never drift from what is sent.
function renderManualRuleLists() {
  const controls = readManualControlsFromPanel();
  const always = $("ruleListAlways");
  if (always) {
    always.innerHTML = (controls.always || []).map((item, i) => {
      const value = escapeHtml(item.value || "");
      const cat = escapeHtml(item.category || "MANUAL");
      return ruleRowHtml("manualAlways", i, `${value}<span class="rule-arrow">→ typ</span><span class="rule-cat">${cat}</span>`);
    }).join("");
  }
  const never = $("ruleListNever");
  if (never) {
    never.innerHTML = (controls.never || []).map((item, i) => {
      const value = escapeHtml(neverItemValue(item));
      const forced = neverItemForced(item) ? `<span class="rule-cat" title="Reguła wymuszona — może odsłonić dane zweryfikowane sumą kontrolną (PESEL, NIP, IBAN...)">wymuszona</span>` : "";
      return ruleRowHtml("manualNever", i, `${value}${forced}`);
    }).join("");
  }
  const category = $("ruleListCategory");
  if (category) {
    category.innerHTML = Object.entries(controls.category_overrides || {}).map(([value, cat], i) =>
      ruleRowHtml("manualCategory", i, `${escapeHtml(value)}<span class="rule-arrow">→</span><span class="rule-cat">${escapeHtml(cat)}</span>`)
    ).join("");
  }
  const merge = $("ruleListMerge");
  if (merge) {
    merge.innerHTML = (controls.merge_placeholders || []).map((item, i) =>
      ruleRowHtml("manualMerge", i, `${escapeHtml(item.source)}<span class="rule-arrow">→</span><span class="rule-cat">${escapeHtml(item.target)}</span>`)
    ).join("");
  }
}

function bindManualRuleListActions() {
  ["ruleListAlways", "ruleListNever", "ruleListCategory", "ruleListMerge"].forEach(listId => {
    const list = $(listId);
    if (!list || list.dataset.csmBound) return;
    list.addEventListener("click", e => {
      const btn = e.target.closest("button[data-rule-remove]");
      if (!btn) return;
      removeManualRuleLine(btn.getAttribute("data-rule-remove"), parseInt(btn.getAttribute("data-rule-index"), 10));
    });
    list.dataset.csmBound = "1";
  });
  // Editing the advanced textareas by hand should also refresh the visible lists.
  ["manualAlways", "manualNever", "manualCategory", "manualMerge"].forEach(id => {
    const el = $(id);
    if (!el || el.dataset.csmListBound) return;
    el.addEventListener("input", () => renderManualRuleLists());
    el.dataset.csmListBound = "1";
  });
}


function writeManualControlsToPanel(controls) {
  const normalized = controls || {};
  const always = Array.isArray(normalized.always) ? normalized.always : [];
  const never = Array.isArray(normalized.never) ? normalized.never : [];
  const categoryOverrides = normalized.category_overrides || {};
  const merge = Array.isArray(normalized.merge_placeholders) ? normalized.merge_placeholders : [];
  const alwaysLines = always.map(item => {
    if (typeof item === "string") return item;
    const value = String(item.value || item.text || "").trim();
    const category = String(item.category || "MANUAL").trim().toUpperCase();
    return value ? `${value} => ${category}` : "";
  }).filter(Boolean);
  const categoryLines = Object.entries(categoryOverrides).map(([value, category]) => `${value} => ${String(category).toUpperCase()}`);
  const mergeLines = merge.map(item => {
    const source = String(item.source || item.from || "").trim();
    const target = String(item.target || item.to || "").trim();
    return source && target ? `${source} => ${target}` : "";
  }).filter(Boolean);
  const neverLines = never.map(item => {
    const value = neverItemValue(item).trim();
    if (!value) return "";
    return neverItemForced(item) ? `!${value}` : value;
  }).filter(Boolean);
  const fields = { manualAlways: alwaysLines.join("\n"), manualNever: neverLines.join("\n"), manualCategory: categoryLines.join("\n"), manualMerge: mergeLines.join("\n") };
  Object.entries(fields).forEach(([id, value]) => { const el = $(id); if (el) el.value = value; });
  renderManualRuleLists();
}

function manualControlsMetadata(action) {
  return {
    app_version: APP_VERSION,
    action: action || "manual-controls",
    saved_at: new Date().toISOString(),
    local_only: true,
    privacy_notice: "Reguły ręczne są zapisane wyłącznie lokalnie w panelu CSM i nie są wysyłane do chmury.",
  };
}

function manualControlsToPreset(action) {
  return { metadata: manualControlsMetadata(action), controls: readManualControlsFromPanel() };
}

function summarizeControlsForUser(controls) {
  const c = controls || {};
  const counts = {
    always: Array.isArray(c.always) ? c.always.length : 0,
    never: Array.isArray(c.never) ? c.never.length : 0,
    category_overrides: c.category_overrides ? Object.keys(c.category_overrides).length : 0,
    merge_placeholders: Array.isArray(c.merge_placeholders) ? c.merge_placeholders.length : 0,
  };
  return `zawsze: ${counts.always}, nigdy: ${counts.never}, kategorie: ${counts.category_overrides}, scalanie: ${counts.merge_placeholders}`;
}

function saveManualControlsPreset() {
  try {
    const preset = manualControlsToPreset("save");
    safeLocalStorageSet(MANUAL_CONTROLS_STORAGE_KEY, JSON.stringify(preset));
    setNotice("good", `Zapisano lokalny zestaw reguł: ${summarizeControlsForUser(preset.controls)}.`);
    setStatus("Reguły ręczne zapisano lokalnie w przeglądarce/panelu CSM. Nie wysłano ich poza komputer.");
  } catch (error) {
    setNotice("warn", `Nie udało się zapisać reguł: ${error.message || error}`);
  }
}

function loadManualControlsPreset() {
  try {
    const raw = safeLocalStorageGet(MANUAL_CONTROLS_STORAGE_KEY);
    if (!raw) throw new Error("Brak lokalnie zapisanego zestawu reguł.");
    const preset = JSON.parse(raw);
    writeManualControlsToPanel(preset.controls || preset);
    setNotice("good", `Wczytano lokalny zestaw reguł: ${summarizeControlsForUser(preset.controls || preset)}.`);
    setStatus("Wczytano reguły ręczne z lokalnego zapisu. Sprawdź pola przed zastosowaniem.");
  } catch (error) {
    setNotice("warn", `Nie udało się wczytać reguł: ${error.message || error}`);
  }
}

function manualControlsToPlainText(controls) {
  const c = controls || readManualControlsFromPanel();
  const lines = [];
  lines.push("# CSM — ręczne reguły ukrywania danych");
  lines.push("# Plik może zawierać jawne dane. Nie wysyłaj go dalej bez potrzeby.");
  lines.push("");
  lines.push("# ZAWSZE UKRYWAJ");
  (Array.isArray(c.always) ? c.always : []).forEach(item => {
    if (typeof item === "string") { if (item.trim()) lines.push(item.trim()); return; }
    const value = String(item.value || item.text || "").trim();
    const category = String(item.category || "").trim().toUpperCase();
    if (value) lines.push(category && category !== "MANUAL" ? `${value} => ${category}` : value);
  });
  lines.push("");
  lines.push("# NIE UKRYWAJ");
  (Array.isArray(c.never) ? c.never : []).forEach(item => {
    const v = neverItemValue(item).trim();
    if (v) lines.push(neverItemForced(item) ? `!${v}` : v);
  });
  lines.push("");
  lines.push("# POŁĄCZ OZNACZENIA");
  (Array.isArray(c.merge_placeholders) ? c.merge_placeholders : []).forEach(item => {
    const source = String(item.source || item.from || "").trim();
    const target = String(item.target || item.to || "").trim();
    if (source && target) lines.push(`${source} => ${target}`);
  });
  const categoryOverrides = c.category_overrides || {};
  const categoryEntries = Object.entries(categoryOverrides).filter(([value, category]) => String(value || "").trim() && String(category || "").trim());
  if (categoryEntries.length) {
    lines.push("");
    lines.push("# ZMIEŃ TYP UKRYTEJ DANEJ");
    categoryEntries.forEach(([value, category]) => lines.push(`${String(value).trim()} => ${String(category).trim().toUpperCase()}`));
  }
  return lines.join("\n").replace(/\n{3,}/g, "\n\n") + "\n";
}

function parseManualControlsPlainText(text) {
  const controls = { always: [], never: [], category_overrides: {}, merge_placeholders: [] };
  let section = "always";
  String(text || "").split(/\r?\n/).forEach(rawLine => {
    const line = String(rawLine || "").trim();
    if (!line) return;
    if (/^#/.test(line)) {
      const header = line.replace(/^#+\s*/, "").toLowerCase();
      if (header.includes("nie ukrywaj") || header.includes("nigdy")) section = "never";
      else if (header.includes("połącz") || header.includes("polacz") || header.includes("scal")) section = "merge";
      else if (header.includes("zmień") || header.includes("zmien") || header.includes("typ") || header.includes("kategor")) section = "category";
      else if (header.includes("zawsze") || header.includes("ukrywaj")) section = "always";
      return;
    }
    if (section === "never") {
      const parsed = parseNeverLine(line);
      if (parsed) controls.never.push(parsed);
      return;
    }
    if (section === "merge") {
      const m = line.match(/^(\[[A-Za-z0-9_]+\])\s*=>\s*(\[[A-Za-z0-9_]+\])$/);
      if (m && m[1] !== m[2]) controls.merge_placeholders.push({ source: m[1], target: m[2] });
      return;
    }
    if (section === "category") {
      const m = line.match(/^(.+?)\s*=>\s*([A-Za-z0-9_]+)$/);
      if (m) controls.category_overrides[m[1].trim()] = m[2].trim().toUpperCase();
      return;
    }
    const m = line.match(/^(.+?)\s*=>\s*([A-Za-z0-9_]+)$/);
    controls.always.push(m ? { value: m[1].trim(), category: m[2].trim().toUpperCase() } : { value: line, category: "MANUAL" });
  });
  return controls;
}

function exportManualControlsPreset() {
  try {
    const controls = readManualControlsFromPanel();
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    downloadTextFile(`CSM-reguly-${stamp}.txt`, manualControlsToPlainText(controls), "text/plain;charset=utf-8");
    setNotice("good", "Wyeksportowano reguły do TXT. Plik może zawierać jawne frazy — traktuj go jak dokument roboczy.");
  } catch (error) {
    setNotice("warn", `Nie udało się wyeksportować reguł: ${error.message || error}`);
  }
}

async function readRulesFileFromUser() {
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "text/plain,.txt,application/json,.json";
    input.onchange = () => {
      const file = input.files && input.files[0];
      if (!file) return reject(new Error("Nie wybrano pliku TXT."));
      const reader = new FileReader();
      reader.onload = () => resolve({ text: String(reader.result || ""), name: file.name || "" });
      reader.onerror = () => reject(reader.error || new Error("Nie udało się odczytać pliku."));
      reader.readAsText(file, "utf-8");
    };
    input.click();
  });
}

async function importManualControlsPreset() {
  try {
    const file = await readRulesFileFromUser();
    let controls;
    const trimmed = String(file.text || "").trim();
    if (/\.json$/i.test(file.name || "") || trimmed.startsWith("{")) {
      const preset = JSON.parse(trimmed);
      controls = preset.controls || preset;
    } else {
      controls = parseManualControlsPlainText(trimmed);
    }
    writeManualControlsToPanel(controls);
    safeLocalStorageSet(MANUAL_CONTROLS_STORAGE_KEY, JSON.stringify({ metadata: manualControlsMetadata("import"), controls }));
    setNotice("good", `Zaimportowano lokalne reguły: ${summarizeControlsForUser(controls)}. Sprawdź je przed zastosowaniem.`);
  } catch (error) {
    setNotice("warn", `Nie udało się zaimportować reguł: ${error.message || error}`);
  }
}

function clearManualControls() {
  ["manualAlways", "manualNever", "manualCategory", "manualMerge"].forEach(id => { const el = $(id); if (el) el.value = ""; });
  renderManualRuleLists();
  const box = $("mappingPreview");
  if (box) box.innerHTML = `<div class="small">Ręczne reguły wyczyszczone lokalnie. Mapa źródłowa nie została zmieniona.</div>`;
  setStatus("Wyczyszczono ręczne reguły w panelu. Aby zmienić dokument, dodaj nowe reguły i kliknij zastosuj.");
}

async function previewCurrentMap() {
  const summary = lastSummary || loadSummary() || {};
  const mapId = summary.mapId || lastV4MapId();
  if (!mapId) {
    const msg = "Brak aktywnej listy ukrytych danych. Najpierw utwórz zanonimizowaną kopię.";
    setNotice("warn", msg);
    setStatus(msg);
    return null;
  }
  updateProfileHint();
  const data = await apiPost("/v4/map/preview", { map_id: mapId, document_profile: selectedDocumentProfile() });
  lastMappingPreview = data;
  const box = $("mappingPreview");
  if (box) {
    const notice = data.privacy_notice ? `<div class="notice warn" style="margin:0 0 8px 0">${escapeHtml(data.privacy_notice)}</div>` : "";
    const profile = data.selected_profile || {};
    const profileBox = profile.label ? `<div class="notice good" style="margin:0 0 8px 0"><strong>Profil:</strong> ${escapeHtml(profile.label)}. Kategorie priorytetowe: ${escapeHtml((profile.priority_categories || []).join(", ") || "standardowe")}</div>` : "";
    const rows = (data.replacements || []).slice(0, 120).map(r => `<tr><td>${escapeHtml(r.placeholder || "")}</td><td>${escapeHtml(CATEGORY_LABELS[r.category] || r.category || "")}</td><td>${escapeHtml(r.original || "")}</td><td>${escapeHtml(String(r.count || 1))}</td><td>${renderMappingActions(r)}</td></tr>`).join("");
    box.innerHTML = notice + profileBox + (rows ? `<table style="width:100%;font-size:11px;border-collapse:collapse"><thead><tr><th>Placeholder</th><th>Kategoria</th><th>Wartość lokalna</th><th>Ile</th><th>Reguła</th></tr></thead><tbody>${rows}</tbody></table>` : `<div class="small">Brak mapowań.</div>`);
    bindMappingPreviewActionButtons();
  }
  setStatus(`Podgląd mapowań v1.5: ${data.replacements ? data.replacements.length : 0} pozycji, profil: ${selectedDocumentProfileLabel()}. Dane są pokazywane tylko lokalnie w panelu CSM.`);
  return data;
}

function mappingPreviewToText(payload) {
  const data = payload || lastMappingPreview;
  if (!data) return "Brak pobranego podglądu mapowań. Najpierw kliknij: Pokaż listę ukrytych danych.";
  const counts = Object.entries(data.category_counts || {}).filter(([, v]) => Number(v) > 0).sort((a, b) => Number(b[1]) - Number(a[1])).map(([k, v]) => `- ${CATEGORY_LABELS[k] || k}: ${v}`).join("\n") || "- brak danych kategorii";
  const rows = (data.replacements || []).map(r => `${r.placeholder || ""}	${CATEGORY_LABELS[r.category] || r.category || ""}	${r.original || ""}	${r.count || 1}`).join("\n") || "brak mapowań";
  return `CSM ${data.version || APP_VERSION} — lokalna lista ukrytych danych\nMapa: ${data.map_id || "brak"}\nData: ${data.preview_generated_at || new Date().toISOString()}\n\nUwaga: ${data.privacy_notice || "Podgląd zawiera wartości źródłowe i jest przeznaczony tylko do lokalnej kontroli."}\n\nKategorie:\n${counts}\n\nPlaceholder\tKategoria\tWartość lokalna\tIle\n${rows}`;
}

async function ensureMappingPreviewLoaded() {
  if (lastMappingPreview && Array.isArray(lastMappingPreview.replacements)) return lastMappingPreview;
  return await previewCurrentMap();
}

async function copyMappingPreview() {
  try {
    const data = await ensureMappingPreviewLoaded();
    await copyTextToClipboard(mappingPreviewToText(data));
    setNotice("good", "Lista ukrytych danych została skopiowana do schowka jako TXT. Nie wysyłaj jej poza komputer, jeśli zawiera dane jawne.");
  } catch (error) {
    setNotice("warn", `Nie udało się skopiować listy: ${error.message || error}`);
  }
}

async function downloadMappingPreview() {
  try {
    const data = await ensureMappingPreviewLoaded();
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    downloadTextFile(`CSM-mapping-preview-${stamp}.json`, JSON.stringify(data, null, 2), "application/json;charset=utf-8");
    setNotice("good", "Lokalny podgląd mapowań został przygotowany do pobrania jako JSON.");
  } catch (error) {
    setNotice("warn", `Nie udało się pobrać mapowań: ${error.message || error}`);
  }
}

async function remaskWithManualControls() {
  const summary = lastSummary || loadSummary() || {};
  const mapId = summary.mapId || lastV4MapId();
  const sessionId = summary.sessionId || lastV4SessionId();
  if (!mapId) {
    const msg = "Brak aktywnej mapy. Najpierw utwórz kopię do Claude.";
    setNotice("warn", msg);
    setStatus(msg);
    return null;
  }
  const controls = readManualControlsFromPanel();
  if (!controls.always.length && !controls.never.length && !Object.keys(controls.category_overrides || {}).length && !(controls.merge_placeholders || []).length) {
    const msg = "Dodaj co najmniej jedną regułę: zawsze ukrywaj, nigdy nie ukrywaj, zmień typ albo połącz oznaczenia.";
    setNotice("warn", msg);
    setStatus(msg);
    return null;
  }
  setBusy(true, "Regeneruję kopię z ręcznymi regułami...", "btnApplyManualControls");
  try {
    const data = await apiPostHeavy("/v4/current/remask-session", { map_id: mapId, session_id: sessionId, filename: currentDocumentFilename("dokument.docx"), open_file: true, controls, client_id: manualRulesClientId() || undefined, document_profile: selectedDocumentProfile(), ...reviewModePayload() });
    await rememberV4Session(data);
    const newSummary = buildSummary(data);
    newSummary.modeKind = "docx-v4-current";
    newSummary.reportPreparePath = data.report_prepare_path || "";
    await saveSummary(newSummary);
    showSummary(newSummary);
    renderControlsEffects(data.controls_effects, data.saved_rules, "po utworzeniu kopii");
    setNotice("good", "Utworzono nową kopię _CSM_anon.docx z ręcznymi regułami. Sprawdź ją przed wysłaniem do Claude.");
    setStatus(`v1.6 remask zakończony. Nowa mapa: ${data.map_id}\nPlik roboczy: ${data.anon_path}\nRaport: ${data.report_prepare_path || "report_prepare.json"}`);
  } finally {
    setBusy(false);
  }
}

// ---------- manual rules: client scope, dry-run preview, accountability ----------

const MANUAL_RULES_CLIENT_STORAGE_KEY = "csm.manualRules.clientId";

function manualRulesClientId() {
  const el = $("manualRulesClient");
  return el ? String(el.value || "").trim() : "";
}

function persistManualRulesClientId() {
  safeLocalStorageSet(MANUAL_RULES_CLIENT_STORAGE_KEY, manualRulesClientId());
}

function restoreManualRulesClientId() {
  const el = $("manualRulesClient");
  if (!el) return;
  const saved = safeLocalStorageGet(MANUAL_RULES_CLIENT_STORAGE_KEY);
  if (saved && !el.value) el.value = saved;
}

function describeRuleEffectsHtml(effects) {
  const e = effects || {};
  const rows = [];
  (Array.isArray(e.always) ? e.always : []).forEach(rule => {
    const total = Number(rule.matches || 0) + Number(rule.variant_matches || 0);
    const variantInfo = Number(rule.variant_matches || 0) > 0 ? ` (w tym odmiany: ${rule.variant_matches})` : "";
    const cls = total > 0 ? "good" : "warn";
    const examples = (rule.examples || []).slice(0, 2).map(x => `<div class="uncertain-context">…${escapeHtml(String(x.context || ""))}…</div>`).join("");
    rows.push(`<div class="notice ${cls}" style="margin:4px 0"><strong>Zawsze ukrywaj:</strong> ${escapeHtml(rule.value || "")} → ${escapeHtml(rule.category || "MANUAL")} — dopasowań: ${total}${variantInfo}${total === 0 ? " — reguła nic nie zmienia w tym dokumencie" : ""}${examples}</div>`);
  });
  (Array.isArray(e.never) ? e.never : []).forEach(rule => {
    const blocked = rule.blocked_hard && Object.keys(rule.blocked_hard).length ? Object.entries(rule.blocked_hard).map(([k, v]) => `${k}: ${v}`).join(", ") : "";
    const suppressed = Number(rule.suppressed || 0);
    const cls = blocked ? "bad" : (suppressed > 0 ? "good" : "warn");
    const examples = (rule.examples || []).slice(0, 3).map(x => `<div class="uncertain-context">[${escapeHtml(String(x.category || ""))}] …${escapeHtml(String(x.context || ""))}…</div>`).join("");
    const blockedInfo = blocked ? `<div><strong>Uwaga:</strong> reguła objęłaby dane zweryfikowane sumą kontrolną (${escapeHtml(blocked)}) — pozostały ukryte. Aby je odsłonić świadomie, poprzedź regułę znakiem <code>!</code> (np. <code>!${escapeHtml(rule.value || "")}</code>).</div>` : "";
    rows.push(`<div class="notice ${cls}" style="margin:4px 0"><strong>Nie ukrywaj:</strong> ${escapeHtml(rule.value || "")}${rule.force ? " (wymuszona)" : ""} — wyłączonych wykryć: ${suppressed}${suppressed === 0 && !blocked ? " — reguła nic nie zmienia w tym dokumencie" : ""}${blockedInfo}${examples}</div>`);
  });
  const dead = Array.isArray(e.dead_rules) ? e.dead_rules.filter(Boolean) : [];
  if (dead.length) {
    rows.push(`<div class="small" style="margin:4px 0"><strong>Reguły bez efektu w tym dokumencie:</strong> ${dead.map(escapeHtml).join(", ")}. Jeśli to reguły zapisane na stałe, rozważ ich przegląd.</div>`);
  }
  (Array.isArray(e.warnings) ? e.warnings : []).forEach(w => {
    rows.push(`<div class="notice warn" style="margin:4px 0">${escapeHtml(String(w || ""))}</div>`);
  });
  return rows.join("") || `<div class="small">Brak aktywnych reguł do oceny.</div>`;
}

function renderControlsEffects(effects, savedRules, contextLabel) {
  const box = $("controlsPreviewBox");
  if (!box) return;
  if (!effects || (!Array.isArray(effects.always) && !Array.isArray(effects.never))) {
    return;
  }
  const saved = savedRules || {};
  const savedInfo = (Number(saved.global_rules || 0) + Number(saved.client_rules || 0)) > 0
    ? `<div class="small">Dołączone zapisane reguły — kancelaria: ${Number(saved.global_rules || 0)}, klient: ${Number(saved.client_rules || 0)}.</div>`
    : "";
  box.innerHTML = `<div class="small" style="margin-top:6px"><strong>Skuteczność reguł ${escapeHtml(contextLabel || "")}</strong> (dane wyłącznie lokalne):</div>` + savedInfo + describeRuleEffectsHtml(effects);
}

async function previewManualControlsEffects() {
  const summary = lastSummary || loadSummary() || {};
  const mapId = summary.mapId || lastV4MapId();
  if (!mapId) {
    setNotice("warn", "Brak aktywnej mapy. Najpierw utwórz zanonimizowaną kopię — podgląd reguł działa na oryginale z sesji.");
    return null;
  }
  const controls = readManualControlsFromPanel();
  setBusy(true, "Sprawdzam skutki reguł (bez zmiany plików)...", "btnPreviewControls");
  try {
    const data = await apiPost("/v4/controls/preview", { map_id: mapId, controls, client_id: manualRulesClientId() || undefined });
    renderControlsEffects(data.effects, data.saved_rules, "— podgląd przed zastosowaniem");
    const s = data.controls_summary || {};
    setStatus(`Podgląd skutków reguł gotowy (reguł łącznie: ${s.total || 0}). Żaden plik nie został zmieniony.`);
    return data;
  } catch (error) {
    setNotice("warn", `Nie udało się przygotować podglądu reguł: ${error.message || error}`);
    return null;
  } finally {
    setBusy(false);
  }
}

function persistableControlsFromPanel() {
  const controls = readManualControlsFromPanel();
  // merge_placeholders are map-specific and are intentionally not persisted.
  return { always: controls.always, never: controls.never, category_overrides: controls.category_overrides };
}

async function saveManualRulesToLevel(level) {
  const clientId = manualRulesClientId();
  if (level === "client" && !clientId) {
    setNotice("warn", "Podaj nazwę klienta/sprawy w polu obok, aby zapisać reguły dla klienta.");
    return;
  }
  const controls = persistableControlsFromPanel();
  if (!controls.always.length && !controls.never.length && !Object.keys(controls.category_overrides || {}).length) {
    setNotice("warn", "Brak reguł do zapisania. Dodaj reguły w polach powyżej.");
    return;
  }
  const label = level === "client" ? `klienta „${clientId}”` : "całej kancelarii";
  try {
    // Merge with already saved rules of that level so saving is additive, not destructive.
    const current = await apiGet(`/v4/rules${level === "client" ? `?client_id=${encodeURIComponent(clientId)}` : ""}`);
    const saved = level === "client" ? (current.client || {}) : (current.global || {});
    const mergedAlways = [...(saved.always || [])];
    const seenAlways = new Set(mergedAlways.map(x => String((x && x.value) || x).toLowerCase()));
    controls.always.forEach(item => { const key = String(item.value || "").toLowerCase(); if (key && !seenAlways.has(key)) { seenAlways.add(key); mergedAlways.push(item); } });
    const mergedNever = [...(saved.never || [])];
    const seenNever = new Set(mergedNever.map(x => neverItemValue(x).toLowerCase()));
    controls.never.forEach(item => { const key = neverItemValue(item).toLowerCase(); if (key && !seenNever.has(key)) { seenNever.add(key); mergedNever.push(item); } });
    const mergedOverrides = Object.assign({}, saved.category_overrides || {}, controls.category_overrides || {});
    const payload = { level, client_id: level === "client" ? clientId : undefined, controls: { always: mergedAlways, never: mergedNever, category_overrides: mergedOverrides } };
    const data = await apiPost("/v4/rules", payload);
    const c = data.controls || {};
    setNotice("good", `Zapisano reguły dla ${label} (zawsze: ${(c.always || []).length}, nigdy: ${(c.never || []).length}, typy: ${Object.keys(c.category_overrides || {}).length}). Będą dołączane automatycznie przy każdej anonimizacji${level === "client" ? " z tym klientem" : ""}.`);
  } catch (error) {
    setNotice("warn", `Nie udało się zapisać reguł dla ${label}: ${error.message || error}`);
  }
}

async function showSavedManualRules() {
  const clientId = manualRulesClientId();
  try {
    const data = await apiGet(`/v4/rules${clientId ? `?client_id=${encodeURIComponent(clientId)}` : ""}`);
    const box = $("controlsPreviewBox");
    if (!box) return;
    const renderLevel = (label, rules) => {
      const r = rules || {};
      const always = (r.always || []).map(x => `${escapeHtml(String((x && x.value) || x))} → ${escapeHtml(String((x && x.category) || "MANUAL"))}`).join("<br>") || "—";
      const never = (r.never || []).map(x => `${neverItemForced(x) ? "!" : ""}${escapeHtml(neverItemValue(x))}`).join("<br>") || "—";
      const overrides = Object.entries(r.category_overrides || {}).map(([k, v]) => `${escapeHtml(k)} → ${escapeHtml(v)}`).join("<br>") || "—";
      return `<div class="small" style="margin:4px 0"><strong>${escapeHtml(label)}</strong><br>Zawsze ukrywaj:<br>${always}<br>Nie ukrywaj:<br>${never}<br>Zmiany typu:<br>${overrides}</div>`;
    };
    let html = `<div class="small" style="margin-top:6px"><strong>Zapisane reguły (lokalnie)</strong></div>` + renderLevel("Kancelaria (wszystkie dokumenty)", data.global);
    if (clientId) html += renderLevel(`Klient: ${clientId}`, data.client);
    const clients = (data.clients || []);
    if (clients.length) html += `<div class="small">Klienci z zapisanymi regułami: ${clients.map(escapeHtml).join(", ")}</div>`;
    box.innerHTML = html;
    setStatus("Wyświetlono lokalnie zapisane reguły. Zapisane reguły są dołączane automatycznie przy anonimizacji.");
  } catch (error) {
    setNotice("warn", `Nie udało się pobrać zapisanych reguł: ${error.message || error}`);
  }
}

function currentReportPayload() {
  const summary = lastSummary || loadSummary() || {};
  return {
    app_version: APP_VERSION,
    generated_at: new Date().toISOString(),
    report_type: "anonymization_report",
    map_id: summary.mapId || "",
    entities: summary.entities || 0,
    warnings: summary.warnings || 0,
    category_counts: summary.categoryCounts || {},
    anonymization_report: summary.anonymizationReport || {},
    residual_risks: summary.residualRisks || [],
    manual_review_items: summary.manualReview || [],
    document_profile: selectedDocumentProfile(),
    review_mode: summary.reviewMode || "standard",
    bielik_used: Boolean(summary.bielikUsed),
    bielik_findings_count: Number(summary.bielikFindingsCount || 0),
    bielik_timeout: Boolean(summary.bielikTimeout),
    note: "Raport nie zawiera surowych podejrzanych danych. Służy do kontroli jakości pseudonimizacji CSM."
  };
}

function reportPayloadToText(payload) {
  const counts = Object.entries(payload.category_counts || {})
    .filter(([, v]) => Number(v) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([k, v]) => `- ${CATEGORY_LABELS[k] || k}: ${v}`)
    .join("\n") || "- brak danych kategorii";
  const risks = (payload.residual_risks || []).map(x => `- ${x}`).join("\n") || "- brak oczywistych ryzyk pozostałych";
  const manual = (payload.manual_review_items || []).map(x => `- ${x}`).join("\n") || "- brak dodatkowych uwag kontrolnych";
  const bielik = payload.bielik_used
    ? `sprawdzono, wykryto ${payload.bielik_findings_count || 0} potencjalne ryzyka${payload.bielik_timeout ? " (timeout)" : ""}`
    : "nie użyto";
  return `CSM ${payload.app_version} — raport anonimizacji\nData: ${payload.generated_at}\nMapa: ${payload.map_id || "brak"}\nTryb kontroli: ${payload.review_mode || "standard"}\nBielik: ${bielik}\nUnikalne wartości: ${payload.entities}\nPozycje do kontroli: ${payload.warnings}\n\nKategorie:\n${counts}\n\nRyzyka pozostałe:\n${risks}\n\nUwagi kontrolne:\n${manual}\n\n${payload.note}`;
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const el = document.createElement("textarea");
  el.value = text;
  el.setAttribute("readonly", "readonly");
  el.style.position = "fixed";
  el.style.left = "-9999px";
  document.body.appendChild(el);
  el.select();
  try { document.execCommand("copy"); return true; }
  finally { document.body.removeChild(el); }
}

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

async function copyAnonymizationReport() {
  try {
    const payload = currentReportPayload();
    await copyTextToClipboard(reportPayloadToText(payload));
    setNotice("good", "Raport anonimizacji skopiowany do schowka.");
  } catch (error) {
    setNotice("warn", `Nie udało się skopiować raportu: ${error.message || error}`);
  }
}

function downloadAnonymizationReport() {
  try {
    const payload = currentReportPayload();
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    downloadTextFile(`CSM-anonymization-report-${stamp}.json`, JSON.stringify(payload, null, 2), "application/json;charset=utf-8");
    setNotice("good", "Raport anonimizacji został przygotowany do pobrania.");
  } catch (error) {
    setNotice("warn", `Nie udało się pobrać raportu: ${error.message || error}`);
  }
}

async function saveSummary(summary) {
  try { await saveSetting(LAST_SUMMARY_SETTING_KEY, JSON.stringify(summary || {})); } catch (_) {}
}

function loadSummary() {
  try {
    const raw = getSetting(LAST_SUMMARY_SETTING_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

// ─── Main action dispatcher ──────────────────────────────────────────────────


// --- v0.4 negotiation DOCX file workflow ------------------------------------

function currentDocumentFilename(defaultName = "dokument.docx") {
  try {
    const url = (Office && Office.context && Office.context.document && Office.context.document.url) || "";
    if (url) {
      const clean = decodeURIComponent(String(url).split(/[?#]/)[0]);
      const name = clean.replace(/\\/g, "/").split("/").pop();
      if (name && /\.docx$/i.test(name)) return name;
    }
  } catch (_) {}
  return defaultName;
}

/**
 * Return the full path of the active document (e.g. C:\Users\...\umowa.docx).
 * Office.context.document.url gives a file:// URI or a Windows path in desktop Word.
 * Returns empty string when unavailable (browser / unsaved document).
 */
function officeUrlToLocalPath(rawUrl) {
  try {
    const raw = String(rawUrl || "").trim();
    if (!raw) return "";
    const noHash = raw.split(/[?#]/)[0];
    // Office may return either C:\... / C:/... or a file URL. Preserve UNC
    // paths: file://server/share/doc.docx must become \\server\share\doc.docx,
    // while file:///C:/Users/... becomes C:\Users\... .
    if (/^file:\/\//i.test(noHash)) {
      const url = new URL(noHash);
      let pathname = decodeURIComponent(url.pathname || "");
      if (/^\/[a-zA-Z]:\//.test(pathname)) pathname = pathname.slice(1);
      pathname = pathname.replace(/\//g, "\\");
      if (url.hostname) return ("\\\\" + url.hostname + (pathname.startsWith("\\") ? pathname : "\\" + pathname)).trim();
      return pathname.trim();
    }
    let path = decodeURIComponent(noHash);
    if (/^[a-zA-Z]:\//.test(path)) path = path.replace(/\//g, "\\");
    return path.trim();
  } catch (_) {
    return "";
  }
}

function currentDocumentFullPath() {
  try {
    const url = (Office && Office.context && Office.context.document && Office.context.document.url) || "";
    return officeUrlToLocalPath(url);
  } catch (_) {}
  return "";
}

function currentDocumentFullPathAsync(timeoutMs = 2000) {
  const direct = currentDocumentFullPath();
  if (direct) return Promise.resolve(direct);
  return new Promise((resolve) => {
    let done = false;
    const finish = (value) => { if (!done) { done = true; resolve(value || ""); } };
    const timer = setTimeout(() => finish(""), Math.max(250, timeoutMs || 2000));
    try {
      const doc = Office && Office.context && Office.context.document;
      if (!doc || typeof doc.getFilePropertiesAsync !== "function") {
        clearTimeout(timer);
        finish("");
        return;
      }
      doc.getFilePropertiesAsync((asyncResult) => {
        clearTimeout(timer);
        try {
          const url = asyncResult && asyncResult.value && asyncResult.value.url;
          finish(officeUrlToLocalPath(url));
        } catch (_) {
          finish("");
        }
      });
    } catch (_) {
      clearTimeout(timer);
      finish("");
    }
  });
}

// Close the CSM task pane when the Word document it belongs to is being
// closed server-side. In Word/WebView2 the old pane can otherwise remain visible
// for a moment after prepare/restore and display misleading connection errors
// while the backend is switching documents.
let csmTaskpaneCloseScheduled = false;

function closeCsmTaskpane(reason) {
  try { console.info(`[CSM] closing taskpane: ${reason || "document closed"}`); } catch (_) {}
  try {
    const ui = Office && Office.context && Office.context.ui;
    if (ui && typeof ui.closeContainer === "function") {
      ui.closeContainer();
      return true;
    }
  } catch (_) {}
  try {
    window.close();
    return true;
  } catch (_) {}
  return false;
}

function closeCsmTaskpaneSoon(reason, delayMs = 700) {
  if (csmTaskpaneCloseScheduled) return;
  csmTaskpaneCloseScheduled = true;
  const safeDelay = Math.max(0, Number(delayMs) || 0);
  setTimeout(() => { closeCsmTaskpane(reason); }, safeDelay);
}


function safeLocalStorageSet(key, value) {
  try { window.localStorage && window.localStorage.setItem(key, String(value || "")); } catch (_) {}
}

function safeLocalStorageGet(key) {
  try { return (window.localStorage && window.localStorage.getItem(key)) || ""; } catch (_) { return ""; }
}

async function saveSettingBestEffort(key, value) {
  try { await saveSetting(key, value); return true; } catch (_) { return false; }
}

async function enableTaskpaneAutoShowForCurrentDocument(reason = "prepare") {
  // Office supports a special document setting that asks Word to reopen the
  // task pane with this document. We set it before exporting the DOCX package,
  // so the generated *_CSM_anon.docx has the best chance of opening with CSM
  // already visible. Some tenant/Word builds can ignore it; manual opening from
  // Add-ins remains the safe fallback.
  try {
    Office.context.document.settings.set(OFFICE_AUTO_SHOW_TASKPANE_KEY, true);
    Office.context.document.settings.set("CSM_V4_AUTO_SHOW_REASON", reason || "prepare");
    await new Promise((resolve, reject) => {
      Office.context.document.settings.saveAsync((result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) resolve();
        else reject(result.error || new Error("saveAsync failed"));
      });
    });
    return true;
  } catch (e) {
    console.warn("[CSM] could not enable Office.AutoShowTaskpaneWithDocument", e);
    return false;
  }
}

async function rememberV4Session(data) {
  if (!data) return;
  const mapId = data.map_id || "";
  const sessionId = data.session_id || mapId || "";
  const anonPath = data.anon_path || "";
  if (mapId) {
    await saveSettingBestEffort(V4_LAST_MAP_SETTING_KEY, mapId);
    safeLocalStorageSet(V4_LAST_MAP_SETTING_KEY, mapId);
  }
  if (sessionId) {
    await saveSettingBestEffort(V4_LAST_SESSION_ID_KEY, sessionId);
    safeLocalStorageSet(V4_LAST_SESSION_ID_KEY, sessionId);
  }
  if (anonPath) {
    await saveSettingBestEffort(V4_LAST_ANON_PATH_KEY, anonPath);
    safeLocalStorageSet(V4_LAST_ANON_PATH_KEY, anonPath);
  }
  if (data.document_profile) {
    await persistSelectedDocumentProfile(data.document_profile, "response");
  }
}

function lastV4MapId() {
  return getSetting(V4_LAST_MAP_SETTING_KEY) || safeLocalStorageGet(V4_LAST_MAP_SETTING_KEY) || activeMapId() || "";
}

function lastV4SessionId() {
  return getSetting(V4_LAST_SESSION_ID_KEY) || safeLocalStorageGet(V4_LAST_SESSION_ID_KEY) || currentSessionId();
}

function lastV4AnonPath() {
  return getSetting(V4_LAST_ANON_PATH_KEY) || safeLocalStorageGet(V4_LAST_ANON_PATH_KEY) || "";
}

async function rememberV4SourceContext(filename, knownSourcePath) {
  const source = filename || currentDocumentFilename("");
  // Prefer the path captured synchronously at prepare-start (before any await / focus switch).
  const sourcePath = knownSourcePath || currentDocumentFullPath();
  const preparedAt = new Date().toISOString();
  if (source) {
    await saveSettingBestEffort(V4_LAST_SOURCE_FILENAME_KEY, source);
    safeLocalStorageSet(V4_LAST_SOURCE_FILENAME_KEY, source);
  }
  if (sourcePath) {
    await saveSettingBestEffort(V4_LAST_SOURCE_PATH_KEY, sourcePath);
    safeLocalStorageSet(V4_LAST_SOURCE_PATH_KEY, sourcePath);
  }
  await saveSettingBestEffort(V4_LAST_PREPARED_AT_KEY, preparedAt);
  safeLocalStorageSet(V4_LAST_PREPARED_AT_KEY, preparedAt);
}

function lastV4SourcePath() {
  return getSetting(V4_LAST_SOURCE_PATH_KEY) || safeLocalStorageGet(V4_LAST_SOURCE_PATH_KEY) || "";
}

function lastV4SourceFilename() {
  return getSetting(V4_LAST_SOURCE_FILENAME_KEY) || safeLocalStorageGet(V4_LAST_SOURCE_FILENAME_KEY) || "";
}

function lastV4PreparedAt() {
  return getSetting(V4_LAST_PREPARED_AT_KEY) || safeLocalStorageGet(V4_LAST_PREPARED_AT_KEY) || "";
}

function normalizeDocFilenameForCompare(value) {
  const raw = String(value || "").replace(/\\/g, "/").split(/[?#]/)[0].split("/").pop() || "";
  return raw.trim().toLowerCase();
}

function lastPrepareAgeMs() {
  const preparedAt = Date.parse(lastV4PreparedAt() || "");
  if (!Number.isFinite(preparedAt)) return Number.POSITIVE_INFINITY;
  return Math.max(0, Date.now() - preparedAt);
}

function canUseLastSavedAnonFallback(context) {
  if (!lastV4AnonPath()) {
    // State was never saved — most likely because a previous prepare call aborted
    // before the server responded. Suggest the recovery paths explicitly.
    const currentName = currentDocumentFilename("");
    const currentNorm = normalizeDocFilenameForCompare(currentName);
    if (currentNorm && /_csm_anon\.docx$/i.test(currentNorm)) {
      // Task pane happens to be on the anon copy already — allow it so
      // tryRestoreFromCurrentAnonPackage can use the Office.js package directly.
      return { ok: true, reason: "aktywny dokument wygląda na kopię CSM (brak zapisanej ścieżki sesji)" };
    }
    return {
      ok: false,
      reason: "CSM nie zapamiętał ścieżki do pliku *_CSM_anon.docx z tej sesji. " +
        "Przełącz się w Wordzie do otwartego pliku *_CSM_anon.docx i kliknij 'Twórz wersję jawną' stamtąd, " +
        "albo wskaż ten plik ręcznie w sekcji poniżej."
    };
  }
  const currentName = currentDocumentFilename("");
  const sourceName = lastV4SourceFilename();
  const currentNorm = normalizeDocFilenameForCompare(currentName);
  const sourceNorm = normalizeDocFilenameForCompare(sourceName);

  if (currentNorm && /_csm_jawny\.docx$/i.test(currentNorm)) {
    return { ok: false, reason: "To już jest wersja jawna. Nie tworzę jej ponownie." };
  }
  if (currentNorm && /_csm_anon\.docx$/i.test(currentNorm)) {
    return { ok: true, reason: "aktywny dokument wygląda na kopię CSM" };
  }
  if (currentNorm && sourceNorm && currentNorm !== sourceNorm) {
    return {
      ok: false,
      reason: `Ostatnia zapamiętana kopia CSM dotyczyła pliku „${sourceName}”, a aktywny panel Worda wskazuje „${currentName}”. Żeby nie przywrócić danych z innej sprawy, wskaż właściwy plik *_CSM_anon.docx ręcznie w sekcji „Pomoc i ustawienia zaawansowane”.`
    };
  }
  const ageMs = lastPrepareAgeMs();
  const recent = ageMs <= 12 * 60 * 60 * 1000;
  if (!currentNorm && !recent) {
    return {
      ok: false,
      reason: "Nie umiem potwierdzić, którego dokumentu dotyczy ostatnia sesja CSM. Wskaż właściwy plik *_CSM_anon.docx ręcznie w sekcji „Pomoc i ustawienia zaawansowane”."
    };
  }
  return { ok: true, reason: currentNorm ? "aktywny dokument pasuje do ostatniej sesji CSM" : "ostatnia sesja CSM jest świeża" };
}

function setManualRestoreHint(message) {
  const el = document.getElementById("manualRestoreHint");
  if (el) el.textContent = message || "";
}

function selectedManualRestoreFile() {
  const input = document.getElementById("manualRestoreFile");
  return input && input.files && input.files.length ? input.files[0] : null;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      const marker = ";base64,";
      const index = value.indexOf(marker);
      resolve(index >= 0 ? value.slice(index + marker.length) : value);
    };
    reader.onerror = () => reject(reader.error || new Error("Nie udało się odczytać pliku DOCX."));
    reader.readAsDataURL(file);
  });
}

async function readV4CurrentStatusSafe(timeoutMs = 12000) {
  if (!serverOk) return null;
  try {
    const docxBase64 = await getCompressedDocumentBase64WithTimeout(timeoutMs);
    const mapId = lastV4MapId();
    return await apiPost("/v4/current/status", { docx_base64: docxBase64, map_id: mapId || undefined });
  } catch (_) {
    return null;
  }
}

function describeWordCloseReport(data) {
  try {
    const report = data && data.word_close_report;
    if (!report || !report.scheduled) return "";
    const via = report.path_provided ? "ścieżce" : "unikalnej nazwie pliku";
    return `\nAutomatyczne zamknięcie poprzedniego dokumentu: zaplanowane po ${via}.`;
  } catch (_) {
    return "";
  }
}

function describeOpenResult(data, kind) {
  if (!data) return "";
  const closeText = describeWordCloseReport(data);
  if (data.opened_file) {
    return (kind === "restore"
      ? "\nCSM otworzył oryginalny plik w Wordzie i zamknie kopię roboczą _CSM_anon."
      : "\nCSM otworzył kopię do pracy z Claude w Wordzie i zamknie oryginał.") + closeText;
  }
  if (data.open_error) {
    return `\nNie udało się automatycznie otworzyć pliku: ${data.open_error}\nPlik zapisano w: ${kind === "restore" ? data.restored_path : data.anon_path}`;
  }
  return `\nPlik zapisano w: ${kind === "restore" ? data.restored_path : data.anon_path}`;
}

// Note: document closing is handled server-side via _close_word_document_async
// (PowerShell COM automation in api.py). Word.run()-based closing was unreliable
// because after the new document opens, Word.run() binds to the new document
// context rather than the original one the add-in was attached to.

function buildPrepareSuccessMessage(data) {
  const count = Number((data && data.entities_count) || 0);
  const mode = (data && data.review_mode) || "standard";
  const bielik = data && data.bielik_used
    ? `Bielik: sprawdzono, wykryto ${Number(data.bielik_findings_count || 0)} potencjalne ryzyka.`
    : "Bielik: nie użyto.";
  return `Gotowe. Utworzyłem kopię do pracy z Claude i próbuję otworzyć ją w Wordzie.

Pracuj teraz w pliku z końcówką _CSM_anon.docx. Oryginał nie został zmieniony.

Po zakończeniu pracy kliknij „Utwórz i otwórz wersję jawną”.

Tryb kontroli: ${mode}. ${bielik}

Wykryto i zastąpiono: ${count} wartości.`;
}

function buildRestoreSuccessMessage(data) {
  const report = (data && data.restore_report) || {};
  const quality = (data && data.restore_quality_report) || {};
  const left = Number(report.leftover_total_after_restore || 0);
  const reviewItems = Array.isArray(quality.manual_review_items) ? quality.manual_review_items : [];
  const extra = reviewItems.length ? `

Raport restore: ${reviewItems.slice(0,3).join(" ")}` : "";
  return `Gotowe. Utworzyłem wersję jawną dokumentu.

Pracuj teraz w pliku z końcówką _CSM_jawny.docx. Plik _CSM_anon.docx pozostaje bez zmian jako kopia robocza.

Przywrócone wystąpienia: ${report.restored_occurrences || 0}. Pozostałe placeholdery: ${left}.${extra}`;
}

function inferFilenameKind(filename) {
  const name = String(filename || "").toLowerCase();
  if (/_csm_anon\.docx$/i.test(name)) return "anon";
  if (/_csm_jawny\.docx$/i.test(name)) return "restored";
  return "original";
}

async function readV4DocumentContext(options = {}) {
  const filename = currentDocumentFilename("dokument.docx");
  let kind = inferFilenameKind(filename);
  let metadata = null;
  let hasVisiblePlaceholder = false;
  const status = await readV4CurrentStatusSafe(options.timeoutMs || 5000);
  if (status && status.metadata) {
    metadata = status.metadata;
    if (metadata.document_profile) await persistSelectedDocumentProfile(metadata.document_profile, "metadata");
    if (metadata.csm_document_kind === "anon") kind = "anon";
    if (metadata.csm_document_kind === "restored") kind = "restored";
  }
  if (kind === "original" || options.forcePlaceholderScan) {
    hasVisiblePlaceholder = await documentHasVisiblePlaceholder();
    if (hasVisiblePlaceholder) kind = "anon";
  }
  return { kind, filename, metadata, hasVisiblePlaceholder };
}

function setButtonDisabled(id, disabled, title) {
  const el = $(id);
  if (!el) return;
  el.disabled = Boolean(disabled);
  if (title) el.title = title;
  else el.removeAttribute("title");
}

function setStepDisabled(id, disabled) {
  const el = $(id);
  if (!el) return;
  el.classList.toggle("disabled", Boolean(disabled));
  el.setAttribute("aria-disabled", disabled ? "true" : "false");
}

function applyV4ActionAvailability(context) {
  if (busy) return;
  const ctx = context || lastDocumentContext || { kind: "unknown", filename: "" };
  const kind = ctx.kind || "unknown";
  const fallback = canUseLastSavedAnonFallback(ctx);
  const prepareDisabled = kind === "anon";
  // Word can keep the task pane attached to the original document after CSM opens
  // *_CSM_anon.docx. Do not require the Office.js active-document context for
  // restore if we have a saved anonymized session file. Still block restored files.
  const restoreDisabled = kind === "restored" || (kind !== "anon" && !fallback.ok);
  setButtonDisabled("btnV4Prepare", prepareDisabled, prepareDisabled
    ? "Ten dokument jest już kopią _CSM_anon. Nie przygotowuj go ponownie — po pracy utwórz wersję jawną."
    : "Utwórz z aktualnego dokumentu kopię _CSM_anon do pracy z Claude.");
  setButtonDisabled("btnV4PrepareBielik", prepareDisabled, prepareDisabled
    ? "Ten dokument jest już kopią _CSM_anon. Po pracy utwórz wersję jawną."
    : "Utwórz kopię _CSM_anon i uruchom dodatkowe sprawdzenie Bielikiem.");
  setButtonDisabled("btnV4Restore", restoreDisabled, restoreDisabled
    ? (kind === "restored" ? "To już jest wersja jawna. Nie trzeba tworzyć jej ponownie." : "Wersję jawną można utworzyć po przygotowaniu kopii _CSM_anon.docx.")
    : (kind === "anon" ? "Utwórz wersję jawną z aktualnego pliku _CSM_anon.docx." : "Utwórz wersję jawną z ostatniej zapisanej kopii _CSM_anon.docx."));
  setStepDisabled("step2", prepareDisabled);
  setStepDisabled("step4", restoreDisabled);
}

async function requireDocumentKindForV4(expectedKind, operationLabel) {
  const ctx = await readV4DocumentContext({ forcePlaceholderScan: true, timeoutMs: 5000 });
  lastDocumentContext = ctx;
  applyV4ActionAvailability(ctx);
  if (expectedKind === "original" && ctx.kind === "anon") {
    setNotice("info", "Ten dokument jest już kopią do pracy z Claude (_CSM_anon.docx). Nie przygotowuj go ponownie. Po pracy użyj przycisku „Utwórz i otwórz wersję jawną”.");
    throw new Error("Ten dokument jest już kopią _CSM_anon.docx.");
  }
  if (expectedKind === "anon" && ctx.kind !== "anon") {
    const message = ctx.kind === "restored"
      ? "To już jest wersja jawna. Nie można tworzyć wersji jawnej ponownie z pliku _CSM_jawny.docx."
      : "Najpierw przełącz się do pliku _CSM_anon.docx utworzonego przez CSM. Dopiero z niego utwórz wersję jawną.";
    setNotice("info", message);
    throw new Error(message);
  }
  return ctx;
}

async function v4PrepareDocxCopy(options = {}) {
  if (busy) return;
  const reviewMode = selectedReviewMode(options.reviewMode);
  const reviewLabel = reviewModeLabel(reviewMode);
  const busyButton = reviewMode === "bielik" ? "btnV4PrepareBielik" : "btnV4Prepare";
  // Capture the original document path BEFORE operations that may switch Word focus.
  let wordSourcePath = currentDocumentFullPath();
  if (!wordSourcePath) {
    wordSourcePath = await currentDocumentFullPathAsync(2000);
  }
  try {
    await requireDocumentKindForV4("original", "prepare");
    if (!await ensureServerReadyForOperation()) {
      setNotice("danger", "Lokalny silnik CSM nie jest gotowy. Uruchom CSM → START, poczekaj na komunikat „gotowy do pracy”, a potem kliknij ten sam przycisk ponownie.");
      return;
    }
    if (reviewMode === "standard") {
      setBusy(true, "Tworzę i otwieram kopię do pracy z Claude...", "btnV4Prepare");
    } else {
      setBusy(true, `Tworzę kopię do pracy z Claude (${reviewLabel})...`, busyButton);
    }
    setNotice("info", `Tworzę bezpieczną kopię. Tryb: ${reviewLabel}. Oryginał pozostanie bez zmian.`);
    setStatus("Włączam automatyczne otwieranie panelu CSM dla dokumentu roboczego...");
    const autoShow = await enableTaskpaneAutoShowForCurrentDocument("prepare-anon-copy");
    setStatus("Pobieram pełny DOCX z aktualnie otwartego dokumentu Word...");
    let docxBase64 = await getCompressedDocumentBase64WithTimeout(30000);
    const filename = currentDocumentFilename("dokument.docx");
    setStatus("Tworzę sesję CSM i kopię spseudonimizowaną w C:\\CSM\\sessions... (duże dokumenty mogą wymagać do 2 minut — nie zamykaj Worda)");
    const chosenProfile = await persistSelectedDocumentProfile(selectedDocumentProfile(), "prepare");
    const data = await apiPostHeavy("/v4/current/prepare", { docx_base64: docxBase64, filename, mode: "preserve", open_file: true, controls: readManualControlsFromPanel(), client_id: manualRulesClientId() || undefined, document_profile: chosenProfile, word_source_path: wordSourcePath || undefined, word_source_name: filename || undefined, ...reviewModePayload(reviewMode) }, 300000);
    await rememberV4Session(data);
    await rememberV4SourceContext(filename, wordSourcePath);
    const summary = buildSummary(data);
    summary.modeKind = "docx-v4-current";
    summary.reportPreparePath = data.report_prepare_path || "";
    await saveSummary(summary);
    showSummary(summary);
    renderControlsEffects(data.controls_effects, data.saved_rules, "po anonimizacji");
    const rt = data.negotiation_report && data.negotiation_report.immediate_roundtrip;
    const rtText = rt ? `\nKontrola roundtrip: ${rt.identical ? "OK" : "RÓŻNICE — sprawdź raport"}` : "";
    const openText = describeOpenResult(data, "prepare");
    const autoShowText = autoShow
      ? "\nPanel CSM powinien automatycznie otworzyć się także w pliku roboczym. Jeśli Word tego nie zrobi, otwórz CSM z Dodatków."
      : "\nNie udało się wymusić automatycznego otwarcia panelu w dokumencie roboczym — w razie potrzeby otwórz CSM z Dodatków.";
    setNotice("good", buildPrepareSuccessMessage(data));
    setStatus(`v1.6 prepare zakończony.${openText}${autoShowText}${rtText}
Plik roboczy: ${data.anon_path}
Oryginał w sesji: ${data.original_path}
Ścieżka oryginału (JS): ${wordSourcePath || "(nieznana — auto-zamknięcie wyłączone)"}
Mapa: ${data.map_id}
Bielik: ${data.bielik_used ? `użyto (${data.bielik_findings_count || 0} potencjalne ryzyka)` : "nie użyto"}
Raport prepare: ${data.report_prepare_path || "C:\\CSM\\sessions\\...\\report_prepare.json"}
Raport: ${JSON.stringify(data.negotiation_report || {}, null, 2)}`);

    // Note: closing the original document is handled server-side via PowerShell COM
    // (_close_word_document_async in api.py) — more reliable than Word.run() because
    // by the time the JS delay fires the active document context has already switched
    // to the newly opened anon copy. Close this old CSM pane as well, so the user
    // does not see stale connection errors after Word closes the source document.
    if ((summary.uncertainReviewCandidates || []).length) {
      setNotice("warn", "CSM znalazł wątpliwe elementy. Zanim zamkniesz panel, zaznacz w popupie te, które mają zostać dodatkowo pseudonimizowane, albo pomiń kontrolę.");
    } else {
      closeCsmTaskpaneSoon("zamknięcie oryginału po prepare", 700);
    }
  } catch (error) {
    setNotice("danger", `Nie udało się utworzyć kopii DOCX: ${error.message || error}`);
    setStatus(`Błąd v1.6 prepare: ${error.message || error}`, true);
  } finally {
    setBusy(false);
  }
}


async function preRestoreRevisionAwareRangePass(mapId) {
  let revisionAnchorAudit = null;
  const revBridge = revisionBridge();
  if (revBridge && typeof revBridge.inspectRevisionAnchors === "function") {
    try { revisionAnchorAudit = await revBridge.inspectRevisionAnchors(); } catch (_) { revisionAnchorAudit = null; }
  }
  const restoreMap = await apiPost("/restore", { map_id: mapId });
  const replacements = (restoreMap && restoreMap.replacements) || [];
  const pairs = buildRangePairs(replacements, "restore");
  if (!pairs.length) {
    return { used: false, reason: "brak mapy podstawień", replaced: 0 };
  }

  let partsHadRevisionMarkup = false;
  try {
    const parts = await collectOoxmlParts();
    partsHadRevisionMarkup = partsContainRevisionMarkup(parts);
  } catch (_) {}

  let trackingRisk = { hasTracking: false, unknown: true };
  try { trackingRisk = await readTrackedChangesRisk(); } catch (_) {}

  const shouldUseRangePass = Boolean(partsHadRevisionMarkup || (trackingRisk.hasTracking && !trackingRisk.unknown));
  if (!shouldUseRangePass) {
    return { used: false, reason: "brak znaczników śledzenia zmian w aktywnym dokumencie", replaced: 0 };
  }

  setStatus("Przywracam oznaczenia w aktywnym dokumencie przed zbudowaniem wersji jawnej. Word sam zachowa historię zmian tam, gdzie jest to możliwe.");
  const applied = await applySearchReplacePairs(pairs, {
    requireTrackControl: true,
    preserveRevisionContext: true
  });
  return {
    used: true,
    reason: "word-range-pre-restore",
    replaced: Number((applied && applied.replaced) || 0),
    replacedClean: Number((applied && applied.replacedClean) || 0),
    replacedTracked: Number((applied && applied.replacedTracked) || 0),
    classifiedClean: Number((applied && applied.classifiedClean) || 0),
    classifiedTracked: Number((applied && applied.classifiedTracked) || 0),
    revisionAware: Boolean(applied && applied.revisionAware),
    twoPass: Boolean(applied && applied.twoPass),
    revisionAnchorAudit
  };
}

async function restoreFromLastSavedAnonPath(options = {}) {
  const anonPath = lastV4AnonPath();
  if (!anonPath) {
    throw new Error("Brak zapamiętanej ścieżki do pliku *_CSM_anon.docx. Użyj ręcznego wskazania pliku w sekcji „Pomoc i ustawienia zaawansowane”.");
  }
  setStatus(`Tworzę wersję jawną z ostatnio zapisanego pliku _CSM_anon: ${anonPath}`);
  setManualRestoreHint("CSM użyje ostatnio zapisanego pliku _CSM_anon.docx z folderu sesji. Jeśli wprowadzałeś zmiany w Wordzie, zapisz plik przed restore (Ctrl+S).");
  return await apiPostHeavy("/v4/session/restore-last", {
    anon_path: anonPath,
    open_file: true,
    map_id: lastV4MapId(),
    session_id: lastV4SessionId(),
    require_changes: Boolean(options.requireChanges),
    word_anon_path: options.wordAnonPath || undefined,
    word_anon_name: options.wordAnonName || undefined
  });
}

async function tryRestoreFromCurrentAnonPackage(ctx, wordAnonPath) {
  const currentName = currentDocumentFilename("dokument_CSM_anon.docx");
  if (ctx && ctx.kind && ctx.kind !== "anon") {
    return { used: false, reason: "aktywny dokument nie jest rozpoznany jako _CSM_anon" };
  }
  try {
    setStatus("Pobieram aktualnie otwarty pakiet DOCX bezpośrednio z Worda, aby ominąć blokady pliku na dysku...");
    let docxBase64 = await getCompressedDocumentBase64WithTimeout(30000);
    const expectedMap = lastV4MapId();
    const status = await apiPost("/v4/current/status", { docx_base64: docxBase64, map_id: expectedMap || undefined });
    const metadata = (status && status.metadata) || {};
    const kind = (status && status.document_kind) || metadata.csm_document_kind || "unknown";
    if (kind !== "anon") {
      return { used: false, reason: "Office.js zwrócił dokument, który nie jest kopią _CSM_anon ani nie zawiera placeholderów z bieżącej mapy" };
    }
    const currentMap = metadata.map_id || (status && status.placeholder_match_map_id) || "";
    if (currentMap && expectedMap && currentMap !== expectedMap) {
      throw new Error("Aktywny plik _CSM_anon.docx należy do innej mapy CSM niż ostatnia sesja. Żeby nie pomieszać spraw, wskaż właściwy plik ręcznie w sekcji „Pomoc i ustawienia zaawansowane”.");
    }
    const resolvedMapForRangePass = expectedMap || currentMap;
    let preRestoreRangePass = { used: false, reason: "pominięto" };
    if (resolvedMapForRangePass) {
      // Wstępny przebieg w Wordzie jest tylko optymalizacją zachowującą kontekst
      // śledzenia zmian. Jego awaria NIE może przerywać restore — lokalny silnik
      // CSM przywróci placeholdery z pakietu dokumentu tak samo poprawnie.
      try {
        preRestoreRangePass = await preRestoreRevisionAwareRangePass(resolvedMapForRangePass);
      } catch (rangePassError) {
        const rangePassMsg = rangePassError && rangePassError.message ? rangePassError.message : String(rangePassError || "nieznany błąd");
        console.warn("[CSM] pre-restore range pass failed; continuing with package restore", rangePassError);
        preRestoreRangePass = { used: false, failed: true, replaced: 0, reason: `błąd wstępnego przywracania w Wordzie: ${rangePassMsg}` };
        setStatus(`Wstępne przywracanie w aktywnym dokumencie nie powiodło się (${rangePassMsg}). Kontynuuję — placeholdery przywróci lokalny silnik CSM z pakietu dokumentu.`);
      }
      if (preRestoreRangePass && preRestoreRangePass.used) {
        setStatus(`Wstępne przywracanie w aktywnym dokumencie zakończone. Podmieniono: ${preRestoreRangePass.replaced}; tracked: ${preRestoreRangePass.replacedTracked}; clean: ${preRestoreRangePass.replacedClean}. Pobieram ponownie plik z Worda do zbudowania wersji jawnej.`);
      }
      if (preRestoreRangePass && (preRestoreRangePass.used || preRestoreRangePass.failed)) {
        // Po przebiegu (także przerwanym w połowie) treść aktywnego dokumentu mogła
        // się zmienić — pobierz pakiet ponownie, aby wersja jawna i plik roboczy
        // były spójne z tym, co widzi Word. Jeśli ponowne pobranie się nie uda,
        // użyj pakietu sprzed przebiegu: nadal zawiera placeholdery, które
        // przywróci serwer.
        try {
          docxBase64 = await getCompressedDocumentBase64WithTimeout(30000);
        } catch (refreshError) {
          console.warn("[CSM] could not re-read package after range pass; using pre-pass package", refreshError);
        }
      }
    }

    setStatus("Tworzę wersję jawną z aktualnie otwartego dokumentu Word, bez czytania zablokowanego pliku z dysku... (może potrwać do 2 minut — nie zamykaj Worda)");
    const data = await apiPostHeavy("/v4/current/restore", {
      docx_base64: docxBase64,
      filename: currentName,
      open_file: true,
      map_id: expectedMap || currentMap,
      session_id: metadata.session_id || lastV4SessionId(),
      word_anon_path: wordAnonPath || undefined,
      word_anon_name: currentName || undefined
    });
    data.restore_source = "officejs-current-package";
    data.pre_restore_range_pass = preRestoreRangePass;
    return { used: true, data };
  } catch (error) {
    console.warn("[CSM] restore from current Office.js package failed; falling back to saved session file", error);
    return { used: false, reason: error && error.message ? error.message : String(error || "nieznany błąd") };
  }
}

async function v4RestoreDocxCopy() {
  if (busy) return;
  // Capture the current doc path BEFORE server checks or other async work.
  let wordAnonPath = currentDocumentFullPath() || lastV4AnonPath();
  if (!wordAnonPath) {
    wordAnonPath = await currentDocumentFullPathAsync(2000) || lastV4AnonPath();
  }
  try {
    if (!await ensureServerReadyForOperation()) {
      setNotice("danger", "Lokalny silnik CSM nie jest gotowy. Uruchom CSM → START, poczekaj na komunikat „gotowy do pracy”, a potem kliknij ponownie „Utwórz i otwórz wersję jawną”. Nie musisz tworzyć kopii od nowa.");
      return;
    }
    setBusy(true, "Tworzę i otwieram wersję jawną...", "btnV4Restore");

    const ctx = await readV4DocumentContext({ forcePlaceholderScan: true, timeoutMs: 5000 });
    lastDocumentContext = ctx;
    applyV4ActionAvailability(ctx);
    if (ctx.kind === "restored") {
      setNotice("info", "To już jest wersja jawna. Nie tworzę jej ponownie.");
      return;
    }

    const fallback = canUseLastSavedAnonFallback(ctx);
    if (!fallback.ok) {
      throw new Error(fallback.reason);
    }

    // Prefer the current Office.js package when the active Word document is
    // verifiably *_CSM_anon.docx. That avoids Windows file-lock failures and
    // includes unsaved edits. If Word kept the task pane attached to the original
    // document, this check refuses the active package and falls back to the saved
    // session DOCX that CSM created itself.
    let restoreAttempt = { used: false, reason: "pominięto aktywny pakiet Word" };
    if (ctx.kind === "anon") {
      setNotice("info", "Tworzę wersję jawną z aktualnie otwartego pliku _CSM_anon.docx. Ten tryb omija blokadę pliku na dysku i obejmuje niezapisane zmiany Worda.");
      restoreAttempt = await tryRestoreFromCurrentAnonPackage(ctx, wordAnonPath);
    }

    let data = restoreAttempt.used ? restoreAttempt.data : null;
    if (!data) {
      setNotice("info", `Nie udało się bezpiecznie użyć aktywnego pakietu Word (${restoreAttempt.reason}). Tworzę wersję jawną z zapisanej kopii _CSM_anon.docx z sesji CSM. Jeśli edytowałeś plik roboczy w Wordzie, zapisz go najpierw (Ctrl+S), a potem kliknij ten przycisk ponownie.`);
      data = await restoreFromLastSavedAnonPath({ requireChanges: true, wordAnonPath, wordAnonName: currentDocumentFilename("dokument_CSM_anon.docx") });
      data.restore_source = "saved-session-file";
    }

    await rememberV4Session(data);
    setManualRestoreHint("Restore zakończony. Sprawdź otwartą wersję jawną.");
    setNotice((data.warnings || []).length ? "warn" : "good", buildRestoreSuccessMessage(data));
    setStatus(`v1.6 restore zakończony.
Plik jawny: ${data.restored_path}
Ścieżka anon (JS): ${wordAnonPath || "(nieznana — auto-zamknięcie wyłączone)"}
Mapa: ${data.map_id}
Raport restore: ${data.report_restore_path || "C:\\CSM\\sessions\\...\\report_restore.json"}
Raport: ${JSON.stringify(data.negotiation_report || {}, null, 2)}`);
    // Closing the anon copy is handled server-side via PowerShell COM. Close this
    // pane as soon as the restored document is opened, because the pane belongs to
    // the anon file that Word is about to close.
    closeCsmTaskpaneSoon("zamknięcie pliku anon po restore", 700);
  } catch (error) {
    const msg = error.message || String(error || "nieznany błąd");
    if (error && error.status === 409) {
      setManualRestoreHint("CSM zatrzymał restore, bo zapisany plik _CSM_anon wygląda na niezmienioną kopię bazową. Otwórz panel CSM w zmienionym dokumencie _CSM_anon.docx albo zapisz ten plik i wskaż go ręcznie poniżej.");
    } else {
      setManualRestoreHint("Awaryjnie wskaż zapisany plik *_CSM_anon.docx poniżej i kliknij przycisk ręcznego restore.");
    }
    setNotice("danger", `Nie udało się utworzyć wersji jawnej DOCX: ${msg}

Awaryjnie możesz wskazać ręcznie zapisany plik *_CSM_anon.docx w sekcji poniżej.`);
    setStatus(`Błąd v1.6 restore: ${msg}`, true);
  } finally {
    setBusy(false);
  }
}


async function v4RestoreManualDocxCopy() {
  if (busy) return;
  const file = selectedManualRestoreFile();
  if (!file) {
    setManualRestoreHint("Najpierw wybierz zapisany plik *_CSM_anon.docx z folderu CSM sessions albo z miejsca, w którym zapisał go Word.");
    setNotice("warn", "Nie wybrano pliku. Wskaż ręcznie dokument *_CSM_anon.docx, na którym pracowałeś z Claude.");
    return;
  }
  if (!/\.docx$/i.test(file.name || "")) {
    setNotice("danger", "Wybrany plik nie wygląda na DOCX. Wskaż plik *_CSM_anon.docx.");
    return;
  }
  try {
    if (!await ensureServerReadyForOperation()) {
      setNotice("danger", "Lokalny silnik CSM nie jest gotowy. Uruchom CSM → START, poczekaj na komunikat „gotowy do pracy”, a potem kliknij ręczne przywracanie ponownie.");
      return;
    }
    setBusy(true, "Przywracam wersję jawną z ręcznie wskazanego pliku...", "btnV4RestoreManual");
    setManualRestoreHint(`Czytam plik ${file.name}...`);
    const docxBase64 = await fileToBase64(file);
    const fallbackMapId = lastV4MapId();
    // Capture current doc path before async work so server can close it via COM.
    const wordAnonPath = currentDocumentFullPath();
    const data = await apiPostHeavy("/v4/current/restore", {
      docx_base64: docxBase64,
      filename: file.name || "dokument_CSM_anon.docx",
      open_file: true,
      map_id: fallbackMapId,
      session_id: lastV4SessionId(),
      word_anon_path: wordAnonPath || undefined,
      word_anon_name: file.name || undefined
    });
    await rememberV4Session(data);
    const report = data.restore_report || {};
    const openText = describeOpenResult(data, "restore");
    setManualRestoreHint("Ręczne przywracanie zakończone. Sprawdź otwartą wersję jawną.");
    setNotice((data.warnings || []).length ? "warn" : "good", buildRestoreSuccessMessage(data));
    setStatus(`Ręczny restore v1.6 zakończony.\nPlik źródłowy: ${file.name}\nPlik jawny: ${data.restored_path}\nMapa: ${data.map_id}\nRaport restore: ${data.report_restore_path || "C:\\\\CSM\\\\sessions\\\\...\\\\report_restore.json"}`);
    // Closing the anon copy is handled server-side via PowerShell COM. Close this
    // pane if the manual restore was launched from the anon document.
    closeCsmTaskpaneSoon("zamknięcie pliku anon po ręcznym restore", 700);
  } catch (error) {
    const msg = error.message || String(error || "nieznany błąd");
    setManualRestoreHint("Ręczne przywracanie nie powiodło się. Sprawdź, czy wybrano właściwy plik *_CSM_anon.docx i czy CSM START działa.");
    setNotice("danger", `Nie udało się ręcznie utworzyć wersji jawnej DOCX: ${msg}`);
    setStatus(`Błąd ręcznego restore v1.5: ${msg}`, true);
  } finally {
    setBusy(false);
  }
}

async function mainAction() {
  console.info("[CSM] mainAction: start (serverOk=" + serverOk + ", safeModeActive=" + isSafeModeActive() + ")");
  // Immediate visible acknowledgement — the user must see something change even
  // before slow Office.js calls run. Without this, a slow `isSafeModeActive()`
  // or `documentHasVisiblePlaceholder()` made the button look dead.
  setState("busy", `<span class="spinner"></span>Rozpoczynam...`, "Sprawdzam stan dokumentu.", true);
  setStatus("Klik zarejestrowany. Sprawdzam stan dokumentu...");

  if (isSafeModeActive()) {
    await disableSafeMode();
    return;
  } else if (await documentHasVisiblePlaceholder()) {
    setNotice("warn", "Dokument wygląda na spseudonimizowany, ale tryb bezpieczny nie jest aktywny w ustawieniach. Nie pseudonimizuję ponownie — spróbuję przywrócić wersję jawną z najnowszej lokalnej mapy.");
    await disableSafeMode({ reason: "odzyskiwanie po utracie stanu dokumentu" });
    return;
  }
  if (!serverOk) {
    setStatus("Sprawdzam lokalny silnik i token API przed pseudonimizacją...");
    const ok = await checkServer();
    if (!ok) {
      // Previously a silent `return` here left the user thinking nothing
      // happened. Surface the failure so the next step is obvious.
      setState("danger", "Nie mogę uruchomić pseudonimizacji", "Lokalny silnik CSM jest niedostępny albo token API jest nieprawidłowy. Sprawdź sekcję poniżej.");
      setNotice("danger", "Pseudonimizacja przerwana, bo lokalny silnik nie odpowiedział. Uruchom skrót CSM - START, poczekaj kilka sekund i kliknij ponownie.");
      console.error("[CSM] mainAction: checkServer returned false — aborting");
      return;
    }
  }
  await enableSafeMode();
}

// ─── enableSafeMode ──────────────────────────────────────────────────────────

async function enableSafeMode(options = {}) {
  let operationSucceeded = false;
  const reviewMode = selectedReviewMode(options.reviewMode);
  const reviewLabel = reviewModeLabel(reviewMode);
  try {
    const currentState = readSafeModeSnapshot();
    if (isSafeModeActive()) {
      await refreshDocumentState();
      setNotice("warn", "Tryb Claude jest już włączony dla tego dokumentu. Najpierw przywróć dane albo użyj kopii dokumentu.");
      return;
    }
    await markDocumentMasking({ reason: "prepare-start", sessionId: currentSessionId(), previousState: currentState.state });

    setTrackingConsentControls(false);
    const trackingRisk = await readTrackedChangesRisk();

    setBusy(true, `Przygotowuję dokument dla Claude (${reviewLabel})...`, "btnMain");
    stepState(2, [1]);
    setStatus(`Tworzę pełną kopię awaryjną DOCX w ${mapsDir()}\\..\\backups...`);
    setNotice("info", "Najpierw zapisuję pełną kopię awaryjną oryginalnego dokumentu. Dopiero potem modyfikuję widoczną treść dokumentu.");

    let originalDocxBase64 = "";
    try {
      originalDocxBase64 = await getCompressedDocumentBase64WithTimeout(12000);
    } catch (backupError) {
      throw new Error(`Nie udało się utworzyć pełnej kopii awaryjnej DOCX. Dokument NIE został spseudonimizowany. Zapisz ręcznie kopię dokumentu albo spróbuj ponownie po zapisaniu pliku. Szczegóły: ${backupError.message || backupError}`);
    }
    if (!originalDocxBase64 || originalDocxBase64.length < 1000) {
      throw new Error("Nie udało się utworzyć pełnej kopii awaryjnej DOCX. Dokument NIE został spseudonimizowany.");
    }

    const docxRevisionRisk = await readDocxRevisionRisk(originalDocxBase64);
    if (docxRevisionRisk.unknown) {
      throw new Error(`Nie udało się bezpiecznie sprawdzić pełnego DOCX pod kątem znaczników rewizji (${docxRevisionRisk.error || "brak szczegółów"}). Dokument NIE został zmodyfikowany.`);
    }
    const revisionPreservingMode = Boolean(docxRevisionRisk.hasTracking);
    const trackingActuallyOn = Boolean(trackingRisk.hasTracking && !trackingRisk.unknown);
    if (revisionPreservingMode || trackingRisk.hasTracking || trackingRisk.unknown) {
      const files = (docxRevisionRisk.revisionFiles || []).slice(0, 5);
      const detail = revisionPreservingMode
        ? `W pliku DOCX wykryto znaczniki rewizji w: ${files.join(", ")}${(docxRevisionRisk.revisionFiles || []).length > 5 ? " …" : ""}.`
        : "Nie wykryto znaczników rewizji w pakiecie DOCX, ale tryb śledzenia zmian Word jest włączony albo nieznany.";
      showTrackedChangesPreservationNotice(trackingRisk.mode, detail);
    }

    setStatus(revisionPreservingMode
      ? "Pełna kopia awaryjna jest gotowa. Pseudonimizuję widoczną treść dokumentu z zachowaniem śledzenia zmian..."
      : "Pełna kopia awaryjna jest gotowa. Czytam widoczną treść dokumentu i przygotowuję stabilną pseudonimizację...");
    setNotice("info", revisionPreservingMode
      ? "Dokument zawiera śledzenie zmian. Nie zastępuję całego pliku Word. Maskuję tylko konkretne miejsca tak, aby zachować istniejącą historię zmian i nie tworzyć dodatkowych czerwonych zmian poza tymi miejscami."
      : "Pełny plik Word służy jako kopia awaryjna. Pseudonimizacja widocznej treści działa stabilną ścieżką strukturalną.");

    let data;
    let usedFallback = false;
    let modeKind = "parts";
    let bodyScan = { entities_count: 0, category_counts: {} };
    let partsHadRevisionMarkup = revisionPreservingMode;

    try {
      const beforePartsText = await getDocumentText();
      try {
        bodyScan = await apiPost("/scan", { text: beforePartsText, ...reviewModePayload(reviewMode) });
      } catch (scanError) {
        bodyScan = { entities_count: 0, category_counts: {} };
        setNotice("warn", `Nie udało się wykonać skanu wstępnego widocznej treści (${scanError.message || scanError}). Kontynuuję, ale wynik zostanie dodatkowo zweryfikowany.`);
      }

      const parts = await collectOoxmlParts();
      if (!parts.body || !parts.body.trim()) {
        throw new Error("Dokument nie zwrócił struktury Worda. Przechodzę do trybu tekstowego.");
      }
      partsHadRevisionMarkup = partsHadRevisionMarkup || partsContainRevisionMarkup(parts);
      const requireTrackControl = Boolean(partsHadRevisionMarkup || trackingActuallyOn);
      setStatus(partsHadRevisionMarkup
        ? "Pseudonimizuję wskazane części dokumentu z zachowaniem istniejącego śledzenia zmian..."
        : "Pseudonimizuję widoczną treść dokumentu lokalnie w stabilnym trybie strukturalnym...");
      data = await apiPost("/mask_ooxml_parts", { parts, original_docx_base64: originalDocxBase64, original_text: beforePartsText, ...reviewModePayload(reviewMode) });
      await replaceOoxmlParts(data.parts, {
        requireTrackControl,
        preserveTrackChanges: Boolean(partsHadRevisionMarkup || trackingActuallyOn)
      });
      await verifyVisibleAnonymizationApplied(beforePartsText, data, partsHadRevisionMarkup ? "Tryb strukturalny ze śledzeniem zmian" : "Tryb strukturalny", bodyScan.entities_count || 0);

      if (Number(data.entities_count || 0) === 0 && Number(bodyScan.entities_count || 0) === 0) {
        setNotice("warn", "Nie wykryto danych do pseudonimizacji w widocznej treści. Jeśli dokument zawiera dane w komentarzach, przypisach lub metadanych, sprawdź je ręcznie przed użyciem Claude.");
      }
    } catch (ooxmlError) {
      if (ooxmlError && ooxmlError.status === 401) throw ooxmlError;
      if (revisionPreservingMode || partsHadRevisionMarkup || trackingActuallyOn) {
        usedFallback = true;
        modeKind = "range";
        setStatus(`Tryb strukturalny ze śledzeniem zmian nie został zastosowany przez Word (${ooxmlError.message || ooxmlError}). Próbuję pracy na konkretnych fragmentach Worda — bez zastępowania całej struktury dokumentu.`);
        setNotice("warn", "Dokument ma śledzenie zmian. Podmieniam konkretne znalezione wartości w widocznej treści, zamiast zastępować całe części dokumentu. CSM rozdziela zwykły tekst i miejsca objęte śledzeniem zmian. Po operacji sprawdź komentarze, przypisy, nagłówki, stopki i usunięte fragmenty.");
        const rangeResult = await maskVisibleTextByRange(originalDocxBase64, bodyScan, { requireTrackControl: trackingActuallyOn, reviewMode });
        data = rangeResult.data;
        partsHadRevisionMarkup = true;
      } else {
        usedFallback = true;
        modeKind = "text";
        setStatus(`Tryb strukturalny nie zadziałał (${ooxmlError.message || ooxmlError}). Używam stabilnej pseudonimizacji tekstowej.`);
        setNotice("warn", "Użyto trybu tekstowego. Sprawdź formatowanie dokumentu po operacji.");
        const text = await getDocumentText();
        const textScan = await apiPost("/scan", { text, ...reviewModePayload(reviewMode) });
        data = await apiPost("/mask", { text, original_docx_base64: originalDocxBase64, ...reviewModePayload(reviewMode) });
        await replaceBodyWithText(data.masked_text);
        await verifyVisibleAnonymizationApplied(text, data, "Tryb tekstowy", textScan.entities_count || data.entities_count || 0);
      }
    }

    const finalText = await getDocumentText();
    if (Number((bodyScan && bodyScan.entities_count) || 0) > 0 && !containsClaudeSafePlaceholder(finalText)) {
      throw new Error("Walidacja końcowa nie znalazła placeholderów w widocznej treści mimo wykrycia danych. Dokument NIE został oznaczony jako gotowy dla Claude.");
    }

    const sessionId = currentSessionId();
    await markDocumentMasked({ mapId: data.map_id, sessionId, reason: "masking-complete" });
    const revisionMapPersistence = await persistRevisionMapForCurrentDocument(data.map_id, "anonymize");
    await saveSetting(MODE_KIND_SETTING_KEY, modeKind);
    await setDataClearAfterRestore(false);
    const summary = buildSummary(data);
    summary.revisionMapPersistence = revisionMapPersistence;
    summary.modeKind = modeKind;
    summary.visibleBodyScan = bodyScan;
    summary.packageReport = data.package_report || null;
    summary.revisionPreservingMode = Boolean(partsHadRevisionMarkup || revisionPreservingMode);
    await saveSummary(summary);
    showSummary(summary);

    stepState(3, [1,2]);
    setState("ready", "Dokument gotowy dla Claude", "Przejrzyj wersję z placeholderami. Dopiero potem uruchom Claude for Word.");
    $("btnMain") && $("btnMain").classList.add("hidden");
    $("btnRestore") && ($("btnRestore").textContent = "Przywróć wersję jawną");
    $("btnRestore") && $("btnRestore").classList.remove("hidden");
    $("btnEmergency") && $("btnEmergency").classList.add("hidden");
    const successNotice = modeKind === "range"
      ? "Dokument został przygotowany w eksperymentalnym trybie zakresowym Word dla śledzenia zmian. Placeholdery były podmieniane w dwóch turach: zwykłe wystąpienia przy śledzeniu OFF, a wystąpienia w kontekście rewizji przy śledzeniu ON. Przed uruchomieniem Claude for Word sprawdź placeholdery oraz ręcznie skontroluj komentarze, przypisy, nagłówki, stopki i usunięte rewizje."
      : (modeKind === "parts"
          ? (partsHadRevisionMarkup
              ? "Dokument został przygotowany z zachowaniem istniejącego śledzenia zmian. Przejrzyj oznaczenia przed uruchomieniem Claude for Word."
              : "Dokument został przygotowany w stabilnym trybie strukturalnym. Widoczna treść została zweryfikowana pod kątem obecności oznaczeń.")
          : "Użyto trybu tekstowego. Sprawdź formatowanie i treść przed uruchomieniem Claude for Word.");
    setNotice(usedFallback ? "warn" : "good", successNotice);
    const backupInfo = await backupStatusText(data.map_id);
    setStatus(`Tryb Claude włączony.
Mapa lokalna: ${data.map_id}
${backupInfo}
Wykryto: ${data.entities_count} unikalnych wartości.
${(partsHadRevisionMarkup || revisionPreservingMode) ? "Śledzenie zmian zostało zachowane; aplikacja nie akceptowała ani nie odrzucała zmian.\n" : ""}Po zakończeniu pracy z Claude kliknij „Przywróć wersję jawną".`);
    operationSucceeded = true;
  } catch (e) {
    try { await clearSafeModeSettingsForRetry(); } catch (_) {}
    setState("danger", "Nie udało się przygotować dokumentu", "Dokument nie powinien być używany w Claude, dopóki problem nie zostanie rozwiązany.");
    setNotice("danger", `Błąd przy włączaniu trybu Claude: ${e.message || e}`);
    setStatus(`Błąd przy włączaniu trybu Claude: ${e.message || e}`);
  } finally {
    setBusy(false);
    // Do not refresh the panel after a failed prepare operation.
    if (operationSucceeded && !trackedChangesConsentPending) {
      await refreshDocumentState(false);
    }
  }
}

// ─── disableSafeMode ─────────────────────────────────────────────────────────

async function disableSafeMode(options = {}) {
  const { automatic = false, reason = "ręczne przywracanie" } = options;
  if (restoreInProgress) return;
  restoreInProgress = true;
  let restoreSucceeded = false;
  let restoreNeedsAttention = false;
  let mapId = "";
  try {
    mapId = activeMapId();
    if (!mapId) {
      mapId = await getLatestBackupMapId();
      if (!mapId) {
        setNotice("danger", `Brak mapy podstawień i brak kopii awaryjnej w folderze ${backupFolderLabel("…")}. Nie mogę automatycznie przywrócić danych.`);
        setStatus(`Brak mapy podstawień i brak kopii awaryjnej w ${backupFolderLabel("…")}. Nie mogę automatycznie przywrócić danych.`);
        restoreNeedsAttention = true;
        return;
      }
      setNotice("warn", `Nie znalazłem mapy w ustawieniach dokumentu. Używam najnowszej kopii awaryjnej: ${mapId}.`);
    }

    await beginDocumentRestore(mapId, reason);

    setBusy(true, automatic ? "Automatycznie przywracam dane..." : "Przywracam dane...", "btnRestore");
    stepState(4, [1,2,3]);
    setStatus(`${automatic ? "Automatycznie p" : "P"}rzywracam dane (${reason}). Mapa lokalna: ${mapId}`);
    let usedFallback = false;
    let restoreReport = null;
    let replacementsPayload = [];
    try {
      const restoreMap = await apiPost("/restore", { map_id: mapId });
      replacementsPayload = (restoreMap && restoreMap.replacements) || [];
    } catch (_) {}
    const modeKind = getSetting(MODE_KIND_SETTING_KEY) || "parts";
    let restorePartsHadRevisionMarkup = false;
    const forceStructuralRestore = modeKind === "range" || modeKind === "parts" || modeKind === "package";
    if (forceStructuralRestore) {
      try {
        setStatus(modeKind === "range"
          ? "Przywracam wersję jawną w strukturze dokumentu Word. Nie używam trybu awaryjnego, aby nie odłączyć tekstu od historii zmian."
          : "Przywracam wersję jawną w trybie strukturalnym z zachowaniem istniejącego śledzenia zmian...");
        if (modeKind === "range") {
          setNotice("info", "Pseudonimizacja mogła korzystać z pracy na konkretnych fragmentach, ale przywracanie wykonuję przez strukturę dokumentu. To chroni tekst znajdujący się w śledzeniu zmian przed spłaszczeniem historii zmian.");
        }
        const parts = await collectOoxmlParts();
        restorePartsHadRevisionMarkup = partsContainRevisionMarkup(parts);
        let reportPayload = null;
        try {
          reportPayload = await apiPost("/placeholder_report", { map_id: mapId, parts });
        } catch (_) {}
        if (reportPayload) {
          const pre = reportPayload.placeholder_report || {};
          if (Number(pre.missing_total || 0) > 0 || Number(pre.unknown_total || 0) > 0) {
            setNotice("warn", `Walidacja przed przywróceniem: brakujących placeholderów z mapy: ${pre.missing_total || 0}, nieznanych placeholderów w dokumencie: ${pre.unknown_total || 0}. Przywracam dalej, ale sprawdź dokument.`);
          }
        }
        const trackingRisk = await readTrackedChangesRisk();
        const restoreTrackingOn = Boolean(trackingRisk.hasTracking && !trackingRisk.unknown);
        let _usedOrig1 = false;
        try {
          const _origD = await apiPost("/original_ooxml", { map_id: mapId });
          const _origP = (_origD && _origD.ooxml) ? JSON.parse(_origD.ooxml) : null;
          if (_origP && _origP.body) {
            await replaceOoxmlParts(_origP, {
              requireTrackControl: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "package" || modeKind === "range"),
              preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "package" || modeKind === "range")
            });
            _usedOrig1 = true;
          }
        } catch (_) {}
        if (!_usedOrig1) {
          const data = await apiPost("/restore_ooxml_parts", { map_id: mapId, parts });
          restoreReport = data.restore_report || null;
          await replaceOoxmlParts(data.parts, {
            requireTrackControl: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "package" || modeKind === "range"),
            preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "package" || modeKind === "range")
          });
        }
      } catch (ooxmlError) {
        if (ooxmlError && ooxmlError.status === 401) throw ooxmlError;
        throw new Error(`Bezpieczne przywracanie z zachowaniem śledzenia zmian nie powiodło się. Nie używam awaryjnego trybu tekstowego, żeby nie odłączyć danych od historii zmian. Szczegóły: ${ooxmlError.message || ooxmlError}`);
      }
    } else try {
      const parts = await collectOoxmlParts();
      restorePartsHadRevisionMarkup = partsContainRevisionMarkup(parts);
      let reportPayload = null;
      try {
        reportPayload = await apiPost("/placeholder_report", { map_id: mapId, parts });
      } catch (_) {}
      if (reportPayload) {
        const pre = reportPayload.placeholder_report || {};
        if (Number(pre.missing_total || 0) > 0 || Number(pre.unknown_total || 0) > 0) {
          setNotice("warn", `Walidacja przed przywróceniem: brakujących placeholderów z mapy: ${pre.missing_total || 0}, nieznanych placeholderów w dokumencie: ${pre.unknown_total || 0}. Przywracam dalej, ale sprawdź dokument.`);
        }
      }
      const trackingRisk = await readTrackedChangesRisk();
      const restoreTrackingOn = Boolean(trackingRisk.hasTracking && !trackingRisk.unknown);
      let _usedOrig2 = false;
      try {
        const _origD = await apiPost("/original_ooxml", { map_id: mapId });
        const _origP = (_origD && _origD.ooxml) ? JSON.parse(_origD.ooxml) : null;
        if (_origP && _origP.body) {
          await replaceOoxmlParts(_origP, {
            requireTrackControl: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn),
            preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "range")
          });
          _usedOrig2 = true;
        }
      } catch (_) {}
      if (!_usedOrig2) {
        const data = await apiPost("/restore_ooxml_parts", { map_id: mapId, parts });
        restoreReport = data.restore_report || null;
        await replaceOoxmlParts(data.parts, {
          requireTrackControl: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn),
          preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "range")
        });
      }
    } catch (ooxmlError) {
      if (ooxmlError && ooxmlError.status === 401) throw ooxmlError;
      if (restorePartsHadRevisionMarkup) {
        throw new Error(`Bezpieczne przywracanie z zachowaniem śledzenia zmian nie powiodło się. Nie używam awaryjnego trybu tekstowego, żeby nie naruszyć historii zmian. Szczegóły: ${ooxmlError.message || ooxmlError}`);
      }
      usedFallback = true;
      setStatus(`Tryb strukturalny przy przywracaniu nie zadziałał (${ooxmlError.message || ooxmlError}). Używam awaryjnego przywracania tekstowego.`);
      const restoreData = await apiPost("/restore", { map_id: mapId });
      replacementsPayload = (restoreData && restoreData.replacements) || replacementsPayload;
      let text = await getDocumentText();
      // Bug fix: guard against null/undefined replacements array
      for (const r of (restoreData.replacements || []).slice().sort((a, b) => b.placeholder.length - a.placeholder.length)) {
        text = text.split(r.placeholder).join(r.original);
      }
      await replaceBodyWithText(text);
    }

    let usedVisibleRangeRetry = false;
    let postRestoreHasVisiblePlaceholder = await documentHasVisiblePlaceholder();

    // Word can occasionally acknowledge body.insertOoxml(..., Replace) without
    // actually changing the visible body text in the current task pane session
    // Cache/host timing issue observed in desktop Word; keep backend checks fresh. The backend restore report
    // then looks clean, but the user still sees placeholders. In that case do a
    // narrow, visible-text retry through the Range API with track changes
    // temporarily controlled by the bridge. This is not the primary restore
    // path and it is only attempted after structural OOXML restore failed to
    // affect visible text. It avoids clearing the map until the document text is
    // actually verified as placeholder-free.
    if (postRestoreHasVisiblePlaceholder && !usedFallback && replacementsPayload && replacementsPayload.length) {
      try {
        usedVisibleRangeRetry = true;
        setStatus("Przywracanie strukturalne zostało wykonane, ale Word nadal pokazuje oznaczenia. Wykonuję kontrolowane dogranie widocznej treści, bez czyszczenia mapy do czasu weryfikacji.");
        const retryPairs = buildRangePairs(replacementsPayload, "restore");
        const retryRequireTrackControl = Boolean(restorePartsHadRevisionMarkup || modeKind === "package" || modeKind === "range");
        await applySearchReplacePairs(retryPairs, { requireTrackControl: retryRequireTrackControl, preserveRevisionContext: false });
        postRestoreHasVisiblePlaceholder = await documentHasVisiblePlaceholder();
      } catch (retryError) {
        setStatus(`Przywracanie strukturalne zostało wykonane, ale widoczne oznaczenia pozostały. Kontrolowana dogrywka widocznej treści nie powiodła się: ${retryError.message || retryError}`);
      }
    }

    const unresolvedReport = restoreHasUnresolvedPlaceholders(restoreReport);
    if (postRestoreHasVisiblePlaceholder || unresolvedReport) {
      restoreNeedsAttention = true;
      const reportMessage = usedFallback
        ? "Przywracanie tekstowe nie usunęło wszystkich placeholderów."
        : (usedVisibleRangeRetry
            ? `${restoreReportNotice(restoreReport, replacementsPayload)}

Próba dogrania widocznych oznaczeń nie usunęła ich wszystkich.`
            : restoreReportNotice(restoreReport, replacementsPayload));
      await keepSafeModeActiveAfterFailedRestore(
        mapId,
        `${reportMessage}

Tryb Claude NIE został wyłączony, ponieważ nie potwierdzono pełnego przywrócenia wersji jawnej. Mapa pozostaje aktywna i możesz ponowić przywracanie.`
      );
      return;
    }

    await clearSafeModeSettingsAfterRestore();
    await setDataClearAfterRestore(false);
    stepState(null, [1,2,3,4]);
    setState("warn", "Dokument zawiera jawne dane", "Dane zostały przywrócone. Nie zapisuj go ani nie udostępniaj przed ponowną pseudonimizacją albo świadomym zakończeniem pracy.");
    const reportMessage = usedFallback
      ? "Dane przywrócono awaryjnie tekstowo. Sprawdź formatowanie dokumentu."
      : (usedVisibleRangeRetry
          ? `${restoreReportNotice(restoreReport, replacementsPayload)}

Uwaga: Word nie odświeżył widocznej treści po pierwszym przywróceniu, więc panel wykonał dodatkową kontrolowaną podmianę widocznych oznaczeń z próbą zachowania kontekstu śledzenia zmian.`
          : restoreReportNotice(restoreReport, replacementsPayload));
    setNotice(restoreReportNoticeLevel(restoreReport, usedFallback), `${reportMessage}

${restoredDocumentClearWarningText()}`);
    $("btnMain") && ($("btnMain").textContent = "Przygotuj dla Claude (tryb bezpieczny)");
    $("btnMain") && $("btnMain").classList.remove("hidden");
    $("btnRestore") && $("btnRestore").classList.add("hidden");
    $("btnEmergency") && $("btnEmergency").classList.add("hidden");
    setClearDataAcknowledgementControl(false);
    setStatus(`Tryb Claude wyłączony. Dane przywrócone z mapy: ${mapId}.\nDokument jest teraz w wersji jawnej. Jeśli chcesz kontynuować pracę z Claude, kliknij „Przygotuj dla Claude (tryb bezpieczny)”.\nOperacja została wykonana bez akceptowania ani odrzucania śledzonych zmian.`);
    restoreSucceeded = true;
  } catch (e) {
    restoreNeedsAttention = true;
    if (mapId) {
      await keepSafeModeActiveAfterFailedRestore(
        mapId,
        `Błąd przy przywracaniu danych: ${e.message || e}\n\nNie uruchamiam automatycznie przywracania awaryjnego, aby nie nadpisać zmian w dokumencie. Mapa pozostaje aktywna; możesz ponowić przywracanie albo świadomie użyć kopii awaryjnej w sekcji Zaawansowane.`
      );
    } else {
      setState("danger", "Nie udało się przywrócić danych", "Nie zapisuj dokumentu, dopóki nie rozwiążesz problemu.");
      setNotice("danger", `Nie udało się przywrócić danych: ${e.message || e}`);
      setStatus(`Nie udało się przywrócić danych: ${e.message || e}`);
    }
  } finally {
    restoreInProgress = false;
    setBusy(false);
    if (restoreSucceeded) {
      await refreshDocumentState(false);
    } else if (!restoreNeedsAttention && !isDataClearAfterRestore()) {
      await refreshDocumentState(false);
    } else {
      setClearDataAcknowledgementControl(false);
    }
  }
}

// ─── emergencyRestoreOriginal ────────────────────────────────────────────────

async function emergencyRestoreOriginal() {
  if (restoreInProgress) return;
  restoreInProgress = true;
  try {
    let mapId = activeMapId();
    if (!mapId) {
      mapId = await getLatestBackupMapId();
      if (!mapId) {
        setNotice("danger", `Brak mapy podstawień i brak kopii awaryjnej w folderze ${backupFolderLabel("…")}.`);
        return;
      }
      setNotice("warn", `Używam najnowszej kopii awaryjnej: ${mapId}.`);
    }
    await beginDocumentRestore(mapId, "emergency-restore-original");
    setBusy(true, "Przywracam kopię awaryjną...", "btnEmergency");
    setStatus(`Przywracam oryginalną kopię awaryjną z mapy: ${mapId}. Używam strukturalnej kopii Worda, aby nie zastępować całego pliku i nie spłaszczać historii redakcyjnej.`);
    const data = await apiPost("/original_ooxml", { map_id: mapId });
    let originalPayload = data.ooxml;
    try {
      const parsed = JSON.parse(originalPayload);
      if (parsed && typeof parsed === "object" && parsed.body) {
        await replaceOoxmlParts(parsed);
      } else {
        await replaceBodyWithOoxml(originalPayload);
      }
    } catch (_) {
      await replaceBodyWithOoxml(originalPayload);
    }
    await clearSafeModeSettingsAfterRestore();
    await setDataClearAfterRestore(false);
    stepState(null, [1,2,3,4]);
    setState("warn", "Przywrócono kopię awaryjną — dokument jawny", "Zmiany wykonane na wersji spseudonimizowanej mogły zostać cofnięte. Dokument zawiera prawdziwe dane.");
    setNotice("warn", `Przywrócono oryginalną kopię awaryjną. Sprawdź dokument, bo zmiany merytoryczne wykonane po pseudonimizacji mogły zostać cofnięte.\n\n${restoredDocumentClearWarningText()}`);
    setClearDataAcknowledgementControl(false);
    setStatus(`Przywrócono oryginalną kopię awaryjną z mapy: ${mapId}. Dokument jest teraz w wersji jawnej.`);
  } catch (e) {
    setState("danger", "Nie udało się przywrócić kopii awaryjnej", "Nie zapisuj dokumentu, dopóki nie rozwiążesz problemu.");
    setNotice("danger", `Nie udało się przywrócić kopii awaryjnej: ${e.message || e}`);
    setStatus(`Nie udało się przywrócić kopii awaryjnej: ${e.message || e}`);
  } finally {
    restoreInProgress = false;
    setBusy(false);
    if (!isDataClearAfterRestore()) {
      await refreshDocumentState(false);
    } else {
      setClearDataAcknowledgementControl(false);
    }
  }
}

// ─── refreshDocumentState ────────────────────────────────────────────────────

async function refreshDocumentState(showTech = true) {
  const snapshot = readSafeModeSnapshot();
  const enabled = isSafeModeActive();
  const mapId = snapshot.mapId || "";
  const tracking = await readTrackingModeLabel();
  if (enabled) {
    stepState(3, [1,2]);
    setState("ready", "Dokument jest spseudonimizowany", "Możesz pracować z Claude. Po zakończeniu przywróć wersję jawną.");
    $("btnMain") && $("btnMain").classList.add("hidden");
    $("btnRestore") && ($("btnRestore").textContent = "Przywróć wersję jawną");
    $("btnRestore") && $("btnRestore").classList.remove("hidden");
    $("btnEmergency") && $("btnEmergency").classList.add("hidden");
    setTrackingConsentControls(false);
    setClearDataAcknowledgementControl(false);
    const summary = lastSummary || loadSummary();
    if (summary) showSummary(summary);
    setNotice("warn", "Tryb Claude jest włączony. Nie zapisuj i nie wysyłaj dokumentu jako finalnego, dopóki nie przywrócisz wersji jawnej.");
  } else {
    const clearAfterRestore = isDataClearAfterRestore();
    const docContext = await readV4DocumentContext({ forcePlaceholderScan: false, timeoutMs: 10000 });
    lastDocumentContext = docContext;
    const v4Metadata = docContext.metadata;
    const hasVisiblePlaceholder = docContext.hasVisiblePlaceholder;
    if (docContext.kind === "anon") {
      if (v4Metadata) await rememberV4Session({ map_id: v4Metadata.map_id, session_id: v4Metadata.session_id || v4Metadata.map_id, anon_path: v4Metadata.anon_filename || "" });
      stepState(4, [1,2,3]);
      setState("ready", "Pracujesz na kopii dla Claude", "To jest plik _CSM_anon.docx. Po pracy utwórz wersję jawną.");
      $("btnMain") && $("btnMain").classList.add("hidden");
      $("btnRestore") && $("btnRestore").classList.add("hidden");
      $("btnEmergency") && $("btnEmergency").classList.add("hidden");
      setTrackingConsentControls(false);
      setClearDataAcknowledgementControl(false);
      setNotice("good", "CSM rozpoznał kopię do pracy z Claude. Gdy skończysz pracę w tym pliku, kliknij „Utwórz i otwórz wersję jawną”.");
    } else if (docContext.kind === "restored") {
      stepState(null, [1,2,3,4]);
      setState("ready", "To jest wersja jawna", "Nie twórz wersji jawnej ponownie z pliku _CSM_jawny.docx.");
      $("btnMain") && ($("btnMain").textContent = "Przygotuj dla Claude (tryb bezpieczny)");
      $("btnRestore") && $("btnRestore").classList.add("hidden");
      $("btnEmergency") && $("btnEmergency").classList.add("hidden");
      setTrackingConsentControls(false);
      setClearDataAcknowledgementControl(false);
      setNotice("good", "Dokument jest już wersją jawną. Jeśli chcesz ponownie pracować z Claude, utwórz nową kopię do Claude z tego jawnego pliku.");
    } else if (clearAfterRestore && !hasVisiblePlaceholder) {
      stepState(2, [1,2,3,4]);
      setState("warn", "Dokument zawiera jawne dane", "Dane zostały przywrócone. Nie zapisuj go ani nie udostępniaj przed ponowną pseudonimizacją albo świadomym zakończeniem pracy.");
      $("btnMain") && ($("btnMain").textContent = "Przygotuj dla Claude (tryb bezpieczny)");
      $("btnRestore") && $("btnRestore").classList.add("hidden");
      $("btnEmergency") && $("btnEmergency").classList.add("hidden");
      setTrackingConsentControls(false);
      setClearDataAcknowledgementControl(false);
      setNotice("warn", restoredDocumentClearWarningText());
    } else if (hasVisiblePlaceholder) {
      stepState(4, [1,2,3]);
      setState("warn", "Dokument wygląda na spseudonimizowany", "Nie widzę aktywnej mapy w ustawieniach dokumentu. Spróbuję przywrócić wersję jawną z najnowszej lokalnej mapy.");
      $("btnMain") && ($("btnMain").textContent = "Przywróć wersję jawną");
      $("btnMain") && $("btnMain").classList.remove("hidden");
      $("btnRestore") && $("btnRestore").classList.add("hidden");
      $("btnEmergency") && $("btnEmergency").classList.remove("hidden");
      setTrackingConsentControls(false);
      setClearDataAcknowledgementControl(false);
      setNotice("warn", `W treści widać placeholdery, ale tryb Claude nie jest aktywny w ustawieniach dokumentu. Nie uruchamiaj przygotowania ponownie. Kliknij „Przywróć wersję jawną" — panel użyje najnowszej lokalnej mapy z ${backupFolderLabel("…")}, jeśli mapa z dokumentu zniknęła.`);
    } else {
      stepState(serverOk ? 2 : 1, serverOk ? [1] : []);
      setState(serverOk ? "ready" : "warn", serverOk ? "Gotowe do pracy z CSM" : "Najpierw uruchom silnik lokalny", serverOk ? "Użyj trybu negocjacyjnego DOCX powyżej." : "Uruchom CSM - START i sprawdź połączenie.");
      $("btnMain") && ($("btnMain").textContent = serverOk ? "Przygotuj aktywny dokument (tryb szybki)" : "Sprawdź i pseudonimizuj");
      $("btnRestore") && $("btnRestore").classList.add("hidden");
      $("btnEmergency") && $("btnEmergency").classList.add("hidden");
      setTrackingConsentControls(false);
      setClearDataAcknowledgementControl(false);
      setNotice(serverOk ? "info" : "warn", serverOk ? "Zalecana ścieżka to tryb negocjacyjny DOCX powyżej. Tryb szybki jest dostępny wyłącznie w diagnostyce." : "Lokalny silnik nie został jeszcze potwierdzony.");
    }
  }
  applyV4ActionAvailability(lastDocumentContext);
  if (showTech) {
    setStatus(`Status dokumentu: ${enabled ? "tryb Claude aktywny" : "tryb Claude wyłączony"}
Stan v3: ${snapshot.state || "brak"}
Mapa: ${mapId || "brak"}
Silnik lokalny: ${serverOk ? "ok" : "niepotwierdzony"}
Śledzenie zmian Word: ${tracking}
Folder map: ${mapsDir()}
Folder backups: ${installPaths.backups || "(katalog instalacji)\\backups"}`);
  }
}

// ─── Technical status ────────────────────────────────────────────────────────

function _updateBielikBadge(nlp) {
  // Sticky: once Bielik is confirmed reachable it stays ON even on transient
  // health check failures (Ollama busy, brief timeout).  Only an explicit
  // bielik_enabled=false resets the sticky flag.
  if (nlp && nlp.bielik_enabled && nlp.bielik_reachable) {
    GBielikConfirmedOn = true;
  } else if (nlp && !nlp.bielik_enabled) {
    GBielikConfirmedOn = false;  // Ollama uninstalled / CSMW_ENABLE_BIELIK cleared
  }
  const effectivelyOn = GBielikConfirmedOn && nlp && nlp.bielik_enabled;

  // small badge in "Kontrola działania"
  const el = document.getElementById("bielikStatusBadge");
  if (el) {
    if (!nlp) { el.textContent = ""; el.className = "bielik-badge bielik-unknown"; }
    else if (!nlp.bielik_enabled) { el.textContent = "Bielik niedostępny"; el.className = "bielik-badge bielik-off"; el.title = "Standardowa anonimizacja działa. Głębokie sprawdzenie AI wymaga lokalnego modelu Bielik/Ollama."; }
    else if (effectivelyOn) { el.textContent = "Bielik dostępny"; el.className = "bielik-badge bielik-on"; el.title = "Możesz uruchomić głębsze sprawdzenie lokalnym modelem AI."; }
    else { el.textContent = "Bielik uruchamia się"; el.className = "bielik-badge bielik-warn"; el.title = "Lokalny model jeszcze nie odpowiedział. Standardowa anonimizacja działa bez Bielika."; }
  }
  // header indicator (green/red dot — always visible)
  const ind = document.getElementById("bielikIndicator");
  if (!ind) return;
  const label = ind.querySelector(".bielik-label");
  if (!nlp) {
    ind.className = "bielik-indicator bielik-checking";
    if (label) label.textContent = " Bielik";
  } else if (effectivelyOn) {
    ind.className = "bielik-indicator bielik-on";
    if (label) label.textContent = " Bielik";
    ind.title = "Bielik dostępny";
  } else if (nlp.bielik_enabled) {
    // enabled but not yet reachable — show as checking, not OFF
    ind.className = "bielik-indicator bielik-checking";
    if (label) label.textContent = " Bielik";
    ind.title = "Bielik uruchamia się";
  } else {
    ind.className = "bielik-indicator bielik-off";
    if (label) label.textContent = " Bielik";
    ind.title = "Bielik niedostępny";
  }
  // panel status text
  const ps = document.getElementById("bielikPanelStatus");
  if (ps && nlp) {
    if (effectivelyOn) {
      ps.textContent = "Bielik dostępny. Możesz uruchomić głębsze sprawdzenie lokalnym modelem AI.";
      ps.style.color = "var(--green)";
    } else if (nlp.bielik_enabled) {
      ps.textContent = "Bielik uruchamia się. Lokalny model jeszcze nie odpowiedział. Standardowa anonimizacja działa bez Bielika.";
      ps.style.color = "#92400e";
    } else {
      ps.textContent = "Bielik niedostępny. Możesz nadal użyć standardowej anonimizacji.";
      ps.style.color = "var(--muted)";
    }
  }
}

async function showTechnicalStatus() {
  const snapshot = readSafeModeSnapshot();
  const enabled = isSafeModeActive();
  const summary = lastSummary || loadSummary();
  const sidecar = await checkRevisionSidecarStatus({ show: false });
  const sidecarText = sidecar ? formatRevisionSidecarStatus(sidecar) : `Mechanizm zachowania śledzenia zmian: nie sprawdzono (${(lastRevisionSidecarStatus && lastRevisionSidecarStatus.error) || "brak danych"})`;
  const nlp = lastHealth && lastHealth.nlp;
  const bielikText = nlp
    ? `Bielik AI: ${nlp.bielik_enabled ? (nlp.bielik_reachable ? "włączony i osiągalny" : "włączony, Ollama niedostępna") : "wyłączony (CSMW_ENABLE_BIELIK≠1)"}`
    : "Bielik AI: nie sprawdzono";
  setStatus(`Wersja panelu: ${APP_VERSION}
API: ${lastHealth ? JSON.stringify(lastHealth) : "nie sprawdzono"}
Moduł state-machine.js: ${stateMachine() ? "aktywny" : "fallback legacy"}
Moduł word-bridge.js: ${wordBridge() ? "aktywny" : "niedostępny — błąd!"}
Moduł revision_bridge.js: ${revisionBridge() ? "aktywny" : "niedostępny"}
Stan v3: ${snapshot.state || "brak"}
Tryb bezpiecznej kopii: ${enabled}
Mapa: ${snapshot.mapId || "brak"}
Tryb techniczny: ${getSetting(MODE_KIND_SETTING_KEY) || "brak"}
Sesja: ${snapshot.sessionId || "brak"}
Ostatnia tranzycja v3: ${snapshot.lastTransition || "brak"}
Folder map: ${mapsDir()}
Folder backups: ${installPaths.backups || "(katalog instalacji)\\backups"}
${bielikText}
${sidecarText}
Ostatnie podsumowanie: ${summary ? JSON.stringify(summary, null, 2) : "brak"}`);
}

// ─── Auto-restore guards ─────────────────────────────────────────────────────

function armAutoRestoreGuards() {
  async function tryAutoRestore(reason) {
    if (autoRestoreAttempted || restoreInProgress) return;
    if (!isSafeModeActive()) return;
    autoRestoreAttempted = true;
    try {
      await disableSafeMode({ automatic: true, reason });
    } catch (_) {}
  }
  window.addEventListener("beforeunload", (event) => {
    try {
      if (isSafeModeActive()) {
        tryAutoRestore("zamykanie panelu lub Worda");
        event.preventDefault();
        event.returnValue = "Dokument jest spseudonimizowany. Przed zamknięciem przywróć dane albo świadomie zapisz wersję spseudonimizowaną.";
        return event.returnValue;
      }
      if (isDataClearAfterRestore()) {
        event.preventDefault();
        event.returnValue = "Dokument zawiera jawne dane po przywróceniu. Czy na pewno chcesz zamknąć bez ponownej pseudonimizacji?";
        return event.returnValue;
      }
    } catch (_) {}
  });
  window.addEventListener("pagehide", () => { tryAutoRestore("zamykanie panelu lub Worda"); });
}

async function recoverIfPreviousSessionWasLeftMasked() {
  const snapshot = readSafeModeSnapshot();
  const savedSessionId = snapshot.sessionId || "";
  const thisSessionId = currentSessionId();
  if (isSafeModeActive() && savedSessionId && savedSessionId !== thisSessionId) {
    setState("warn", "Dokument był pozostawiony w trybie Claude", "Za chwilę spróbuję automatycznie przywrócić dane.");
    setNotice("warn", "Ten dokument wygląda na pozostawiony w trybie Claude po poprzedniej sesji. Za 3 sekundy spróbuję automatycznie przywrócić dane.");
    setTimeout(() => {
      if (isSafeModeActive()) {
        disableSafeMode({ automatic: true, reason: "odzyskiwanie po ponownym otwarciu dokumentu" });
      }
    }, 3000);
  }
}

// ─── DOM readiness guard ─────────────────────────────────────────────────────

function waitForDomReady() {
  if (document.readyState === "interactive" || document.readyState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    document.addEventListener("DOMContentLoaded", resolve, { once: true });
  });
}

function bindButtonsWhenDomReady() {
  return waitForDomReady().then(() => {
    const ok = bindButtons();
    if (!ok) {
      setStatus("Panel załadowany, ale elementy interfejsu nie były jeszcze gotowe. Ponawiam wiązanie przycisków...");
      setTimeout(() => { try { bindButtons(); } catch (error) { reportPanelError(error, "bindButtons retry"); } }, 250);
    }
    return ok;
  });
}

function showOfficeNotReadyDiagnostic() {
  const titleEl = document.getElementById("stateTitle");
  const descEl = document.getElementById("stateDesc");
  const dot = document.getElementById("stateDot");
  const status = document.getElementById("status");
  const notices = document.getElementById("notices");
  if (titleEl) titleEl.textContent = "Office.js nie jest gotowe";
  if (descEl) descEl.textContent = "Panel HTML działa, ale host Office nie udostępnił API. Zamknij panel i uruchom ponownie Worda.";
  if (dot) dot.className = "dot danger";
  if (status) status.textContent = "Office.js / Office.onReady nie jest dostępne. Użyj CSM-CLEAN, potem otwórz Worda i panel ponownie. Jeśli błąd wraca, sprawdź DevTools → Console.";
  if (notices) notices.innerHTML = `<div class="notice danger">Panel zarejestrował kliknięcie, ale Office.js nie jest gotowe. To problem ładowania hosta Word/Office, nie działania silnika pseudonimizacji.</div>`;
}

// ─── Initialization ──────────────────────────────────────────────────────────

console.info(`[CSM] taskpane.js loaded, version ${APP_VERSION}. Waiting for Office.onReady...`);

// Expose handlers before calling Office.onReady. If Office.js fails to initialize,
// inline/fallback bindings can still show a visible diagnostic instead of making
// the button look dead.
window.mainAction = mainAction;
window.checkServer = checkServer;
window.disableSafeMode = disableSafeMode;
window.emergencyRestoreOriginal = emergencyRestoreOriginal;
window.refreshDocumentState = refreshDocumentState;
window.showTechnicalStatus = showTechnicalStatus;
window.v4PrepareDocxCopy = v4PrepareDocxCopy;
window.v4RestoreDocxCopy = v4RestoreDocxCopy;
window.v4RestoreManualDocxCopy = v4RestoreManualDocxCopy;
window.copyAnonymizationReport = copyAnonymizationReport;
window.downloadAnonymizationReport = downloadAnonymizationReport;
window.previewCurrentMap = previewCurrentMap;
window.remaskWithManualControls = remaskWithManualControls;
window.CSM_bindButtons = bindButtonsWhenDomReady;
window.CSM_handleMainClick = async function CSM_handleMainClick(event) {
  if (event) {
    try { event.preventDefault(); event.stopPropagation(); } catch (_) {}
  }
  const btn = document.getElementById("btnMain");
  if (btn) btn.classList.add("is-pressing");
  try {
    console.info("[CSM] fallback click: btnMain");
    await mainAction(event);
  } catch (error) {
    console.error("[CSM] fallback click error:", error);
    reportPanelError(error, "btnMain fallback");
  } finally {
    if (btn) btn.classList.remove("is-pressing");
  }
};

waitForDomReady().then(() => {
  try {
    bindButtons();
    const earlyStatus = document.getElementById("status");
    if (earlyStatus) earlyStatus.textContent = `Skrypt panelu v${APP_VERSION} wczytany. Czekam na Office.onReady...`;
  } catch (error) {
    reportPanelError(error, "early bindButtons");
  }
});

let _csmOfficeReady = false;
setTimeout(() => {
  if (_csmOfficeReady) return;
  const titleEl = document.getElementById("stateTitle");
  const descEl = document.getElementById("stateDesc");
  const dot = document.getElementById("stateDot");
  const status = document.getElementById("status");
  const notices = document.getElementById("notices");
  if (titleEl) titleEl.textContent = "Office.onReady nie wystartowało";
  if (descEl) descEl.textContent = "Panel załadował JS, ale host Office nie zgłosił gotowości w 8 sekund.";
  if (dot) dot.className = "dot danger";
  if (status) status.textContent = "Office.onReady() nie wywołane w 8s. Zamknij panel, uruchom CSM-CLEAN albo CSM → STOP i CSM → START, potem otwórz panel ponownie. Sprawdź F12 → Console pod kątem błędów ładowania office.js.";
  if (notices) notices.innerHTML = `<div class="notice danger">Office.onReady nie wywołało się w 8 sekund. Najczęstsza przyczyna: blokada certyfikatu localhost, cache Worda albo problem z office.js. Kliknięcie przycisku pokaże diagnostykę zamiast milczeć.</div>`;
  console.error("[CSM] Office.onReady did not fire within 8s — likely office.js failed to load or the host blocked it.");
}, 8000);

// ── Service panel (launcher integration) ─────────────────────────────────────

/**
 * Call a service endpoint (POST /service/*).
 * Shows svcStatus feedback; does NOT set global busy state so the main panel
 * remains usable.
 */
async function callServiceEndpoint(path, label) {
  const svcStatus = $("svcStatus");
  if (svcStatus) svcStatus.textContent = `${label}…`;
  try {
    const result = await apiPostService(path, {}, 6000);
    if (svcStatus) svcStatus.textContent = `${label}: OK. Jeśli pojawi się okno PowerShell, zostaw je do zakończenia pracy.`;
    setNotice("good", `${label}: polecenie przyjęte przez lokalny silnik CSM.`);
    return result;
  } catch (err) {
    const message = err.message || String(err);
    if (svcStatus) svcStatus.textContent = `${label}: nie wykonano — ${message}`;
    setNotice("warn", `${label}: ${message}`);
    return null;
  }
}

async function svcStart() {
  await callServiceEndpoint("/service/start", "START");
}

async function svcStop() {
  await callServiceEndpoint("/service/stop", "STOP");
}

async function svcRepair() {
  await callServiceEndpoint("/service/repair", "NAPRAW");
}

// window.confirm() is unreliable in Office add-in WebView2 — it silently
// returns false without showing any dialog. Use inline HTML confirmation instead.
function _svcInlineConfirm(statusElId, message, onConfirm) {
  const el = $(statusElId);
  if (!el) { onConfirm(); return; }
  el.innerHTML =
    '<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:10px;margin-top:4px">' +
    '<div style="font-size:12px;font-weight:700;color:#991b1b;margin-bottom:8px">' + message + '</div>' +
    '<div style="display:flex;gap:8px">' +
    '<button id="_svcYes" style="flex:1;padding:7px;border-radius:8px;border:0;background:#dc2626;color:#fff;font-size:12px;font-weight:700;cursor:pointer">Tak, kontynuuj</button>' +
    '<button id="_svcNo"  style="flex:1;padding:7px;border-radius:8px;border:1px solid #e5e7eb;background:#fff;font-size:12px;cursor:pointer">Anuluj</button>' +
    '</div></div>';
  const yes = document.getElementById("_svcYes");
  const no  = document.getElementById("_svcNo");
  if (yes) yes.onclick = () => { el.innerHTML = ""; onConfirm(); };
  if (no)  no.onclick  = () => { el.textContent = "Anulowano."; };
}

async function svcClean() {
  _svcInlineConfirm("svcStatus",
    "⚠ CLEAN zamknie Microsoft Word. Zapisz otwarte dokumenty przed kontynuacją.",
    () => callServiceEndpoint("/service/clean", "CLEAN")
  );
}

async function svcUninstall() {
  _svcInlineConfirm("svcStatus",
    "⚠ ODINSTALUJ: zatrzyma usługę, usunie CSM z Worda, usunie skróty i zamknie Word. " +
    "Dane sesji w C:\\CSM\\sessions pozostaną.",
    () => callServiceEndpoint("/service/uninstall", "ODINSTALUJ")
  );
}

async function svcDiagnose() {
  const logEl = $("svcLog");
  const svcStatus = $("svcStatus");
  if (!logEl) return;
  logEl.classList.remove("hidden");
  logEl.textContent = "Uruchamiam diagnozę…\n";
  if (svcStatus) svcStatus.textContent = "DIAGNOZA w toku…";

  await loadRuntimeTokenFresh();
  const token = (window.CSM_TOKEN || "").trim();
  const url = `${activeApiBase}/service/diagnose`;

  // Use fetch + ReadableStream (works in WebView2 / modern Office browsers).
  // EventSource doesn't support custom headers; we use fetch with streaming instead.
  try {
    const resp = await fetch(url, {
      headers: {
        "X-CSM-Token": token,
        "Accept": "text/event-stream",
      }
    });
    if (!resp.ok) {
      logEl.textContent += `\n[HTTP ${resp.status}]`;
      if (svcStatus) svcStatus.textContent = `DIAGNOZA: błąd HTTP ${resp.status}`;
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // Parse SSE lines: "data: <text>\n\n"
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const text = line.slice(6);
        if (text === "__END__") {
          if (svcStatus) svcStatus.textContent = "DIAGNOZA zakończona.";
          return;
        }
        logEl.textContent += text + "\n";
        logEl.scrollTop = logEl.scrollHeight;
      }
    }
    if (svcStatus) svcStatus.textContent = "DIAGNOZA zakończona.";
  } catch (err) {
    logEl.textContent += `\n[BŁĄD: ${err.message || err}]`;
    if (svcStatus) svcStatus.textContent = "DIAGNOZA: błąd połączenia.";
  }
}

function bindServicePanel() {
  bindButton("btnSvcStart",      svcStart);
  bindButton("btnSvcStop",       svcStop);
  bindButton("btnSvcRepair",     svcRepair);
  bindButton("btnSvcClean",      svcClean);
  bindButton("btnSvcDiagnose",   svcDiagnose);
  bindButton("btnSvcUninstall",  svcUninstall);
}

if (window.Office && typeof Office.onReady === "function") {
  Office.onReady(async () => {
    _csmOfficeReady = true;
    console.info("[CSM] Office.onReady fired");
    try {
      await bindButtonsWhenDomReady();
      await ensureDocumentStateReady();
      armAutoRestoreGuards();
      setState("warn", "Sprawdzam lokalny silnik", "Jeśli silnik nie działa, kliknij skrót CSM - START.");
      stepState(1, []);
      setNotice("info", "Najbezpieczniej pracuj na kopii dokumentu. Panel nie wysyła mapy podstawień do Claude.");
      setStatus(`Panel v${APP_VERSION} załadowany. Sprawdzam lokalny silnik i token API...`);
      await checkServer();
      await recoverIfPreviousSessionWasLeftMasked();
    } catch (error) {
      reportPanelError(error, "Office.onReady");
    }
  });
} else {
  console.error("[CSM] Office.onReady unavailable at taskpane startup");
  waitForDomReady().then(() => {
    try {
      bindButtons();
      showOfficeNotReadyDiagnostic();
    } catch (error) {
      reportPanelError(error, "Office unavailable");
    }
  });
}
