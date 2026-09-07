/**
 * FaceFlow AI v4 — App Logic
 * Live status messages + Wikidata identity card
 */
"use strict";

// ── State ──────────────────────────────────────────────────────
let selectedFile = null;
let scanResult   = null;

// ── DOM ────────────────────────────────────────────────────────
const dropZone      = document.getElementById("drop-zone");
const fileInput     = document.getElementById("file-input");
const previewImg    = document.getElementById("preview-img");
const previewWrap   = document.getElementById("preview-wrap");
const dropInner     = document.getElementById("drop-inner");
const btnScan       = document.getElementById("btn-scan");
const btnReset      = document.getElementById("btn-reset");
const pipeline      = document.getElementById("pipeline");
const uploadPanel   = document.getElementById("upload-panel");
const progressCard  = document.getElementById("progress-card");
const progressLabel = document.getElementById("progress-label");
const progressFill  = document.getElementById("progress-fill");
const errorBanner   = document.getElementById("error-banner");

// ── Drop Zone ──────────────────────────────────────────────────
dropZone.addEventListener("click", e => { if (e.target !== fileInput) fileInput.click(); });
dropZone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
  e.preventDefault(); dropZone.classList.remove("drag-over");
  const f = e.dataTransfer.files?.[0]; if (f) setFile(f);
});
fileInput.addEventListener("change", () => { if (fileInput.files?.[0]) setFile(fileInput.files[0]); });

function setFile(file) {
  selectedFile = file;
  btnScan.disabled = false;
  const reader = new FileReader();
  reader.onload = e => {
    previewImg.src = e.target.result;
    previewWrap.style.display = "block";
    dropInner.style.display = "none";
  };
  reader.readAsDataURL(file);
}

// ── Live Progress Messages ─────────────────────────────────────
const PROGRESS_MSGS = [
  [0,  10, "Uploading your image securely…"],
  [1,  20, "Detecting face landmarks…"],
  [3,  32, "Building 512-dimensional face embedding…"],
  [5,  44, "Hosting image for reverse image search…"],
  [7,  54, "Querying Google Lens — scanning billions of images…"],
  [9,  63, "Analysing visual matches from the web…"],
  [11, 72, "Comparing face similarity across candidates…"],
  [13, 80, "Searching Wikipedia & Wikidata databases…"],
  [15, 88, "Compiling identity profile…"],
  [17, 94, "Almost done — finalising results…"],
];

let progressTimer = null;
function startProgressAnimation() {
  let idx = 0;
  progressTimer = setInterval(() => {
    if (idx >= PROGRESS_MSGS.length) return clearInterval(progressTimer);
    const [, pct, msg] = PROGRESS_MSGS[idx];
    setProgress(msg, pct);
    idx++;
  }, 2000);
}
function stopProgressAnimation() {
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
}

// ── Scan ───────────────────────────────────────────────────────
btnScan.addEventListener("click", () => startScan(null));

async function startScan(faceIndex = null) {
  if (!selectedFile) return;

  errorBanner.style.display = "none";
  uploadPanel.style.display = "none";
  document.getElementById("multi-face-panel").style.display = "none";
  progressCard.style.display = "flex";
  pipeline.style.display = "none";

  setProgress("Uploading your image securely…", 10);
  startProgressAnimation();

  const fd = new FormData();
  fd.append("image", selectedFile);
  if (faceIndex !== null) fd.append("face_index", faceIndex.toString());

  let result;
  try {
    const resp = await fetch("/api/scan", { method: "POST", body: fd });
    result = await resp.json();
  } catch (err) {
    stopProgressAnimation();
    progressCard.style.display = "none";
    uploadPanel.style.display = "block";
    showError("Network error: " + err.message);
    return;
  }

  stopProgressAnimation();
  setProgress("Done! Rendering results…", 100);
  await sleep(350);
  progressCard.style.display = "none";
  pipeline.style.display = "flex";
  scanResult = result;
  renderResults(result);
}

// ── Render Results ─────────────────────────────────────────────
function renderResults(result) {
  btnReset.style.display = "block";

  // Multi-face ?
  if (!result.success && result.status === "MULTIPLE_FACES" && result.face_detection?.bboxes) {
    showMultiFaceSelector(result.face_detection.bboxes);
    return;
  }

  // Step 1 — Face Detection
  const fd = result.face_detection;
  if (fd) {
    pstepDone(1, `${fd.face_count} face detected`);
    show("s1-body");
    setText("s1-face-status", `${fd.face_count} face(s) found`);
    setText("s1-model",       fd.embedding_model);
    setText("s1-dim",         `${fd.embedding_dimension}-dimensional`);
  } else {
    pstepError(1, result.error?.code || "Failed");
    showError(result.error?.message || "Face detection failed.");
    return;
  }

  if (!result.success && !result.best_candidate) {
    pstepError(2, result.error?.code || "Error");
    showError(result.error?.message);
    return;
  }

  // Step 2 — Web Discovery
  const cnt = result.search_results_count ?? 0;
  const cnd = result.candidates_evaluated ?? 0;
  pstepDone(2, `${cnt} results · ${cnd} analysed`);
  show("s2-body");
  setText("s2-results",    `${cnt} web results found`);
  setText("s2-candidates", `${cnd} face candidates evaluated`);

  // Step 3 — Best Match
  const best = result.best_candidate;
  if (!best) {
    pstepError(3, "No match above threshold");
    showError(result.error?.message || "No candidate above threshold.");
    return;
  }
  pstepDone(3, result.match_label);
  show("s3-body");
  setText("m-sim",   `${best.face_similarity.toFixed(4)} similarity`);
  setText("m-label", result.match_label);
  if (best.url) {
    const ml = document.getElementById("m-link");
    ml.href = best.url; ml.style.display = "inline";
  }

  // Step — Person
  const person = result.person;
  const personStep = document.getElementById("step-person");
  if (person) {
    personStep.className = "pstep done";
    setText("sp-status", `✓ ${person.name}`);
  } else {
    personStep.className = "pstep error-step";
    setText("sp-status", "Not identified");
  }

  // Identity card
  renderIdentityCard(best, person, result.match_label);

  // Fingerprint
  if (result.fingerprint) {
    document.getElementById("fp-row").style.display = "flex";
    setText("s4-fp", result.fingerprint);
  }
}

// ── Identity Card ──────────────────────────────────────────────
function renderIdentityCard(best, person, matchLabel) {
  const card = document.getElementById("identity-card");
  card.style.display = "flex";

  // Photo — Wikipedia person photo > match thumbnail
  const personImg  = document.getElementById("person-img");
  const matchImg   = document.getElementById("match-img");
  const placeholder = document.getElementById("photo-placeholder");

  if (person?.image_url) {
    personImg.src = person.image_url;
    personImg.style.display = "block";
    placeholder.style.display = "none";
  } else if (best.image_url) {
    matchImg.src = best.image_url;
    matchImg.style.display = "block";
    matchImg.onerror = () => { matchImg.style.display = "none"; placeholder.style.display = "flex"; };
    placeholder.style.display = "none";
  }

  // Sim badge
  setText("sim-badge", `${(best.face_similarity * 100).toFixed(1)}% match`);

  // Name & description
  if (person) {
    setText("person-name",    person.name);
    setText("person-desc",    person.description || "Public Figure");
    setText("person-extract", person.extract || "");
  } else {
    setText("person-name",    best.title?.split(" - ")[0]?.split(" — ")[0]?.trim() || "Unknown");
    setText("person-desc",    `Found via ${best.source || "web search"}`);
    setText("person-extract", `Face similarity: ${best.face_similarity.toFixed(4)} · ${matchLabel}`);
  }

  // Meta chips
  const metaWrap = document.getElementById("icard-meta");
  metaWrap.innerHTML = "";
  // SVG icon helpers
  const SVG_TARGET = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="2"/><line x1="12" y1="2" x2="12" y2="6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  const SVG_CAKE   = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M20 21H4V8a2 2 0 012-2h12a2 2 0 012 2v13z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M8 6V4M12 6V3M16 6V4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  const SVG_GLOBE  = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20" stroke="currentColor" stroke-width="2"/></svg>';
  const SVG_BAG    = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><rect x="2" y="7" width="20" height="14" rx="2" stroke="currentColor" stroke-width="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
  const SVG_STAR   = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
  addMetaTag(metaWrap, SVG_TARGET, matchLabel);
  if (person?.birth_date)   addMetaTag(metaWrap, SVG_CAKE,  person.birth_date);
  if (person?.nationality)  addMetaTag(metaWrap, SVG_GLOBE, person.nationality);
  if (person?.occupation)   addMetaTag(metaWrap, SVG_BAG,   person.occupation);
  if (person?.known_for)    addMetaTag(metaWrap, SVG_STAR,  person.known_for);
  if (!person && best.source) addMetaTag(metaWrap, SVG_GLOBE, best.source);


  // Links
  if (person?.wikipedia_url) {
    const wl = document.getElementById("person-wiki-link");
    wl.href = person.wikipedia_url; wl.style.display = "inline-flex";
  }
  if (best.url) {
    const sl = document.getElementById("m-source-link");
    sl.href = best.url; sl.style.display = "inline-flex";
    setText("m-source-text", best.source || "Source");
  }
}

function addMetaTag(wrap, iconSvg, text) {
  const el = document.createElement("span");
  el.className = "meta-tag";
  el.innerHTML = `<span class="meta-tag-icon">${iconSvg}</span><span>${text}</span>`;
  wrap.appendChild(el);
}

// ── Multi-face ─────────────────────────────────────────────────
function showMultiFaceSelector(bboxes) {
  pipeline.style.display = "none";
  progressCard.style.display = "none";
  uploadPanel.style.display = "block";
  document.getElementById("multi-face-panel").style.display = "block";
  const imgEl = document.getElementById("faces-img");
  const boxes = document.getElementById("faces-boxes");
  boxes.innerHTML = "";
  imgEl.src = previewImg.src;
  imgEl.onload = () => {
    const nw = imgEl.naturalWidth, nh = imgEl.naturalHeight;
    bboxes.forEach((bbox, idx) => {
      const [x1, y1, x2, y2] = bbox;
      const box = document.createElement("div");
      box.className = "face-box";
      box.style.left   = `${(x1/nw)*100}%`;
      box.style.top    = `${(y1/nh)*100}%`;
      box.style.width  = `${((x2-x1)/nw)*100}%`;
      box.style.height = `${((y2-y1)/nh)*100}%`;
      box.addEventListener("click", () => startScan(idx));
      boxes.appendChild(box);
    });
  };
}
document.getElementById("btn-cancel-select").addEventListener("click", () => {
  document.getElementById("multi-face-panel").style.display = "none";
});

// ── Reset ──────────────────────────────────────────────────────
btnReset.addEventListener("click", resetAll);

function resetAll() {
  selectedFile = null; scanResult = null;
  fileInput.value = "";
  previewImg.src = "";
  previewWrap.style.display = "none";
  dropInner.style.display = "flex";
  btnScan.disabled = true;
  pipeline.style.display = "none";
  uploadPanel.style.display = "block";
  progressCard.style.display = "none";
  btnReset.style.display = "none";
  errorBanner.style.display = "none";

  [1,2,3].forEach(i => {
    const s = document.getElementById(`step-${i}`);
    if (s) s.className = "pstep";
    setText(`s${i}-status`, "—");
    const b = document.getElementById(`s${i}-body`);
    if (b) b.style.display = "none";
  });
  const ps = document.getElementById("step-person");
  if (ps) ps.className = "pstep";
  setText("sp-status", "—");

  document.getElementById("identity-card").style.display = "none";
  document.getElementById("fp-row").style.display = "none";
  document.getElementById("person-img").style.display = "none";
  document.getElementById("match-img").style.display = "none";
  document.getElementById("photo-placeholder").style.display = "flex";
  document.getElementById("person-wiki-link").style.display = "none";
  document.getElementById("m-source-link").style.display = "none";
  document.getElementById("icard-meta").innerHTML = "";
}

// ── Helpers ────────────────────────────────────────────────────
function pstepDone(n, label) {
  const s = document.getElementById(`step-${n}`);
  if (s) s.className = "pstep done";
  setText(`s${n}-status`, "✓ " + label);
}
function pstepError(n, label) {
  const s = document.getElementById(`step-${n}`);
  if (s) s.className = "pstep error-step";
  setText(`s${n}-status`, label);
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? "—";
}
function show(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = "flex";
}
function showError(msg) {
  if (!msg) return;
  errorBanner.textContent = msg;
  errorBanner.style.display = "block";
}
function setProgress(msg, pct) {
  progressLabel.textContent = msg;
  progressFill.style.width = (pct || 10) + "%";
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
