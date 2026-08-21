(function (root) {
  "use strict";

  const DEFAULT_SLICE_SIZE = 4 * 1024 * 1024;

  function requireWord() {
    if (!root.Word || !root.Word.run) throw new Error("Word JavaScript API is unavailable.");
    return root.Word;
  }

  function requireOfficeDocument() {
    const office = root.Office;
    if (!office || !office.context || !office.context.document) {
      throw new Error("Office.context.document is unavailable.");
    }
    return office.context.document;
  }

  function insertLocationReplace() {
    const WordApi = requireWord();
    return (WordApi.InsertLocation && WordApi.InsertLocation.replace) || "Replace";
  }

  function wordTrackOffValue() {
    const WordApi = requireWord();
    return (WordApi.ChangeTrackingMode && WordApi.ChangeTrackingMode.off) || "Off";
  }

  async function run(operation) {
    // Word.run entrypoint, wrapped for the v0.3 bridge contract.
    const WordApi = requireWord();
    return WordApi.run(operation);
  }

  async function readTrackingMode() {
    return run(async (context) => {
      context.document.load("changeTrackingMode");
      await context.sync();
      return context.document.changeTrackingMode || "unknown";
    });
  }

  async function runWithTrackChangesTemporarilyOff(operation, options) {
    const opts = options || {};
    return run(async (context) => {
      const offValue = wordTrackOffValue();
      let previousMode = "unknown";
      let canControlTracking = false;

      try {
        context.document.load("changeTrackingMode");
        await context.sync();
        previousMode = context.document.changeTrackingMode || "unknown";
        canControlTracking = true;
        if (String(previousMode).toLowerCase() !== String(offValue).toLowerCase()) {
          context.document.changeTrackingMode = offValue;
          await context.sync();
          context.document.load("changeTrackingMode");
          await context.sync();
          canControlTracking = String(context.document.changeTrackingMode || "").toLowerCase() === String(offValue).toLowerCase();
        }
      } catch (_) {
        canControlTracking = false;
      }

      if (opts.requireTrackControl && !canControlTracking) {
        throw new Error("Word did not allow safe temporary control of tracked changes.");
      }

      try {
        const result = await operation(context, canControlTracking, previousMode);
        if (canControlTracking && previousMode && previousMode !== "unknown" && String(previousMode).toLowerCase() !== String(offValue).toLowerCase()) {
          context.document.changeTrackingMode = previousMode;
          await context.sync();
        }
        return { result, canControlTracking, previousMode };
      } catch (error) {
        if (canControlTracking && previousMode && previousMode !== "unknown" && String(previousMode).toLowerCase() !== String(offValue).toLowerCase()) {
          try {
            context.document.changeTrackingMode = previousMode;
            await context.sync();
          } catch (_) {}
        }
        throw error;
      }
    });
  }

  async function runPreservingTrackingMode(operation, options) {
    const opts = options || {};
    return run(async (context) => {
      let previousMode = "unknown";
      let canControlTracking = false;
      try {
        context.document.load("changeTrackingMode");
        await context.sync();
        previousMode = context.document.changeTrackingMode || "unknown";
        canControlTracking = true;
      } catch (_) {
        canControlTracking = false;
      }
      if (opts.requireTrackControl && !canControlTracking) {
        throw new Error("Word did not allow safe access to tracked changes mode.");
      }
      const result = await operation(context, canControlTracking, previousMode);
      return { result, canControlTracking, previousMode };
    });
  }

  async function readBodyText() {
    return run(async (context) => {
      const body = context.document.body;
      body.load("text");
      await context.sync();
      return body.text || "";
    });
  }

  async function readBodyOoxml() {
    return run(async (context) => {
      const bodyOoxml = context.document.body.getOoxml();
      await context.sync();
      return bodyOoxml.value || "";
    });
  }

  async function replaceBodyWithText(text, options) {
    return runWithTrackChangesTemporarilyOff(async (context) => {
      context.document.body.insertText(String(text || ""), insertLocationReplace());
      await context.sync();
    }, options || {});
  }

  async function replaceBodyWithOoxml(ooxml, options) {
    const runner = options && options.preserveTrackChanges ? runPreservingTrackingMode : runWithTrackChangesTemporarilyOff;
    return runner(async (context) => {
      context.document.body.insertOoxml(String(ooxml || ""), insertLocationReplace());
      await context.sync();
    }, options || {});
  }

  function headerFooterTypes() {
    const WordApi = root.Word || {};
    const HF = WordApi.HeaderFooterType || {};
    return [HF.primary || "Primary", HF.firstPage || "FirstPage", HF.evenPages || "EvenPages"];
  }

  async function collectOoxmlParts() {
    return run(async (context) => {
      const parts = {};
      const pending = [{ name: "body", result: context.document.body.getOoxml() }];
      try {
        const sections = context.document.sections;
        sections.load("items");
        await context.sync();
        const types = headerFooterTypes();
        (sections.items || []).forEach((section, sectionIndex) => {
          types.forEach((type, typeIndex) => {
            try { pending.push({ name: `section${sectionIndex}_header${typeIndex}`, result: section.getHeader(type).body.getOoxml() }); } catch (_) {}
            try { pending.push({ name: `section${sectionIndex}_footer${typeIndex}`, result: section.getFooter(type).body.getOoxml() }); } catch (_) {}
          });
        });
      } catch (_) {
        // Some Word hosts do not expose sections, headers or footers to add-ins.
      }
      await context.sync();
      pending.forEach((item) => {
        if (item.result && item.result.value && item.result.value.trim()) parts[item.name] = item.result.value;
      });
      return parts;
    });
  }

  async function replaceOoxmlParts(parts, options) {
    const safeParts = parts || {};
    const runner = options && options.preserveTrackChanges ? runPreservingTrackingMode : runWithTrackChangesTemporarilyOff;
    return runner(async (context) => {
      if (safeParts.body) context.document.body.insertOoxml(safeParts.body, insertLocationReplace());
      try {
        const sections = context.document.sections;
        sections.load("items");
        await context.sync();
        const types = headerFooterTypes();
        (sections.items || []).forEach((section, sectionIndex) => {
          types.forEach((type, typeIndex) => {
            const headerKey = `section${sectionIndex}_header${typeIndex}`;
            const footerKey = `section${sectionIndex}_footer${typeIndex}`;
            try { if (safeParts[headerKey]) section.getHeader(type).body.insertOoxml(safeParts[headerKey], insertLocationReplace()); } catch (_) {}
            try { if (safeParts[footerKey]) section.getFooter(type).body.insertOoxml(safeParts[footerKey], insertLocationReplace()); } catch (_) {}
          });
        });
      } catch (_) {}
      await context.sync();
    }, options || {});
  }

  function trackAllValue() {
    const WordApi = requireWord();
    return (WordApi.ChangeTrackingMode && (WordApi.ChangeTrackingMode.trackAll || WordApi.ChangeTrackingMode.trackMineOnly)) || "TrackAll";
  }

  function ooxmlContainsRevisionMarkup(value) {
    return /<(?:[a-zA-Z0-9]+:)?(?:ins|del|moveFrom|moveTo|pPrChange|rPrChange|tblPrChange|trPrChange|tcPrChange)\b|<(?:[a-zA-Z0-9]+:)?delText\b/.test(String(value || ""));
  }

  function safeClientResultValue(result) {
    // ClientResult.value throws when its load/sync failed or never ran.
    if (!result) return null;
    try { return result.value; } catch (_) { return null; }
  }

  function decodeBasicXmlEntities(value) {
    return String(value || "")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'")
      .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(parseInt(code, 10)))
      .replace(/&amp;/g, "&");
  }

  function ooxmlRevisionMarkupCoversText(value, needle) {
    // A paragraph often mixes tracked and ordinary text. Classifying a search
    // hit as "tracked" just because its paragraph contains any revision markup
    // turned every restored placeholder in such a paragraph into a new tracked
    // change. Only report tracked when the searched text itself sits inside a
    // content revision wrapper (w:ins / w:del / w:moveFrom / w:moveTo).
    const xml = String(value || "");
    if (!xml || !ooxmlContainsRevisionMarkup(xml)) return false;
    const text = String(needle || "");
    if (!text) return false;
    const revisionRe = /<(?:[a-zA-Z0-9]+:)?(ins|del|moveFrom|moveTo)\b[^>]*>([\s\S]*?)<\/(?:[a-zA-Z0-9]+:)?\1>/g;
    let match;
    while ((match = revisionRe.exec(xml)) !== null) {
      const inner = decodeBasicXmlEntities(String(match[2] || "").replace(/<[^>]*>/g, ""));
      if (inner.indexOf(text) !== -1) return true;
    }
    return false;
  }

  async function collectTargets(context) {
    const targets = [{ name: "body", body: context.document.body }];
    try {
      const sections = context.document.sections;
      sections.load("items");
      await context.sync();
      const types = headerFooterTypes();
      (sections.items || []).forEach((section, sectionIndex) => {
        types.forEach((type, typeIndex) => {
          try { targets.push({ name: `section${sectionIndex}_header${typeIndex}`, body: section.getHeader(type).body }); } catch (_) {}
          try { targets.push({ name: `section${sectionIndex}_footer${typeIndex}`, body: section.getFooter(type).body }); } catch (_) {}
        });
      });
    } catch (_) {}
    return targets;
  }

  async function applySearchReplacePairs(pairs, options) {
    const opts = options || {};
    const safePairs = (pairs || []).filter((pair) => pair && pair.from && pair.to);
    if (!safePairs.length) return { replaced: 0, canControlTracking: null, previousMode: null, revisionAware: Boolean(opts.preserveRevisionContext) };

    if (!opts.preserveRevisionContext) {
      const wrapped = await runWithTrackChangesTemporarilyOff(async (context) => {
        const targets = await collectTargets(context);
        let replaced = 0;
        for (const pair of safePairs) {
          for (const target of targets) {
            let results;
            try {
              results = target.body.search(String(pair.from), {
                matchCase: true,
                matchWholeWord: false,
                matchPrefix: false,
                matchSuffix: false,
                matchWildcards: false,
                ignorePunct: false,
                ignoreSpace: false
              });
              results.load("items");
              await context.sync();
            } catch (_) {
              continue;
            }
            for (const range of results.items || []) {
              try {
                range.insertText(String(pair.to), insertLocationReplace());
                replaced += 1;
              } catch (_) {}
            }
            if ((results.items || []).length) {
              try { await context.sync(); } catch (_) {}
            }
          }
        }
        return { replaced };
      }, opts);
      return {
        replaced: Number((wrapped.result && wrapped.result.replaced) || 0),
        canControlTracking: wrapped.canControlTracking,
        previousMode: wrapped.previousMode,
        revisionAware: false
      };
    }

    // Revision-aware retry for mask/restore. This is a practical two-pass
    // replacement strategy for documents with tracked changes:
    //   1) classify each concrete search result as clean/tracked by checking
    //      whether the searched text itself sits inside revision markup in the
    //      range OOXML or the surrounding paragraph OOXML,
    //   2) replace clean ranges with tracking OFF,
    //   3) replace tracked ranges with tracking OFF as well — the swap edits
    //      the text in place inside the existing revision wrapper, so the
    //      user's tracked change survives untouched and the mask/restore swap
    //      itself never shows up as a new revision,
    //   4) restore the user's original tracking mode.
    // The clean/tracked split is kept for ordering and for panel reporting
    // (replacedClean/replacedTracked), not to vary the tracking mode.
    // It is intentionally occurrence-based, not phrase-based: the same text can
    // appear once inside a revision and once in ordinary text.
    return run(async (context) => {
      const offValue = wordTrackOffValue();
      let previousMode = "unknown";
      let canControlTracking = false;
      try {
        context.document.load("changeTrackingMode");
        await context.sync();
        previousMode = context.document.changeTrackingMode || "unknown";
        canControlTracking = true;
      } catch (_) {
        canControlTracking = false;
      }
      if (opts.requireTrackControl && !canControlTracking) {
        throw new Error("Word did not allow safe tracked-change-aware replacement.");
      }

      const setTrackingMode = async (mode) => {
        if (!canControlTracking || !mode || mode === "unknown") return;
        try {
          context.document.changeTrackingMode = mode;
          await context.sync();
        } catch (_) {}
      };

      const classifyRangesForPair = async (target, pair) => {
        let results;
        try {
          results = target.body.search(String(pair.from), {
            matchCase: true,
            matchWholeWord: false,
            matchPrefix: false,
            matchSuffix: false,
            matchWildcards: false,
            ignorePunct: false,
            ignoreSpace: false
          });
          results.load("items");
          await context.sync();
        } catch (_) {
          return { clean: [], tracked: [] };
        }
        const ranges = results.items || [];
        const rangeOoxmlResults = [];
        const paragraphOoxmlResults = [];
        for (const range of ranges) {
          try { if (context.trackedObjects) context.trackedObjects.add(range); } catch (_) {}
          try { rangeOoxmlResults.push(range.getOoxml()); } catch (_) { rangeOoxmlResults.push(null); }
          try { paragraphOoxmlResults.push(range.paragraphs.getFirst().getOoxml()); } catch (_) { paragraphOoxmlResults.push(null); }
        }
        if (rangeOoxmlResults.some(Boolean) || paragraphOoxmlResults.some(Boolean)) {
          // OOXML inspection is best-effort classification input. A failed sync
          // (e.g. GeneralException on an exotic range) must not abort the whole
          // replacement — unreadable results are treated as clean below.
          try { await context.sync(); } catch (_) {}
        }
        const clean = [];
        const tracked = [];
        for (let i = 0; i < ranges.length; i += 1) {
          const rangeXml = safeClientResultValue(rangeOoxmlResults[i]);
          const paragraphXml = safeClientResultValue(paragraphOoxmlResults[i]);
          // Tracked only when the searched text itself is wrapped in revision
          // markup. Text that was never tracked must stay untracked even when
          // its paragraph carries other tracked changes, otherwise restore
          // would invent new revisions for clean text.
          const isTracked = ooxmlRevisionMarkupCoversText(rangeXml, pair.from) || ooxmlRevisionMarkupCoversText(paragraphXml, pair.from);
          (isTracked ? tracked : clean).push({ range: ranges[i], pair, targetName: target.name });
        }
        return { clean, tracked };
      };

      const replaceClassifiedRanges = async (items, trackingMode) => {
        if (!items.length) return 0;
        await setTrackingMode(trackingMode);
        let count = 0;
        for (const item of items) {
          try {
            item.range.insertText(String(item.pair.to), insertLocationReplace());
            count += 1;
          } catch (_) {}
        }
        // A single invalid range fails the whole batch at sync time. Swallow it:
        // occurrences Word did not replace keep their placeholders and the local
        // CSM engine restores them from the document package afterwards.
        try { await context.sync(); } catch (_) { return 0; }
        return count;
      };

      const targets = await collectTargets(context);
      let replacedClean = 0;
      let replacedTracked = 0;
      let classifiedClean = 0;
      let classifiedTracked = 0;

      try {
        for (const pair of safePairs) {
          for (const target of targets) {
            const classified = await classifyRangesForPair(target, pair);
            classifiedClean += classified.clean.length;
            classifiedTracked += classified.tracked.length;
            // Two phases per phrase/target. Clean first, then tracked, so Word
            // does not create unnecessary new revisions in ordinary text while
            // still preserving visible tracked context where it exists.
            replacedClean += await replaceClassifiedRanges(classified.clean, offValue);
            replacedTracked += await replaceClassifiedRanges(classified.tracked, trackedMode);
            try {
              [...classified.clean, ...classified.tracked].forEach((item) => {
                try { if (context.trackedObjects) context.trackedObjects.remove(item.range); } catch (_) {}
              });
            } catch (_) {}
          }
        }
      } finally {
        if (canControlTracking && previousMode && previousMode !== "unknown") {
          try {
            context.document.changeTrackingMode = previousMode;
            await context.sync();
          } catch (_) {}
        }
      }
      return {
        replaced: replacedClean + replacedTracked,
        replacedClean,
        replacedTracked,
        classifiedClean,
        classifiedTracked,
        canControlTracking,
        previousMode,
        revisionAware: true,
        twoPass: true
      };
    });
  }

  function bytesToBase64(bytes) {
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const chunk = bytes.subarray(i, i + chunkSize);
      binary += String.fromCharCode.apply(null, Array.from(chunk));
    }
    return root.btoa(binary);
  }

  function sliceDataToBytes(data) {
    if (data instanceof Uint8Array) return data;
    if (Array.isArray(data)) return new Uint8Array(data);
    if (typeof data === "string") {
      const out = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i += 1) out[i] = data.charCodeAt(i) & 0xff;
      return out;
    }
    return new Uint8Array(0);
  }

  function withTimeout(promise, ms, message) {
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = root.setTimeout(() => reject(new Error(message || `Operation exceeded ${ms} ms.`)), ms);
    });
    return Promise.race([promise.finally(() => root.clearTimeout(timer)), timeout]);
  }

  async function getCompressedDocumentBase64(options) {
    // Uses Office.FileType.Compressed through the Office.js document file API.
    const opts = options || {};
    const document = requireOfficeDocument();
    const office = root.Office || {};
    if (!document.getFileAsync || !office.FileType || !office.FileType.Compressed) {
      throw new Error("Office compressed document access is unavailable.");
    }
    const read = new Promise((resolve, reject) => {
      document.getFileAsync(office.FileType.Compressed, { sliceSize: opts.sliceSize || DEFAULT_SLICE_SIZE }, (result) => {
        if (result.status !== office.AsyncResultStatus.Succeeded) {
          reject(result.error || new Error("Could not read compressed document."));
          return;
        }
        const file = result.value;
        const chunks = [];
        let total = 0;
        let index = 0;
        const closeFile = () => { try { file.closeAsync(() => {}); } catch (_) {} };
        const next = () => {
          if (index >= file.sliceCount) {
            const all = new Uint8Array(total);
            let offset = 0;
            chunks.forEach((chunk) => { all.set(chunk, offset); offset += chunk.length; });
            closeFile();
            resolve(bytesToBase64(all));
            return;
          }
          file.getSliceAsync(index, (sliceResult) => {
            if (sliceResult.status !== office.AsyncResultStatus.Succeeded) {
              closeFile();
              reject(sliceResult.error || new Error("Could not read compressed document slice."));
              return;
            }
            const bytes = sliceDataToBytes(sliceResult.value.data);
            chunks.push(bytes);
            total += bytes.length;
            index += 1;
            next();
          });
        };
        next();
      });
    });
    return opts.timeoutMs ? withTimeout(read, opts.timeoutMs, opts.timeoutMessage) : read;
  }

  const CSMWordBridge = Object.freeze({
    run,
    readTrackingMode,
    runWithTrackChangesTemporarilyOff,
    readBodyText,
    readBodyOoxml,
    replaceBodyWithText,
    replaceBodyWithOoxml,
    collectOoxmlParts,
    replaceOoxmlParts,
    applySearchReplacePairs,
    ooxmlContainsRevisionMarkup,
    ooxmlRevisionMarkupCoversText,
    getCompressedDocumentBase64,
    headerFooterTypes,
    bytesToBase64,
    sliceDataToBytes,
    withTimeout
  });

  root.CSMWordBridge = CSMWordBridge;
  if (typeof module !== "undefined" && module.exports) module.exports = CSMWordBridge;
})(typeof globalThis !== "undefined" ? globalThis : window);
