#!/usr/bin/env node
/* Static validation used by npm run lint and npm run build.
 * The Office add-in is shipped as static files, so "build" means validating
 * syntax and the UX/API/release contract rather than bundling assets.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..", "..");
const mode = process.argv.includes("--build") ? "build" : "lint";
const failures = [];

function relPath(abs) {
  return path.relative(root, abs).replace(/\\/g, "/");
}

function read(rel) {
  return fs.readFileSync(path.join(root, rel), "utf8");
}

function readJson(rel) {
  return JSON.parse(read(rel));
}

function requireFile(rel) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) failures.push(`Missing required file: ${rel}`);
}

function assertContains(rel, needle, message) {
  const text = read(rel);
  if (!text.includes(needle)) failures.push(`${rel}: ${message}`);
}

function syntaxCheck(rel) {
  const file = path.join(root, rel);
  const result = spawnSync(process.execPath, ["--check", file], { encoding: "utf8" });
  if (result.status !== 0) {
    failures.push(`${rel}: JavaScript syntax check failed\n${result.stderr || result.stdout}`);
  }
}

function syntaxCheckIfPresent(rel) {
  // Generated at runtime by tools/start-claude-safe-mode.ps1; a fresh clone does not have it.
  if (!fs.existsSync(path.join(root, rel))) return;
  syntaxCheck(rel);
}

function walk(dir, cb) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    const rel = relPath(abs);
    if (entry.isDirectory()) {
      if ([".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"].includes(entry.name)) {
        cb(abs, rel, entry);
        continue;
      }
      walk(abs, cb);
    } else {
      cb(abs, rel, entry);
    }
  }
}

["VERSION.json", "addin/taskpane.html", "addin/taskpane.js", "addin/word-bridge.js", "addin/revision_bridge.js", "addin/state-machine.js", "addin/manifest.xml", "server/api.py", "server/version.py", "tests/run_pytest.py", ".github/workflows/build-csm-installer.yml", ".github/release.yml"].forEach(requireFile);

const versionData = readJson("VERSION.json");
const appVersion = versionData.version;
const versionTag = `v${appVersion}`;
const versionUnderscore = appVersion.replace(/\./g, "_");

["addin/taskpane.js", "addin/word-bridge.js", "addin/revision_bridge.js", "addin/state-machine.js"].forEach(syntaxCheck);
syntaxCheckIfPresent("addin/csm-token.js");

assertContains("addin/taskpane.html", "id=\"progressCard\"", "missing operation progress panel");
assertContains("addin/taskpane.html", "progress-spinner", "missing spinner for long-running operations");
assertContains("addin/taskpane.js", "function setBusy", "missing centralized busy-state handler");
assertContains("addin/taskpane.js", "showButtonLoading", "missing button-level loading feedback");
assertContains("addin/taskpane.js", "async function apiPost", "missing local API wrapper");
assertContains("addin/taskpane.js", "async function apiGet", "missing authenticated local API GET wrapper");
assertContains("addin/taskpane.js", "checkRevisionSidecarStatus", "missing sidecar status frontend synchronization helper");
assertContains("addin/taskpane.html", "btnRevisionSidecarStatus", "missing sidecar status diagnostic button");
assertContains("addin/taskpane.js", "function requireRevisionBridge", "missing revision bridge accessor");
assertContains("addin/taskpane.js", "CSM_MANUAL_CONTROLS_V1", "missing local manual rules storage key");
assertContains("addin/taskpane.js", "function saveManualControlsPreset", "missing local manual rules save handler");
assertContains("addin/taskpane.js", "function loadManualControlsPreset", "missing local manual rules load handler");
assertContains("addin/taskpane.js", "function exportManualControlsPreset", "missing local manual rules export handler");
assertContains("addin/taskpane.js", "async function importManualControlsPreset", "missing local manual rules import handler");
assertContains("addin/taskpane.html", "btnSaveManualControls", "missing save manual rules button");
assertContains("addin/taskpane.html", "btnLoadManualControls", "missing load manual rules button");
assertContains("addin/taskpane.html", "btnExportManualControls", "missing export manual rules button");
assertContains("addin/taskpane.html", "btnImportManualControls", "missing import manual rules button");

assertContains("addin/taskpane.html", `id="documentProfile"`, "missing document profile selector");
assertContains("addin/taskpane.html", "Pisma procesowe", "missing pleadings profile label");
assertContains("addin/taskpane.html", "Umowy", "missing contracts profile label");
assertContains("addin/taskpane.js", "function selectedDocumentProfile", "missing selected document profile handler");
assertContains("addin/taskpane.js", "renderMappingActions", "missing quick mapping action renderer");
assertContains("addin/taskpane.js", `data-map-action="never"`, "missing quick never-anonymize action");
assertContains("addin/taskpane.js", `data-map-action="always"`, "missing quick always-anonymize action");
assertContains("server/api.py", "DOCUMENT_PROFILES", "backend must define document profiles");
assertContains("server/api.py", "_profile_report", "backend must include profile report helper");
assertContains("addin/taskpane.js", "catch (networkError)", "API wrapper should fail safely on network errors");
assertContains("addin/manifest.xml", "<TaskpaneId>Office.AutoShowTaskpaneWithDocument</TaskpaneId>", "manifest must designate the auto-open task pane id");
assertContains("addin/taskpane.js", "OFFICE_AUTO_SHOW_TASKPANE_KEY = \"Office.AutoShowTaskpaneWithDocument\"", "frontend must tag documents for Office task pane auto-open");
assertContains("server/security.py", "os.environ.get(\"CSM_API_TOKEN\")", "local API token must be read from environment/runtime, not hardcoded");
assertContains("server/api.py", "from version import APP_VERSION", "backend must use central server/version.py");
assertContains("server/version.py", "VERSION.json", "server/version.py must load the root VERSION.json");


assertContains("addin/revision_bridge.js", "MAP_SETTING_KEYS", "revision bridge must persist CustomXmlPart pointers in document settings");

assertContains("addin/revision_bridge.js", "readRevisionMap", "revision bridge must read persisted revision maps");

assertContains("addin/revision_bridge.js", "deleteRevisionMap", "revision bridge must expose revision map cleanup");

assertContains("addin/revision_bridge.js", "context.document.properties.customProperties", "revision bridge must mirror small metadata into custom properties when available");

assertContains("addin/taskpane.js", "persistRevisionMapForCurrentDocument", "taskpane must persist revision map after masking");

assertContains("server/word_revision_engine.py", "build_document_metadata", "backend revision plan must emit document metadata");

assertContains("server/api.py", "document_metadata=build_document_metadata(job)", "revision endpoints must return document metadata for Word settings/custom properties");

const workflow = read(".github/workflows/build-csm-installer.yml");
if (!/^permissions:\n\s+contents: read/m.test(workflow)) failures.push(".github/workflows/build-csm-installer.yml: workflow must use least-privilege contents: read permissions");
["actions/checkout@v6", "actions/setup-node@v4", "actions/setup-python@v5", "actions/upload-artifact@v7"].forEach((needle) => {
  if (!workflow.includes(needle)) failures.push(`.github/workflows/build-csm-installer.yml: missing ${needle}`);
});
["npm ci", "python -m pip install -r server\\requirements.txt", "npm run lint --silent", "python -m pytest -q", "npm run build --silent"].forEach((needle) => {
  if (!workflow.includes(needle)) failures.push(`.github/workflows/build-csm-installer.yml: missing QA step '${needle}'`);
});
if (!workflow.includes("concurrency:")) failures.push(".github/workflows/build-csm-installer.yml: workflow should declare concurrency to avoid duplicate installer builds");
if (!workflow.includes("cancel-in-progress: true")) failures.push(".github/workflows/build-csm-installer.yml: concurrency should cancel in-progress duplicate builds");
if (!workflow.includes("persist-credentials: false")) failures.push(".github/workflows/build-csm-installer.yml: checkout should not persist credentials when the workflow only needs read access");
if (!workflow.includes("needs: qa")) failures.push(".github/workflows/build-csm-installer.yml: installer build must depend on qa job");
if (!workflow.includes("if-no-files-found: error")) failures.push(".github/workflows/build-csm-installer.yml: artifact upload must fail when installer is missing");
if (!workflow.includes("retention-days:")) failures.push(".github/workflows/build-csm-installer.yml: installer artifact should declare retention-days");

const archivedSkippedTest = "tests/test_v04_taskpane_integration.py";
if (fs.existsSync(path.join(root, archivedSkippedTest))) {
  failures.push(`${archivedSkippedTest}: archived skipped tests must live outside active pytest collection`);
}
const archivedTestDoc = "docs/archive/tests/test_v04_taskpane_integration.py.txt";
if (!fs.existsSync(path.join(root, archivedTestDoc))) {
  failures.push(`${archivedTestDoc}: historical alpha4 taskpane test should be archived as documentation, not collected by pytest`);
}


// Active pytest files should be feature-oriented, not historical release labels.
const historicalTestNameRe = /^test_v(?:0?3|0?4|0?5|0?6|0?7|030|035|036|037|039|040|041|042|043|044|050)|alpha|beta|hotfix/i;
const activeTestDir = path.join(root, "tests");
for (const name of fs.readdirSync(activeTestDir)) {
  if (name.endsWith(".py") && historicalTestNameRe.test(name)) {
    failures.push(`tests/${name}: active tests must use feature-based names, not historical release labels`);
  }
}
const activeTestHistoricalTextRe = /(?:v)?0\.4\.(?:1(?:\.1)?|2(?:\.1|\.2|\.3)?|3|4|5)\b|0\.3\.0-alpha|\balpha\d*\b|\bbeta\d*\b|\bhotfix\b/i;
for (const name of fs.readdirSync(activeTestDir)) {
  if (!name.endsWith(".py")) continue;
  const rel = `tests/${name}`;
  const text = read(rel);
  if (activeTestHistoricalTextRe.test(text)) {
    failures.push(`${rel}: active tests must not contain stale historical release wording`);
  }
}
const oldInstructionAssetDir = "docs/v04_legacy_instr_assets";
if (fs.existsSync(path.join(root, oldInstructionAssetDir))) {
  failures.push(`${oldInstructionAssetDir}: historical instruction assets must live under docs/archive/`);
}

const releaseConfig = read(".github/release.yml");
if (!releaseConfig.includes("changelog:")) failures.push(".github/release.yml: missing changelog configuration");
if (!releaseConfig.includes("skip-changelog")) failures.push(".github/release.yml: missing skip-changelog exclusion");

const packageJson = readJson("package.json");
const addinPackageJson = readJson("addin/package.json");
const packageLockJson = readJson("package-lock.json");
const addinPackageLockJson = readJson("addin/package-lock.json");
if (packageJson.version !== appVersion) failures.push(`package.json: expected version ${appVersion}, got ${packageJson.version}`);
if (addinPackageJson.version !== appVersion) failures.push(`addin/package.json: expected version ${appVersion}, got ${addinPackageJson.version}`);
if (packageLockJson.version !== appVersion) failures.push(`package-lock.json: expected root version ${appVersion}, got ${packageLockJson.version}`);
if ((packageLockJson.packages && packageLockJson.packages[""] && packageLockJson.packages[""].version) !== appVersion) failures.push("package-lock.json: packages[''].version is not synchronized");
if (addinPackageLockJson.version !== appVersion) failures.push(`addin/package-lock.json: expected root version ${appVersion}, got ${addinPackageLockJson.version}`);
if ((addinPackageLockJson.packages && addinPackageLockJson.packages[""] && addinPackageLockJson.packages[""].version) !== appVersion) failures.push("addin/package-lock.json: packages[''].version is not synchronized");

const taskpane = read("addin/taskpane.html");
const jsFiles = ["addin/taskpane.js", "addin/word-bridge.js", "addin/revision_bridge.js", "addin/state-machine.js"].map(read).join("\n");
if (/GEMINI_API_KEY\s*=\s*["'][^"']+/.test(taskpane) || /CSM_API_TOKEN\s*=\s*["'][^"']+/.test(taskpane)) {
  failures.push("addin/taskpane.html: potential hardcoded API secret in UI");
}
if (/GEMINI_API_KEY\s*=\s*["'][^"']+/.test(jsFiles) || /CSM_API_TOKEN\s*=\s*["'][^"']+/.test(jsFiles)) {
  failures.push("addin/*.js: potential hardcoded API secret");
}

// Distribution hygiene: root package may contain only current user-facing artifacts.
const expectedInstruction = `Instrukcja_CSM_v${versionUnderscore}.docx`;
const expectedChecklist = `WINDOWS-TEST-CHECKLIST-${versionTag}.md`;
const expectedReleaseNotes = `RELEASE-NOTES-${versionTag}.txt`;
for (const rel of [expectedInstruction, expectedChecklist, expectedReleaseNotes]) requireFile(rel);

const releaseNotesInRoot = fs.readdirSync(root).filter((name) => /^RELEASE-NOTES-v\d+\.\d+\.\d+(?:\.\d+)?\.txt$/.test(name));
for (const name of releaseNotesInRoot) {
  if (name !== expectedReleaseNotes) failures.push(`Historical release notes must be in docs/archive/release-notes, not root: ${name}`);
}
const instructionDocsInRoot = fs.readdirSync(root).filter((name) => /^Instrukcja_CSM_v\d+_\d+_\d+(?:_\d+)?\.docx$/.test(name));
for (const name of instructionDocsInRoot) {
  if (name !== expectedInstruction) failures.push(`Historical instruction DOCX must not be packaged in root: ${name}`);
}
const checklistsInRoot = fs.readdirSync(root).filter((name) => /^WINDOWS-TEST-CHECKLIST-v\d+\.\d+\.\d+(?:\.\d+)?\.md$/.test(name));
for (const name of checklistsInRoot) {
  if (name !== expectedChecklist) failures.push(`Historical Windows checklist must not be packaged in root: ${name}`);
}

const installGuide = fs.existsSync(path.join(root, "install-guide.html")) ? read("install-guide.html") : "";
if (!installGuide.includes(`CSM for Word ${versionTag}`)) failures.push(`install-guide.html: missing current ${versionTag} title`);
if (!installGuide.includes(`CSM-Setup-${versionTag}.exe`)) failures.push(`install-guide.html: missing current installer filename`);

const activeUserVisibleLabels = {
  "addin/taskpane.html": [/\balpha\b/i, /\bbeta\b/i],
  "addin/taskpane.js": [/Roundtrip alpha/i],
  "server/api.py": [/Alpha roundtrip check/i, /file_docx_negotiation_alpha/],
};
for (const [rel, patterns] of Object.entries(activeUserVisibleLabels)) {
  if (!fs.existsSync(path.join(root, rel))) continue;
  const text = read(rel);
  for (const pattern of patterns) {
    if (pattern.test(text)) failures.push(`${rel}: stale alpha/beta wording must not appear in active user-facing/runtime paths (${pattern})`);
  }
}

const currentFacingFiles = [
  "README.md",
  "README-EASY-START.md",
  "install-guide.html",
  "addin/taskpane.html",
  "addin/taskpane.js",
  "addin/manifest.xml",
  "installer/CSM-Setup.iss",
  "installer/build-csm-setup.ps1",
  "installer/README.md",
  expectedReleaseNotes,
  expectedChecklist,
];
const staleVersionRe = /(?:v)?0\.4\.(?:0-alpha2|1(?:\.1)?|2(?:\.1|\.2|\.3)?|3|4|5)\b/g;
for (const rel of currentFacingFiles) {
  if (!fs.existsSync(path.join(root, rel))) continue;
  const text = read(rel);
  const matches = [...text.matchAll(staleVersionRe)].map((m) => m[0]);
  if (matches.length) failures.push(`${rel}: stale user-facing version references (${[...new Set(matches)].join(", ")})`);
}

// Generated/runtime/transient files must not leak into source packages.
const forbiddenDirNames = new Set(["node_modules", ".venv"]);
const forbiddenFilePatterns = [/\.pyc$/i, /^npm-audit.*\.json$/i, /^\.DS_Store$/i];
walk(root, (abs, rel, entry) => {
  if (rel.startsWith("docs/archive/")) return;
  if (entry.isDirectory() && forbiddenDirNames.has(entry.name)) failures.push(`Forbidden generated directory in package: ${rel}`);
  // Python caches are intentionally ignored here so lint remains stable after developers run pytest.
  // Release ZIP cleanliness is verified before packaging and by package-content checks.
  if (entry.isFile() && forbiddenFilePatterns.some((re) => re.test(entry.name))) failures.push(`Forbidden transient file in package: ${rel}`);
});

const backupDir = path.join(root, "backups");
if (fs.existsSync(backupDir)) {
  const generatedBackups = fs.readdirSync(backupDir).filter((name) => ![".keep", "WARNING.txt"].includes(name));
  if (generatedBackups.length) {
    failures.push(`backups/: package must not contain generated backup/session folders (${generatedBackups.slice(0, 5).join(", ")})`);
  }
}


const activeTextFilesForPolicy = [
  "server/api.py",
  "server/tc_engine.py",
  "server/redactor.py",
  "addin/taskpane.html",
  "README.md",
  expectedReleaseNotes,
];
for (const rel of activeTextFilesForPolicy) {
  if (!fs.existsSync(path.join(root, rel))) continue;
  const text = read(rel);
  const pendingOcrPattern = new RegExp(["nie wykonuje", "jeszcze"].join(" ") + "|" + ["jeszcze", ".*OCR"].join(" ") + "|" + ["pełnego", "OCR"].join(" "), "i");
  if (pendingOcrPattern.test(text)) {
    failures.push(`${rel}: user-facing copy must not suggest OCR is a planned or pending feature`);
  }
}

if (mode === "build") {
  assertContains("addin/manifest.xml", "taskpane.html", "manifest must point to the task pane");
  assertContains("server/api.py", "@app.exception_handler(Exception)", "backend should expose a global fail-safe exception handler");
  assertContains("VERSION.json", '"cloud_features": true', "cloud/VPS features must remain explicitly enabled for the v1.3 release line");
  assertContains("VERSION.json", '"ocr_features": false', "OCR features must remain disabled for this release line");
}

if (failures.length) {
  console.error(`CSM ${mode} validation failed:`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`CSM ${mode} validation passed for ${versionTag}.`);
