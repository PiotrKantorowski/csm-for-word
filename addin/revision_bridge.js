(function (root) {
  "use strict";

  const ANCHOR_PREFIX = "CSM_ANCHOR:";
  const MAP_NAMESPACE = "https://skills.kancelariakantorowski.pl/csm/revision-map/1";
  const MAP_SCHEMA_VERSION = "0.5.2-revision-map";
  const MAP_ENGINE_VERSION = "0.5.2-revision-plan";
  const MAP_SETTING_KEYS = Object.freeze({
    partId: "CSM_RevisionMapPartId",
    mapId: "CSM_RevisionMapId",
    schemaVersion: "CSM_RevisionMapSchemaVersion",
    engineVersion: "CSM_RevisionEngineVersion",
    namespace: "CSM_RevisionMapNamespace"
  });

  function requireWord() {
    if (!root.Word || !root.Word.run) throw new Error("Word JavaScript API is unavailable.");
    return root.Word;
  }

  function randomId() {
    const cryptoObj = root.crypto || root.msCrypto;
    if (cryptoObj && cryptoObj.randomUUID) return cryptoObj.randomUUID();
    if (cryptoObj && cryptoObj.getRandomValues) {
      const bytes = new Uint8Array(16);
      cryptoObj.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
      return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function makeAnchorId(id) {
    const suffix = String(id || randomId()).replace(/[^A-Za-z0-9_.:-]/g, "");
    return suffix.startsWith(ANCHOR_PREFIX) ? suffix : `${ANCHOR_PREFIX}${suffix}`;
  }

  function escapeXml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");
  }

  function normalizeAnchor(anchor) {
    const a = anchor || {};
    return {
      anchorId: String(a.anchorId || a.anchor_id || ""),
      entityId: String(a.entityId || a.entity_id || ""),
      entityType: String(a.entityType || a.entity_type || ""),
      originalText: String(a.originalText || a.original_text || ""),
      currentText: String(a.currentText || a.current_text || a.text || ""),
      trackedChangeCount: Number(a.trackedChangeCount || a.tracked_change_count || 0),
      changeTrackingMode: String(a.changeTrackingMode || a.change_tracking_mode || "unknown"),
      sourcePart: String(a.sourcePart || a.source_part || a.documentPart || a.document_part || "body"),
      paragraphId: String(a.paragraphId || a.paragraph_id || a.paragraph || ""),
      originalOoxmlPresent: Boolean(a.originalOoxmlPresent || a.original_ooxml_present || a.originalOoxml || a.original_ooxml || a.selectionOoxml || a.selection_ooxml),
      reviewedOriginalPresent: Boolean(a.reviewedOriginalPresent || a.reviewed_original_present || a.reviewedOriginal || a.reviewed_original || a.originalText || a.original_text),
      reviewedCurrentPresent: Boolean(a.reviewedCurrentPresent || a.reviewed_current_present || a.reviewedCurrent || a.reviewed_current || a.currentText || a.current_text || a.text)
    };
  }

  function buildRevisionMapXml(payload) {
    const data = payload || {};
    const anchors = Array.isArray(data.anchors) ? data.anchors.map(normalizeAnchor) : [];
    const operations = Array.isArray(data.operations) ? data.operations : [];
    const attrs = [
      `xmlns:csm="${escapeXml(MAP_NAMESPACE)}"`,
      `schemaVersion="${escapeXml(data.schemaVersion || data.schema_version || MAP_SCHEMA_VERSION)}"`,
      `engineVersion="${escapeXml(data.engineVersion || data.engine_version || MAP_ENGINE_VERSION)}"`,
      `mapId="${escapeXml(data.mapId || data.map_id || "")}"`,
      `createdAt="${escapeXml(data.createdAt || new Date().toISOString())}"`
    ];
    const anchorXml = anchors.map((a) => (
      `<csm:anchor id="${escapeXml(a.anchorId)}" entityId="${escapeXml(a.entityId)}" entityType="${escapeXml(a.entityType)}" trackedChangeCount="${escapeXml(a.trackedChangeCount)}" changeTrackingMode="${escapeXml(a.changeTrackingMode)}" sourcePart="${escapeXml(a.sourcePart)}" paragraphId="${escapeXml(a.paragraphId)}" originalOoxmlPresent="${escapeXml(String(a.originalOoxmlPresent))}" reviewedOriginalPresent="${escapeXml(String(a.reviewedOriginalPresent))}" reviewedCurrentPresent="${escapeXml(String(a.reviewedCurrentPresent))}">` +
      `<csm:originalText>${escapeXml(a.originalText)}</csm:originalText>` +
      `<csm:currentText>${escapeXml(a.currentText)}</csm:currentText>` +
      `</csm:anchor>`
    )).join("");
    const operationXml = operations.map((op) => (
      `<csm:operation anchorId="${escapeXml(op.anchorId || op.anchor_id || "")}" mode="${escapeXml(op.mode || "")}" entityType="${escapeXml(op.entityType || op.entity_type || "")}">` +
      `<csm:from>${escapeXml(op.from || op.from_text || op.originalText || op.original_text || "")}</csm:from>` +
      `<csm:to>${escapeXml(op.to || op.to_text || op.replacementText || op.replacement_text || "")}</csm:to>` +
      `</csm:operation>`
    )).join("");
    const strategy = data.strategy || data.restoreStrategy || data.restore_strategy || {};
    const strategyXml = `<csm:strategy mode="${escapeXml(strategy.mode || "")}" operationsScope="${escapeXml(strategy.operationsScope || strategy.operations_scope || "")}" requiresSidecar="${escapeXml(String(Boolean(strategy.requiresSidecar || strategy.requires_sidecar)))}" requiresFullPackage="${escapeXml(String(Boolean(strategy.requiresFullPackage || strategy.requires_full_package)))}" confidence="${escapeXml(strategy.confidence || "")}">${escapeXml(strategy.reason || "")}</csm:strategy>`;
    return `<?xml version="1.0" encoding="UTF-8"?><csm:revisionMap ${attrs.join(" ")}>${strategyXml}<csm:anchors>${anchorXml}</csm:anchors><csm:operations>${operationXml}</csm:operations></csm:revisionMap>`;
  }

  async function captureSelectionAnchor(options) {
    const opts = options || {};
    const WordApi = requireWord();
    return WordApi.run(async (context) => {
      const doc = context.document;
      const selection = doc.getSelection();
      doc.load("changeTrackingMode");
      const original = selection.getReviewedText(WordApi.ChangeTrackingVersion.original);
      const current = selection.getReviewedText(WordApi.ChangeTrackingVersion.current);
      const ooxml = selection.getOoxml();
      const control = selection.insertContentControl();
      const anchorId = makeAnchorId(opts.anchorId);
      control.tag = anchorId;
      control.title = opts.title || "CSM revision anchor";
      try { control.appearance = WordApi.ContentControlAppearance.tags; } catch (_) {}
      await context.sync();
      return {
        anchorId,
        tag: anchorId,
        title: control.title || "CSM revision anchor",
        changeTrackingMode: doc.changeTrackingMode || "unknown",
        originalText: original.value || "",
        currentText: current.value || "",
        selectionOoxml: ooxml.value || "",
        sourcePart: opts.sourcePart || "body",
        paragraphId: opts.paragraphId || "",
        originalOoxmlPresent: Boolean(ooxml.value),
        reviewedOriginalPresent: Boolean(original.value),
        reviewedCurrentPresent: Boolean(current.value)
      };
    });
  }

  async function resolveAnchor(anchorId) {
    const WordApi = requireWord();
    return WordApi.run(async (context) => {
      const controls = context.document.body.getContentControls().getByTag(String(anchorId || ""));
      controls.load("items/tag,title,text");
      await context.sync();
      if (!controls.items || !controls.items.length) return { found: false, anchorId: String(anchorId || "") };
      const control = controls.items[0];
      const range = control.getRange();
      const current = range.getReviewedText(WordApi.ChangeTrackingVersion.current);
      const original = range.getReviewedText(WordApi.ChangeTrackingVersion.original);
      const ooxml = range.getOoxml();
      let tracked = null;
      try {
        tracked = control.getTrackedChanges();
        tracked.load("items");
      } catch (_) {
        tracked = null;
      }
      await context.sync();
      return {
        found: true,
        anchorId: control.tag || String(anchorId || ""),
        title: control.title || "",
        text: control.text || "",
        currentText: current.value || "",
        originalText: original.value || "",
        selectionOoxml: ooxml.value || "",
        trackedChangeCount: tracked && tracked.items ? tracked.items.length : 0,
        sourcePart: "body",
        originalOoxmlPresent: Boolean(ooxml.value),
        reviewedOriginalPresent: Boolean(original.value),
        reviewedCurrentPresent: Boolean(current.value)
      };
    });
  }

  async function inspectRevisionAnchors() {
    const WordApi = requireWord();
    return WordApi.run(async (context) => {
      const controls = context.document.body.getContentControls();
      controls.load("items/tag,title,text");
      await context.sync();
      const anchors = (controls.items || [])
        .filter((control) => String(control.tag || "").startsWith(ANCHOR_PREFIX))
        .map((control) => ({ anchorId: control.tag || "", title: control.title || "", text: control.text || "", sourcePart: "body" }));
      return { count: anchors.length, anchors };
    });
  }


  function buildDocumentMetadata(payload, customXmlPartId) {
    const data = payload || {};
    const documentMetadata = data.documentMetadata || data.document_metadata || {};
    const base = {
      [MAP_SETTING_KEYS.partId]: String(customXmlPartId || documentMetadata[MAP_SETTING_KEYS.partId] || ""),
      [MAP_SETTING_KEYS.mapId]: String(data.mapId || data.map_id || documentMetadata[MAP_SETTING_KEYS.mapId] || ""),
      [MAP_SETTING_KEYS.schemaVersion]: String(data.schemaVersion || data.schema_version || documentMetadata[MAP_SETTING_KEYS.schemaVersion] || MAP_SCHEMA_VERSION),
      [MAP_SETTING_KEYS.engineVersion]: String(data.engineVersion || data.engine_version || documentMetadata[MAP_SETTING_KEYS.engineVersion] || MAP_ENGINE_VERSION),
      [MAP_SETTING_KEYS.namespace]: MAP_NAMESPACE,
      CSM_RevisionMapMode: String(data.mode || documentMetadata.CSM_RevisionMapMode || ""),
      CSM_RevisionOperationsCount: String((Array.isArray(data.operations) ? data.operations.length : documentMetadata.CSM_RevisionOperationsCount) || 0),
      CSM_RevisionAnchorsCount: String((Array.isArray(data.anchors) ? data.anchors.length : documentMetadata.CSM_RevisionAnchorsCount) || 0),
      CSM_RevisionRestoreStrategy: String((data.strategy && data.strategy.mode) || (data.restoreStrategy && data.restoreStrategy.mode) || documentMetadata.CSM_RevisionRestoreStrategy || "")
    };
    return Object.assign({}, documentMetadata, base);
  }

  async function upsertWordSettings(context, metadata) {
    const settings = context.document && context.document.settings;
    if (!settings || !settings.add) return { saved: false, reason: "Word settings API is unavailable." };
    for (const key of Object.keys(metadata || {})) {
      const value = String(metadata[key] == null ? "" : metadata[key]);
      try {
        const existing = settings.getItemOrNullObject(key);
        existing.load("value");
        await context.sync();
        if (existing.isNullObject) settings.add(key, value);
        else existing.value = value;
      } catch (_) {
        try { settings.add(key, value); } catch (__) {}
      }
    }
    await context.sync();
    return { saved: true, keys: Object.keys(metadata || {}) };
  }

  async function upsertCustomProperties(context, metadata) {
    const props = context.document && context.document.properties && context.document.properties.customProperties;
    if (!props) return { saved: false, reason: "Word customProperties API is unavailable on this host." };
    const keys = Object.keys(metadata || {});
    for (const key of keys) {
      const value = String(metadata[key] == null ? "" : metadata[key]);
      try {
        const existing = props.getItemOrNullObject(key);
        existing.load("key,value");
        await context.sync();
        if (existing.isNullObject) props.add(key, value);
        else existing.value = value;
      } catch (_) {
        try { if (props.add) props.add(key, value); } catch (__) {}
      }
    }
    try { await context.sync(); } catch (_) {}
    return { saved: true, keys };
  }

  async function upsertRevisionMap(payload) {
    const WordApi = requireWord();
    const data = payload || {};
    const xml = String(data.customXmlPayload || data.custom_xml_payload || buildRevisionMapXml(data));
    return WordApi.run(async (context) => {
      const customXmlParts = context.document.customXmlParts;
      if (!customXmlParts || !customXmlParts.add) {
        throw new Error("Word CustomXmlPart API is unavailable.");
      }
      try {
        const existing = customXmlParts.getByNamespace(MAP_NAMESPACE);
        existing.load("items/id");
        await context.sync();
        for (const part of existing.items || []) {
          try { part.delete(); } catch (_) {}
        }
        if (existing.items && existing.items.length) await context.sync();
      } catch (_) {}
      const part = customXmlParts.add(xml);
      try { part.load("id"); } catch (_) {}
      await context.sync();
      const metadata = buildDocumentMetadata(data, part.id || "");
      const settingsResult = await upsertWordSettings(context, metadata);
      const customPropertiesResult = await upsertCustomProperties(context, metadata);
      return {
        namespace: MAP_NAMESPACE,
        schemaVersion: metadata[MAP_SETTING_KEYS.schemaVersion] || MAP_SCHEMA_VERSION,
        engineVersion: metadata[MAP_SETTING_KEYS.engineVersion] || MAP_ENGINE_VERSION,
        mapId: metadata[MAP_SETTING_KEYS.mapId] || "",
        customXmlPartId: part.id || "",
        settings: settingsResult,
        customProperties: customPropertiesResult,
        metadata,
        xml
      };
    });
  }

  async function readRevisionMap() {
    const WordApi = requireWord();
    return WordApi.run(async (context) => {
      let partId = "";
      try {
        const setting = context.document.settings.getItemOrNullObject(MAP_SETTING_KEYS.partId);
        setting.load("value");
        await context.sync();
        partId = setting.isNullObject ? "" : String(setting.value || "");
      } catch (_) {
        partId = "";
      }
      if (partId) {
        try {
          const part = context.document.customXmlParts.getItem(partId);
          const xml = part.getXml();
          await context.sync();
          return { found: true, source: "settings", namespace: MAP_NAMESPACE, customXmlPartId: partId, xml: xml.value || "" };
        } catch (_) {}
      }
      const scoped = context.document.customXmlParts.getByNamespace(MAP_NAMESPACE);
      scoped.load("items/id");
      await context.sync();
      if (!scoped.items || !scoped.items.length) {
        return { found: false, source: "namespace", namespace: MAP_NAMESPACE, customXmlPartId: "", xml: "" };
      }
      const part = scoped.items[0];
      const xml = part.getXml();
      await context.sync();
      return { found: true, source: "namespace", namespace: MAP_NAMESPACE, customXmlPartId: part.id || "", xml: xml.value || "" };
    });
  }

  async function deleteRevisionMap() {
    const WordApi = requireWord();
    return WordApi.run(async (context) => {
      let deletedParts = 0;
      try {
        const scoped = context.document.customXmlParts.getByNamespace(MAP_NAMESPACE);
        scoped.load("items/id");
        await context.sync();
        for (const part of scoped.items || []) {
          try { part.delete(); deletedParts += 1; } catch (_) {}
        }
      } catch (_) {}
      try {
        const settings = context.document.settings;
        for (const key of Object.keys(MAP_SETTING_KEYS)) {
          const item = settings.getItemOrNullObject(MAP_SETTING_KEYS[key]);
          item.load("value");
          await context.sync();
          if (!item.isNullObject && item.delete) item.delete();
        }
      } catch (_) {}
      await context.sync();
      return { deletedParts, namespace: MAP_NAMESPACE };
    });
  }

  const CSMRevisionBridge = Object.freeze({
    ANCHOR_PREFIX,
    MAP_NAMESPACE,
    MAP_SCHEMA_VERSION,
    MAP_ENGINE_VERSION,
    MAP_SETTING_KEYS,
    makeAnchorId,
    buildRevisionMapXml,
    buildDocumentMetadata,
    captureSelectionAnchor,
    resolveAnchor,
    inspectRevisionAnchors,
    upsertRevisionMap,
    readRevisionMap,
    deleteRevisionMap
  });

  root.CSMRevisionBridge = CSMRevisionBridge;
  if (typeof module !== "undefined" && module.exports) module.exports = CSMRevisionBridge;
})(typeof globalThis !== "undefined" ? globalThis : window);
