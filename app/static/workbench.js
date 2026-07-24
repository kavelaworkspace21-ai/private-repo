/* ── Juriscite — Advocate Workbench (LSAI-WB) ──
   Hub → guided session: INTAKE → CONFIRM → GENERATING → artifact (review-gated). */
"use strict";

let session = null;          // latest session payload from the API
let artifact = null;
let triedSubmit = false;

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  loadTiles();
  loadCases();
});

/* ── Hub ── */
async function loadTiles() {
  const grid = document.getElementById("wb-tiles");
  try {
    const r = await apiFetch("/api/workbench/workflows");
    if (!r.ok) { grid.innerHTML = '<p class="muted">Sign in to use the Workbench.</p>'; return; }
    const flows = await r.json();
    grid.innerHTML = "";
    flows.forEach(f => {
      const locked = f.needs_upload && !f.upload_ready && !f.upload_tool;
      const tile = document.createElement("div");
      tile.className = "wb-tile" + (locked ? " locked" : "");
      tile.innerHTML =
        (locked ? '<span class="lock">DOCUMENT UPLOAD — NEXT UPDATE</span>' : "") +
        `<div class="t">${esc(f.label)}</div>` +
        `<div class="d">${esc(f.tagline)}</div>` +
        `<div class="meta">${f.questions} intake questions · ${f.sections} sections · ` +
        `${f.kind === "draft" ? "counts as 1 draft" : "counts as 1 research query"}</div>`;
      if (f.upload_tool) tile.onclick = () => openFilePanel();
      else if (f.upload_ready) tile.onclick = () => openUploadFirst(f);
      else if (f.type === "argument_studio") tile.onclick = () => openArgEntry(f);
      else if (!f.needs_upload) tile.onclick = () => startSession(f.type);
      grid.appendChild(tile);
    });
    _fillLibFilters(flows);
    loadLibrary();
  } catch (_) {
    grid.innerHTML = '<p class="muted">Could not load the Workbench.</p>';
  }
}

async function loadCases() {
  try {
    const r = await apiFetch("/api/cases/");
    if (!r.ok) return;
    const sel = document.getElementById("wa-case");
    (await r.json()).forEach(c => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.title.length > 30 ? c.title.slice(0, 29) + "…" : c.title;
      sel.appendChild(o);
    });
  } catch (_) {}
}

/* ── Session flow ── */
let pendingUploadFirst = null;   // workflow awaiting its Step-0 upload

function openUploadFirst(f) {
  // Upload-first workflows: the document comes before the questions.
  pendingUploadFirst = f.type;
  session = null; artifact = null; triedSubmit = false;
  document.getElementById("wb-hub").style.display = "none";
  document.getElementById("wb-session").style.display = "";
  document.getElementById("ws-title").textContent = f.label;
  document.getElementById("ws-state").textContent = "Step 0 · Attach file";
  ["ws-intake", "ws-confirm", "ws-generating", "ws-artifact"].forEach(id => show(id, false));
  show("ws-uploadstep", true);
  // Judgment Analyzer also accepts an Indian Kanoon pick (WB-05).
  show("ws-kanoon-row", f.type === "judgment_analyzer");
}

function openArgEntry(f) {
  // Argument Studio's three entry modes: Matter / (files via WB-08) / selected citations.
  pendingUploadFirst = f.type;
  session = null; artifact = null; triedSubmit = false;
  document.getElementById("wb-hub").style.display = "none";
  document.getElementById("wb-session").style.display = "";
  document.getElementById("ws-title").textContent = f.label;
  document.getElementById("ws-state").textContent = "Step 0 · Build from";
  ["ws-intake", "ws-confirm", "ws-generating", "ws-artifact", "ws-uploadstep"].forEach(id => show(id, false));
  const sel = document.getElementById("arg-matter");
  if (sel.options.length <= 1) {
    const src = document.getElementById("wa-case");
    Array.from(src.options).slice(1).forEach(o => sel.appendChild(o.cloneNode(true)));
  }
  show("ws-argstep", true);
}

async function startArgSession() {
  const matterId = document.getElementById("arg-matter").value;
  const tids = document.getElementById("arg-citations").value
    .split(/[\s,]+/).map(s => (s.match(/\d{3,}/) || [""])[0]).filter(Boolean);
  show("ws-argstep", false);
  const r = await apiFetch("/api/workbench/sessions", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow_type: "argument_studio",
                           matter_id: matterId ? parseInt(matterId, 10) : null,
                           citation_tids: tids }),
  });
  const body = await r.json();
  if (!r.ok) { toast(body.detail || "Could not start.", "error"); openArgEntry({ type: "argument_studio", label: "Argument Studio" }); return; }
  session = body; artifact = null; triedSubmit = false;
  const cn = (session.selected_citations || []).length;
  document.getElementById("ws-title").textContent =
    session.label + (cn ? ` — ${cn} selected judgment(s)` : "");
  renderState();
}

async function pickFromKanoon() {
  const tid = document.getElementById("ws-kanoon").value.trim();
  if (!tid) { toast("Paste the Kanoon doc link or id first.", "error"); return; }
  const btn = document.getElementById("ws-kanoon-btn");
  btn.disabled = true; btn.textContent = "Fetching…";
  try {
    const r = await apiFetch("/api/workbench/uploads/from-kanoon", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tid }),
    });
    const body = await r.json();
    if (!r.ok) { toast(body.detail || "Fetch failed.", "error"); return; }
    show("ws-uploadstep", false);
    await startSession(pendingUploadFirst, [body.id]);
    pendingUploadFirst = null;
  } finally {
    btn.disabled = false; btn.textContent = "Fetch & continue";
  }
}

async function uploadForSession() {
  const inp = document.getElementById("ws-file");
  if (!inp.files.length) { toast("Choose a PDF or TXT file first.", "error"); return; }
  const btn = document.getElementById("ws-upload-btn");
  btn.disabled = true; btn.textContent = "Extracting…";
  try {
    const fd = new FormData();
    fd.append("file", inp.files[0]);
    const r = await apiFetch("/api/workbench/uploads", { method: "POST", body: fd });
    const body = await r.json();
    if (!r.ok) { toast(body.detail || "Upload failed.", "error"); return; }
    show("ws-uploadstep", false);
    await startSession(pendingUploadFirst, [body.id]);
    pendingUploadFirst = null;
  } finally {
    btn.disabled = false; btn.textContent = "Upload & continue";
  }
}

async function startSession(type, uploadIds) {
  const r = await apiFetch("/api/workbench/sessions", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow_type: type, upload_ids: uploadIds || [] }),
  });
  const body = await r.json();
  if (!r.ok) { toast(body.detail || "Could not start.", "error"); return; }
  session = body; artifact = null; triedSubmit = false;
  document.getElementById("wb-hub").style.display = "none";
  document.getElementById("wb-session").style.display = "";
  show("ws-uploadstep", false);
  const up = (session.uploads && session.uploads.length)
    ? " — " + session.uploads.map(u => u.filename).join(", ") : "";
  document.getElementById("ws-title").textContent = session.label + up;
  renderState();
}

function backToHub() {
  document.getElementById("wb-session").style.display = "none";
  document.getElementById("wb-hub").style.display = "";
  session = null;
  loadLibrary();
}

function show(id, on) { document.getElementById(id).style.display = on ? "" : "none"; }

function renderState() {
  const st = session.state;
  document.getElementById("ws-state").textContent =
    { INTAKE: "Step 1 · Intake", CONFIRM: "Step 2 · Confirm", GENERATING: "Generating…",
      COMPLETE: "Complete", REFUSED: "Refused — no source" }[st] || st;
  show("ws-intake", st === "INTAKE");
  show("ws-confirm", st === "CONFIRM");
  show("ws-generating", st === "GENERATING");
  show("ws-artifact", !!artifact && (st === "COMPLETE" || st === "REFUSED"));
  if (st === "INTAKE") renderQuestions();
  if (st === "CONFIRM") renderRecap();
}

function renderQuestions() {
  const box = document.getElementById("ws-questions");
  box.innerHTML = "";
  session.questions.forEach(q => {
    const wrap = document.createElement("div");
    wrap.className = "ws-q" + (triedSubmit && session.missing.includes(q.key) ? " missing" : "");
    wrap.innerHTML = `<label>${esc(q.question)} ${q.required ? '<span class="req">*</span>' : ""}</label>`;
    const ta = document.createElement("textarea");
    ta.id = "q_" + q.key;
    ta.value = session.answers[q.key] || "";
    if (q.hint) ta.placeholder = q.hint;
    wrap.appendChild(ta);
    box.appendChild(wrap);
  });
  show("ws-assume-row", triedSubmit && session.missing.length > 0);
}

function collectAnswers() {
  const out = {};
  session.questions.forEach(q => {
    const el = document.getElementById("q_" + q.key);
    if (el && el.value.trim()) out[q.key] = el.value.trim();
  });
  return out;
}

async function submitAnswers() {
  const btn = document.getElementById("ws-continue");
  btn.disabled = true; btn.textContent = "Saving…";
  try {
    const r = await apiFetch(`/api/workbench/sessions/${session.id}/answers`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        answers: collectAnswers(),
        proceed_with_assumptions: document.getElementById("ws-assume").checked,
      }),
    });
    const body = await r.json();
    if (!r.ok) { toast(body.detail || "Error", "error"); return; }
    session = body; triedSubmit = true;
    if (session.state === "INTAKE") {
      toast(`${session.missing.length} required question(s) still unanswered.`, "error");
    }
    renderState();
  } finally {
    btn.disabled = false; btn.textContent = "Continue";
  }
}

function editIntake() { session.state = "INTAKE"; renderState(); }

function renderRecap() {
  const rec = document.getElementById("ws-recap");
  rec.innerHTML = session.questions.map(q => {
    const a = session.answers[q.key];
    return `<div style="margin-bottom:.45rem;"><span style="color:var(--text-3);">${esc(q.question)}</span><br/>` +
           (a ? `<b>${esc(a)}</b>` : '<i style="color:#F59E0B;">(unanswered — stated assumption)</i>') + `</div>`;
  }).join("");
  const asx = document.getElementById("ws-assumptions");
  if (session.assumptions.length) {
    asx.style.display = "";
    asx.innerHTML = "<b>Stated assumptions that will appear in the output:</b><br/>" +
      session.assumptions.map(esc).join("<br/>");
  } else asx.style.display = "none";
}

async function generateArtifact() {
  session.state = "GENERATING"; renderState();
  try {
    const r = await apiFetch(`/api/workbench/sessions/${session.id}/generate`, { method: "POST" });
    const body = await r.json();
    if (!r.ok) {
      session.state = "CONFIRM"; renderState();
      const d = body.detail || {};
      toast(d.message || d.error || (typeof d === "string" ? d : "Generation failed."), "error");
      if (d.upgrade_url) setTimeout(() => { location.href = d.upgrade_url; }, 1800);
      return;
    }
    artifact = body;
    const sref = await apiFetch(`/api/workbench/sessions/${session.id}`);
    session = await sref.json();
    renderArtifact();
    renderState();
  } catch (_) {
    session.state = "CONFIRM"; renderState();
    toast("Network error — nothing was charged. Retry.", "error");
  }
}

function regenerate() { generateArtifact(); }

function renderArtifact() {
  document.getElementById("wa-conf").textContent = "Confidence: " + artifact.confidence;
  document.getElementById("wa-ver").textContent = "version " + artifact.version +
    " · " + (artifact.citations.length ? artifact.citations.length + " verified citation(s)" : "no citations");
  const refused = session.state === "REFUSED" ||
    artifact.sections.every(s => s.blocked || !s.content.trim());
  const rbox = document.getElementById("wa-refused");
  if (session.state === "REFUSED") {
    rbox.style.display = "";
    rbox.innerHTML = "<b>Refused — no source, no answer.</b> The retrieved law did not cover " +
      "the legal points this artifact needed, so it was withheld rather than guessed. " +
      "Refine the intake (name the statute or facts more precisely) and regenerate.";
  } else rbox.style.display = "none";

  const box = document.getElementById("wa-sections");
  box.innerHTML = "";
  artifact.sections.forEach(sec => {
    const el = document.createElement("div");
    el.className = "wa-sec" + (sec.blocked ? " blocked" : "");
    let cards = "";
    if (sec.authorities && sec.authorities.length) {
      cards = '<div style="margin-top:.6rem;">' + sec.authorities.map(a =>
        `<a href="${esc(a.url)}" target="_blank" rel="noopener" style="display:block;margin:.35rem 0;` +
        `padding:.45rem .6rem;border-left:2px solid var(--sapphire,#3B82F6);background:var(--surface-2);` +
        `border-radius:0 8px 8px 0;font-size:.74rem;color:var(--text-2);text-decoration:none;">` +
        `<b style="color:var(--sapphire,#3B82F6);">[${esc(a.ref)}]</b> ${esc(a.title)} — ` +
        `${esc(a.court)}, ${esc(a.date)} <span style="color:var(--text-4);">(good-law: ${esc(a.good_law)})</span></a>`
      ).join("") + "</div>";
    }
    el.innerHTML = `<span class="gtag">${sec.grounding !== "NONE" ? esc(sec.grounding) : ""}</span>` +
      `<h3>${esc(sec.name)}</h3><div class="body">${esc(sec.content)}</div>` + cards;
    box.appendChild(el);
  });
}

async function saveToReview() {
  const caseId = document.getElementById("wa-case").value;
  const r = await apiFetch(`/api/workbench/artifacts/${artifact.id}/save-to-review`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId ? parseInt(caseId, 10) : null }),
  });
  const body = await r.json();
  if (!r.ok) { toast(body.detail || "Save failed.", "error"); return; }
  toast("Saved for advocate review — opening Drafts…");
  setTimeout(() => { location.href = "/drafts"; }, 1200);
}

/* ── WB-08: Artifact Library + practice actions ── */
async function loadLibrary() {
  const box = document.getElementById("lib-rows");
  if (!box) return;
  const type = document.getElementById("lib-type").value;
  const matter = document.getElementById("lib-matter").value;
  const qs = new URLSearchParams();
  if (type) qs.set("artifact_type", type);
  if (matter) qs.set("matter_id", matter);
  try {
    const r = await apiFetch("/api/workbench/artifacts" + (qs.toString() ? "?" + qs : ""));
    if (!r.ok) return;
    const rows = await r.json();
    if (!rows.length) {
      box.innerHTML = '<p class="muted" style="font-size:.78rem;">No artifacts yet — run any tool above.</p>';
      return;
    }
    box.innerHTML = "";
    rows.forEach(a => {
      const el = document.createElement("div");
      el.className = "wb-tile";
      el.style.cssText = "display:flex;justify-content:space-between;align-items:center;" +
                         "padding:.7rem 1rem;margin-bottom:.5rem;cursor:pointer;";
      const approved = a.review_status === "ADVOCATE_APPROVED";
      el.innerHTML =
        `<div><b style="font-size:.85rem;">${esc(a.label)}</b> ` +
        `<span class="muted" style="font-size:.7rem;">v${a.version} · ${esc(a.confidence)} · ` +
        `${(a.created_at || "").slice(0, 10)}</span></div>` +
        `<span style="font-size:.62rem;font-weight:700;padding:.14rem .5rem;border-radius:12px;` +
        (approved ? "color:#10B981;background:rgba(16,185,129,.12);\">APPROVED"
                  : "color:#F59E0B;background:rgba(245,158,11,.12);\">FOR REVIEW") + "</span>";
      el.onclick = () => openArtifact(a.id);
      box.appendChild(el);
    });
  } catch (_) {}
}

function _fillLibFilters(flows) {
  const ts = document.getElementById("lib-type");
  if (ts && ts.options.length <= 1) {
    flows.forEach(f => {
      const o = document.createElement("option");
      o.value = f.type; o.textContent = f.label;
      ts.appendChild(o);
    });
  }
  const ms = document.getElementById("lib-matter");
  const src = document.getElementById("wa-case");
  if (ms && src && ms.options.length <= 1) {
    Array.from(src.options).slice(1).forEach(o => ms.appendChild(o.cloneNode(true)));
  }
}

async function openArtifact(id) {
  const r = await apiFetch(`/api/workbench/artifacts/${id}`);
  if (!r.ok) { toast("Could not open artifact.", "error"); return; }
  artifact = await r.json();
  session = { id: artifact.session_id, state: "COMPLETE", label: artifact.label,
              questions: [], answers: {}, missing: [], assumptions: [],
              selected_citations: [], uploads: [] };
  document.getElementById("wb-hub").style.display = "none";
  document.getElementById("wb-session").style.display = "";
  document.getElementById("ws-title").textContent = artifact.label + " — v" + artifact.version;
  ["ws-intake", "ws-confirm", "ws-generating", "ws-uploadstep", "ws-argstep"].forEach(x => show(x, false));
  renderArtifact();
  show("ws-artifact", true);
  document.getElementById("ws-state").textContent =
    artifact.review_status === "ADVOCATE_APPROVED" ? "Approved" : "For review";
}

async function exportArtifact(fmt) {
  if (!artifact) return;
  const r = await apiFetch(`/api/workbench/artifacts/${artifact.id}/export`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format: fmt }),
  });
  if (!r.ok) { toast("Export failed.", "error"); return; }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `juriscite_${artifact.artifact_type}_v${artifact.version}.${fmt}`;
  a.click(); URL.revokeObjectURL(a.href);
}

async function saveArtifactToMatter() {
  const caseId = document.getElementById("wa-case").value;
  if (!caseId) { toast("Pick a matter in the dropdown first.", "error"); return; }
  const r = await apiFetch(`/api/workbench/artifacts/${artifact.id}/save-to-matter`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: parseInt(caseId, 10) }),
  });
  const body = await r.json();
  toast(r.ok ? body.message : (body.detail || "Save failed."), r.ok ? "" : "error");
}

async function createTasksFromArtifact() {
  const caseId = document.getElementById("wa-case").value;
  if (!caseId) { toast("Pick a matter in the dropdown first.", "error"); return; }
  const r = await apiFetch(`/api/workbench/artifacts/${artifact.id}/create-tasks`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: parseInt(caseId, 10) }),
  });
  const body = await r.json();
  if (r.ok) toast(body.message + " Opening Court Diary…"), setTimeout(() => location.href = "/diary", 1400);
  else {
    const d = body.detail || {};
    toast(d.message || (typeof d === "string" ? d : "No tasks created."), "error");
    if (d.upgrade_url) setTimeout(() => location.href = d.upgrade_url, 1600);
  }
}

async function approveArtifact() {
  if (!artifact) return;
  if (!confirm("Approve this artifact? This records YOUR approval in the audit log.")) return;
  const r = await apiFetch(`/api/workbench/artifacts/${artifact.id}/approve`, { method: "POST" });
  const body = await r.json();
  if (!r.ok) { toast(body.detail || "Approval failed.", "error"); return; }
  artifact = body;
  document.getElementById("ws-state").textContent = "Approved";
  toast("Approved — recorded in the audit log.");
}

/* ── WB-02: Chat with Case File ── */
let ftUpload = null;   // current upload payload

function openFilePanel() {
  document.getElementById("wb-hub").style.display = "none";
  document.getElementById("wb-filetool").style.display = "";
  const sel = document.getElementById("ft-case");
  if (sel.options.length <= 1) {
    const src = document.getElementById("wa-case");
    Array.from(src.options).slice(1).forEach(o => sel.appendChild(o.cloneNode(true)));
  }
}

function backToHubFromFile() {
  document.getElementById("wb-filetool").style.display = "none";
  document.getElementById("wb-hub").style.display = "";
}

async function uploadCaseFile() {
  const inp = document.getElementById("ft-file");
  if (!inp.files.length) { toast("Choose a PDF or TXT file first.", "error"); return; }
  const btn = document.getElementById("ft-upload-btn");
  btn.disabled = true; btn.textContent = "Extracting…";
  try {
    const fd = new FormData();
    fd.append("file", inp.files[0]);
    const r = await apiFetch("/api/workbench/uploads", { method: "POST", body: fd });
    const body = await r.json();
    if (!r.ok) { toast(body.detail || "Upload failed.", "error"); return; }
    ftUpload = body;
    document.getElementById("ft-name").textContent = body.filename;
    document.getElementById("ft-meta").textContent =
      ` · ${body.page_count} page(s) · auto-deletes ${body.delete_after ? body.delete_after.slice(0, 10) : "—"} unless saved to a matter`;
    document.getElementById("ft-work").style.display = "";
    document.getElementById("ft-thread").innerHTML = "";
    document.getElementById("ft-dates").style.display = "none";
    toast("Extracted. Ask away — answers cite pages from this file only.");
  } finally {
    btn.disabled = false; btn.textContent = "Upload & extract";
  }
}

function _ftBubble(html, cls) {
  const el = document.createElement("div");
  el.style.cssText = "margin:.55rem 0;padding:.6rem .8rem;border-radius:10px;font-size:.84rem;" +
    "line-height:1.6;white-space:pre-wrap;" +
    (cls === "q" ? "background:var(--gold-dim,rgba(200,169,106,.12));"
                 : "background:var(--surface-2);border:1px solid var(--border);");
  el.innerHTML = html;
  document.getElementById("ft-thread").appendChild(el);
  el.scrollIntoView({ block: "nearest" });
  return el;
}

async function askFile() {
  if (!ftUpload) return;
  const q = document.getElementById("ft-q");
  const question = q.value.trim();
  if (question.length < 3) return;
  q.value = "";
  _ftBubble(esc(question), "q");
  const wait = _ftBubble("…", "a");
  const btn = document.getElementById("ft-ask");
  btn.disabled = true;
  try {
    const r = await apiFetch(`/api/workbench/uploads/${ftUpload.id}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const body = await r.json();
    if (!r.ok) {
      const d = body.detail || {};
      wait.innerHTML = esc(d.message || d.error || (typeof d === "string" ? d : "Error."));
      return;
    }
    let html = esc(body.answer);
    if (!body.refused && body.anchors.length) {
      html += '<div style="margin-top:.6rem;">' + body.anchors.slice(0, 4).map(a =>
        `<div style="margin:.35rem 0;padding:.45rem .6rem;border-left:2px solid var(--gold);` +
        `background:var(--surface);border-radius:0 8px 8px 0;font-size:.74rem;color:var(--text-3);">` +
        `<b style="color:var(--gold);">p.${a.page}</b> · ${esc(a.snippet.slice(0, 220))}…</div>`).join("") +
        "</div>";
    }
    wait.innerHTML = html;
  } catch (_) {
    wait.textContent = "Network error — retry.";
  } finally {
    btn.disabled = false;
  }
}

async function generateDates() {
  if (!ftUpload) return;
  const box = document.getElementById("ft-dates");
  box.style.display = ""; box.innerHTML = "Extracting chronology…";
  const r = await apiFetch(`/api/workbench/uploads/${ftUpload.id}/list-of-dates`, { method: "POST" });
  const body = await r.json();
  if (!r.ok) { box.innerHTML = esc(body.detail || "Failed."); return; }
  if (!body.rows.length) {
    box.innerHTML = '<div class="section-label" style="margin-top:0;">List of Dates & Events</div>' +
                    '<p class="muted" style="font-size:.8rem;">No recognisable dates found in this file.</p>';
    return;
  }
  let html = '<div class="section-label" style="margin-top:0;">List of Dates & Events ' +
             `<span class="muted" style="font-weight:400;">(${body.rows.length} entries)</span></div>` +
             '<table style="width:100%;border-collapse:collapse;font-size:.78rem;">' +
             '<tr style="color:var(--text-3);text-align:left;"><th style="padding:.3rem .5rem;">#</th>' +
             '<th style="padding:.3rem .5rem;">Date</th><th style="padding:.3rem .5rem;">Event</th>' +
             '<th style="padding:.3rem .5rem;">Page</th></tr>';
  body.rows.forEach((r2, i) => {
    html += `<tr style="border-top:1px solid var(--border);"><td style="padding:.35rem .5rem;color:var(--text-4);">${i + 1}</td>` +
      `<td style="padding:.35rem .5rem;white-space:nowrap;color:var(--gold);">${esc(r2.date_text)}</td>` +
      `<td style="padding:.35rem .5rem;">${esc(r2.event)}</td>` +
      `<td style="padding:.35rem .5rem;color:var(--text-4);">${r2.page}</td></tr>`;
  });
  html += "</table>" +
    '<div style="margin-top:.8rem;"><button class="btn btn-gold btn-sm" onclick="saveDatesToReview()">' +
    "💾 Save to review queue</button> " +
    '<span class="muted" style="font-size:.72rem;">Approve & export (Word/PDF) from Drafts.</span></div>';
  box.innerHTML = html;
  box._markdown = body.markdown;
}

async function saveDatesToReview() {
  const box = document.getElementById("ft-dates");
  const r = await apiFetch("/api/drafts/", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_type: "workbench_list_of_dates",
                           title: "List of Dates — " + (ftUpload ? ftUpload.filename : "case file"),
                           content: box._markdown || "" }),
  });
  if (r.ok) { toast("Saved for advocate review — opening Drafts…"); setTimeout(() => location.href = "/drafts", 1100); }
  else toast("Save failed.", "error");
}

async function saveFileToMatter() {
  if (!ftUpload) return;
  const caseId = document.getElementById("ft-case").value;
  if (!caseId) { toast("Pick a matter first.", "error"); return; }
  const r = await apiFetch(`/api/workbench/uploads/${ftUpload.id}/save-to-matter`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: parseInt(caseId, 10) }),
  });
  const body = await r.json();
  if (r.ok) {
    document.getElementById("ft-meta").textContent = " · saved to matter — no longer auto-deletes";
    toast(body.message);
  } else toast(body.detail || "Save failed.", "error");
}

/* esc fallback (utils.js provides one on most pages) */
if (typeof esc === "undefined") {
  window.esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
if (typeof apiFetch === "undefined") {
  window.apiFetch = async (url, opts = {}) => {
    const token = localStorage.getItem("access_token");
    opts.headers = { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    const res = await fetch(url, opts);
    if (res.status === 401) {
      localStorage.removeItem("access_token"); localStorage.removeItem("current_user");
      window.location.href = "/login";
    }
    return res;
  };
}
if (typeof toast === "undefined") {
  window.toast = (m) => { try { console.log(m); } catch (_) {} };
}
