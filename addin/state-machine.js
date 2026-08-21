(function (root) {
  "use strict";

  const CSM_STATE_V3 = "CSM_STATE_V3";
  const CSM_MAP_ID_V3 = "CSM_MAP_ID_V3";
  const CSM_SESSION_ID_V3 = "CSM_SESSION_ID_V3";
  const CSM_LAST_TRANSITION_V3 = "CSM_LAST_TRANSITION_V3";
  const CSM_BACKUP_PATH_V3 = "CSM_BACKUP_PATH_V3";

  const CSM_STATES = Object.freeze({
    CLEAN: "CLEAN",
    MASKING: "MASKING",
    MASKED: "MASKED",
    RESTORING: "RESTORING",
    RESTORED: "RESTORED",
    ERROR: "ERROR"
  });

  const CSM_ALLOWED_TRANSITIONS = Object.freeze({
    CLEAN: Object.freeze(["CLEAN", "MASKING", "ERROR"]),
    MASKING: Object.freeze(["CLEAN", "MASKED", "ERROR"]),
    MASKED: Object.freeze(["MASKED", "RESTORING", "ERROR"]),
    RESTORING: Object.freeze(["MASKED", "RESTORED", "ERROR"]),
    RESTORED: Object.freeze(["CLEAN", "MASKING", "ERROR"]),
    ERROR: Object.freeze(["CLEAN", "MASKING", "MASKED", "RESTORING", "RESTORED", "ERROR"])
  });

  const CSM_STATE_KEYS = Object.freeze({
    state: CSM_STATE_V3,
    mapId: CSM_MAP_ID_V3,
    sessionId: CSM_SESSION_ID_V3,
    lastTransition: CSM_LAST_TRANSITION_V3,
    backupPath: CSM_BACKUP_PATH_V3
  });

  function nowIso() {
    return new Date().toISOString();
  }

  function requireOfficeSettings() {
    const office = root.Office;
    if (!office || !office.context || !office.context.document || !office.context.document.settings) {
      throw new Error("Office.context.document.settings is unavailable.");
    }
    return office.context.document.settings;
  }

  function normalizeState(value) {
    const raw = String(value || "").trim().toUpperCase();
    return Object.prototype.hasOwnProperty.call(CSM_STATES, raw) ? raw : CSM_STATES.CLEAN;
  }

  function readSetting(settings, key) {
    const value = settings.get(key);
    return value == null ? "" : String(value);
  }

  function readStateSnapshot() {
    const settings = requireOfficeSettings();
    const state = normalizeState(readSetting(settings, CSM_STATE_V3));
    return Object.freeze({
      state,
      mapId: readSetting(settings, CSM_MAP_ID_V3),
      sessionId: readSetting(settings, CSM_SESSION_ID_V3),
      lastTransition: readSetting(settings, CSM_LAST_TRANSITION_V3),
      backupPath: readSetting(settings, CSM_BACKUP_PATH_V3),
      isClean: state === CSM_STATES.CLEAN,
      isMasked: state === CSM_STATES.MASKED,
      isBusy: state === CSM_STATES.MASKING || state === CSM_STATES.RESTORING
    });
  }

  function saveSettingsAsync() {
    const settings = requireOfficeSettings();
    const office = root.Office || {};
    return new Promise((resolve, reject) => {
      settings.saveAsync((result) => {
        const succeeded = office.AsyncResultStatus && result && result.status === office.AsyncResultStatus.Succeeded;
        if (succeeded || (result && result.status === "succeeded")) {
          resolve(readStateSnapshot());
          return;
        }
        reject((result && result.error) || new Error("Could not save CSM v3 document state."));
      });
    });
  }

  function transitionAllowed(fromState, toState) {
    const from = normalizeState(fromState);
    const to = normalizeState(toState);
    const allowed = CSM_ALLOWED_TRANSITIONS[from] || [];
    return allowed.indexOf(to) >= 0;
  }

  function writeSnapshotFields(settings, nextState, fields) {
    settings.set(CSM_STATE_V3, normalizeState(nextState));
    settings.set(CSM_MAP_ID_V3, fields.mapId || "");
    settings.set(CSM_SESSION_ID_V3, fields.sessionId || "");
    settings.set(CSM_BACKUP_PATH_V3, fields.backupPath || "");
    settings.set(CSM_LAST_TRANSITION_V3, JSON.stringify(fields.lastTransition));
  }

  async function transitionTo(nextState, metadata) {
    const settings = requireOfficeSettings();
    const before = readStateSnapshot();
    const to = normalizeState(nextState);
    if (!transitionAllowed(before.state, to)) {
      throw new Error(`Invalid CSM v3 state transition: ${before.state} -> ${to}`);
    }

    const meta = metadata || {};
    const keep = meta.keepExisting === true;
    const fields = {
      mapId: Object.prototype.hasOwnProperty.call(meta, "mapId") ? String(meta.mapId || "") : (keep ? before.mapId : ""),
      sessionId: Object.prototype.hasOwnProperty.call(meta, "sessionId") ? String(meta.sessionId || "") : (keep ? before.sessionId : ""),
      backupPath: Object.prototype.hasOwnProperty.call(meta, "backupPath") ? String(meta.backupPath || "") : (keep ? before.backupPath : ""),
      lastTransition: {
        at: meta.at || nowIso(),
        from: before.state,
        to,
        reason: meta.reason || "",
        mapId: Object.prototype.hasOwnProperty.call(meta, "mapId") ? String(meta.mapId || "") : before.mapId,
        sessionId: Object.prototype.hasOwnProperty.call(meta, "sessionId") ? String(meta.sessionId || "") : before.sessionId,
        backupPath: Object.prototype.hasOwnProperty.call(meta, "backupPath") ? String(meta.backupPath || "") : before.backupPath
      }
    };

    if (to === CSM_STATES.MASKED && !fields.mapId) {
      throw new Error("CSM v3 MASKED state requires a mapId.");
    }
    if (to === CSM_STATES.RESTORING && !fields.mapId) {
      fields.mapId = before.mapId;
    }

    writeSnapshotFields(settings, to, fields);
    return saveSettingsAsync();
  }

  function ensureCleanState() {
    const snapshot = readStateSnapshot();
    if (snapshot.state !== CSM_STATES.CLEAN) return Promise.resolve(snapshot);
    if (snapshot.lastTransition) return Promise.resolve(snapshot);
    const settings = requireOfficeSettings();
    writeSnapshotFields(settings, CSM_STATES.CLEAN, {
      mapId: "",
      sessionId: "",
      backupPath: "",
      lastTransition: { at: nowIso(), from: CSM_STATES.CLEAN, to: CSM_STATES.CLEAN, reason: "init" }
    });
    return saveSettingsAsync();
  }

  function markClean(reason) {
    return transitionTo(CSM_STATES.CLEAN, { reason: reason || "clean" });
  }

  function markMasking(metadata) {
    const meta = Object.assign({ reason: "masking-start" }, metadata || {});
    return transitionTo(CSM_STATES.MASKING, meta);
  }

  function markMasked(metadata) {
    const meta = Object.assign({ reason: "masking-complete" }, metadata || {});
    return transitionTo(CSM_STATES.MASKED, meta);
  }

  function markRestoring(metadata) {
    const meta = Object.assign({ reason: "restore-start", keepExisting: true }, metadata || {});
    return transitionTo(CSM_STATES.RESTORING, meta);
  }

  function markRestored(metadata) {
    const meta = Object.assign({ reason: "restore-complete" }, metadata || {});
    return transitionTo(CSM_STATES.RESTORED, meta);
  }

  function markError(metadata) {
    const meta = Object.assign({ reason: "error", keepExisting: true }, metadata || {});
    return transitionTo(CSM_STATES.ERROR, meta);
  }

  const CSMStateMachine = Object.freeze({
    keys: CSM_STATE_KEYS,
    states: CSM_STATES,
    allowedTransitions: CSM_ALLOWED_TRANSITIONS,
    normalizeState,
    readStateSnapshot,
    transitionAllowed,
    transitionTo,
    ensureCleanState,
    markClean,
    markMasking,
    markMasked,
    markRestoring,
    markRestored,
    markError
  });

  root.CSMStateMachine = CSMStateMachine;
  if (typeof module !== "undefined" && module.exports) module.exports = CSMStateMachine;
})(typeof globalThis !== "undefined" ? globalThis : window);
