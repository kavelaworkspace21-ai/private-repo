/* Drafts review/approval page + version history */

let draftCache = {};     // id -> draft (for "View full")
let versionCache = {};   // id -> [versions] (for view/revert)
let allDraftsList = [];  // full list (for client-side search)

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  loadDrafts();
});

async function loadDrafts() {
  const wrap = document.getElementById("drafts-list");
  let drafts;
  try {
    drafts = await api.get("/api/drafts/");
  } catch (_) {
    wrap.innerHTML = `<div class="drafts-empty">Could not load drafts.</div>`;
    return;
  }
  draftCache = {};
  versionCache = {};
  if (!drafts.length) {
    wrap.innerHTML = `<div class="drafts-empty">No saved drafts yet. Generate one in the
      <a href="/drafting">Drafting Engine</a> and click "Save for review".</div>`;
    return;
  }
  drafts.forEach((d) => (draftCache[d.id] = d));
  allDraftsList = drafts;
  const q = document.getElementById("draft-search");
  renderDraftList(q ? q.value : "");
}

function renderDraftList(filter = "") {
  const wrap = document.getElementById("drafts-list");
  let rows = allDraftsList;
  const f = (filter || "").trim().toLowerCase();
  if (f) rows = rows.filter((d) =>
    (d.title || "").toLowerCase().includes(f) || (d.document_type || "").toLowerCase().includes(f));
  wrap.innerHTML = rows.length
    ? rows.map(renderCard).join("")
    : `<div class="drafts-empty">No drafts match &ldquo;${esc(filter)}&rdquo;.</div>`;
}

function renderCard(d) {
  const approved = d.status === "ADVOCATE_APPROVED";
  const stClass = approved ? "st-approved" : "st-review";
  const stLabel = approved ? "ADVOCATE APPROVED" : "FOR ADVOCATE REVIEW";
  const when = (d.created_at || "").slice(0, 10);
  const approveBtn = approved
    ? ""
    : `<button class="da-btn da-approve" onclick="approveDraft(${d.id})">Approve</button>`;
  return `
    <div class="draft-card" id="draft-${d.id}">
      <div class="draft-card-top">
        <span class="draft-title">${esc(d.title)}</span>
        <span class="badge-status ${stClass}">${stLabel}</span>
      </div>
      <div class="draft-meta">${esc(d.document_type)} &middot; saved ${esc(when)}${
        approved && d.approved_at ? " &middot; approved " + esc(d.approved_at.slice(0, 10)) : ""
      }</div>
      <div class="draft-preview">${esc((d.content || "").slice(0, 600))}</div>
      <div class="draft-actions">
        ${approveBtn}
        <button class="da-btn" onclick="viewCurrent(${d.id})">View full</button>
        <button class="da-btn" onclick="toggleVersions(${d.id})" id="vbtn-${d.id}">Versions</button>
        <button class="da-btn" onclick="deleteDraft(${d.id})">Delete</button>
      </div>
      <div class="versions-panel" id="versions-${d.id}" style="display:none"></div>
    </div>`;
}

async function toggleVersions(id) {
  const panel = document.getElementById(`versions-${id}`);
  const btn = document.getElementById(`vbtn-${id}`);
  if (panel.style.display !== "none") {       // currently open -> close
    panel.style.display = "none";
    btn.textContent = "Versions";
    return;
  }
  panel.innerHTML = `<div class="ver-when" style="padding:.4rem 0">Loading history&hellip;</div>`;
  panel.style.display = "block";
  btn.textContent = "Hide versions";
  let versions;
  try {
    versions = await api.get(`/api/drafts/${id}/versions`);
  } catch (_) {
    panel.innerHTML = `<div class="ver-when" style="padding:.4rem 0">Could not load history.</div>`;
    return;
  }
  versionCache[id] = versions;
  if (!versions.length) {
    panel.innerHTML = `<div class="ver-when" style="padding:.4rem 0">No versions recorded.</div>`;
    return;
  }
  const top = versions[0].version_no;        // list is newest-first → highest = current
  panel.innerHTML = versions.map((v) => renderVersionRow(id, v, v.version_no === top)).join("");
}

function renderVersionRow(draftId, v, isCurrent) {
  const when = (v.created_at || "").slice(0, 10);
  return `
    <div class="ver-row">
      <span class="ver-no">v${v.version_no}</span>
      <span class="ver-when">${esc(when)}</span>
      ${isCurrent ? `<span class="ver-cur">CURRENT</span>` : ""}
      <button class="ver-link" onclick="viewVersion(${draftId},${v.version_no})">View</button>
      ${isCurrent ? "" : `<button class="ver-link" onclick="diffVersion(${draftId},${v.version_no})">Diff vs current</button>`}
      ${isCurrent ? "" : `<button class="ver-link" onclick="revertVersion(${draftId},${v.version_no})">Revert</button>`}
    </div>`;
}

function openVerModal(title, content) {
  document.getElementById("ver-modal-title").textContent = title;
  document.getElementById("ver-modal-body").textContent = content || "(empty)";
  document.getElementById("ver-modal").classList.add("open");
}

function closeVerModal() {
  document.getElementById("ver-modal").classList.remove("open");
}

function viewCurrent(id) {
  const d = draftCache[id];
  if (!d) return;
  openVerModal(`${d.title} — current`, d.content);
}

function viewVersion(draftId, versionNo) {
  const v = (versionCache[draftId] || []).find((x) => x.version_no === versionNo);
  if (!v) return;
  openVerModal(`${v.title} — v${versionNo}`, v.content);
}

/* ── Version diff (line-level LCS) ── */
function lineDiff(oldText, newText) {
  const a = (oldText || "").split("\n"), b = (newText || "").split("\n");
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) { out.push(["ctx", a[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(["del", a[i]]); i++; }
    else { out.push(["add", b[j]]); j++; }
  }
  while (i < m) out.push(["del", a[i++]]);
  while (j < n) out.push(["add", b[j++]]);
  return out;
}

function diffVersion(draftId, versionNo) {
  const v = (versionCache[draftId] || []).find((x) => x.version_no === versionNo);
  const d = draftCache[draftId];
  if (!v || !d) return;
  const sign = { add: "+", del: "−", ctx: " " };
  const body = lineDiff(v.content, d.content)
    .map(([t, line]) => `<span class="diff-${t}">${esc(sign[t] + " " + (line || ""))}</span>`)
    .join("");
  const html =
    `<div class="diff-legend"><b style="color:#b91c1c">−</b> in v${versionNo} only &nbsp; ` +
    `<b style="color:#057a55">+</b> in current only</div>` +
    `<div class="diff-view">${body}</div>`;
  document.getElementById("ver-modal-title").textContent = `${d.title} — v${versionNo} → current (diff)`;
  document.getElementById("ver-modal-body").innerHTML = html;
  document.getElementById("ver-modal").classList.add("open");
}

async function revertVersion(draftId, versionNo) {
  if (!confirm(`Revert to version ${versionNo}? This creates a new version and re-opens the draft for advocate review.`))
    return;
  try {
    await api.post(`/api/drafts/${draftId}/revert/${versionNo}`, {});
    toast(`Reverted to v${versionNo}; draft re-opened for review.`, "success");
    loadDrafts();
  } catch (e) {
    toast("Could not revert (role may be read-only).", "error");
  }
}

async function approveDraft(id) {
  try {
    await api.post(`/api/drafts/${id}/approve`, {});
    toast("Draft approved.", "success");
    loadDrafts();
  } catch (e) {
    toast("Could not approve (role may be read-only).", "error");
  }
}

async function deleteDraft(id) {
  if (!confirm("Delete this draft permanently?")) return;
  try {
    await api.del(`/api/drafts/${id}`);
    toast("Draft deleted.");
    loadDrafts();
  } catch (e) {
    toast("Could not delete draft.", "error");
  }
}

// Close modal on Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeVerModal();
});
