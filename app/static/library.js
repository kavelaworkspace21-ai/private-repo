/* Legal Library — browse acts → sections → section text + grounded summary */

let LIB_ACTS = [];
let searchTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  showActs();
  document.getElementById("lib-search").addEventListener("input", e => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    searchTimer = setTimeout(() => { if (q.length >= 2) runSearch(q); else showActs(); }, 300);
  });
});

function setCrumbs(html) { document.getElementById("crumbs").innerHTML = html; }

/* ── Acts grid ── */
async function showActs() {
  setCrumbs("");
  const view = document.getElementById("lib-view");
  try {
    if (!LIB_ACTS.length) LIB_ACTS = await api.get("/api/library/acts");
  } catch (_) { view.innerHTML = `<div class="muted">Could not load the library.</div>`; return; }
  if (!LIB_ACTS.length) { view.innerHTML = `<div class="muted">No acts loaded yet.</div>`; return; }
  view.innerHTML = `<div class="acts-grid">${LIB_ACTS.map(actCard).join("")}</div>`;
}

function actCard(a) {
  const v = a.source_verified
    ? `<span class="vbadge v-yes">VERIFIED TEXT</span>`
    : `<span class="vbadge v-no">HEADINGS</span>`;
  const rep = a.status === "repealed" ? `<span class="repealed">REPEALED</span>` : "";
  return `<div class="act-card" onclick="showAct('${a.id}')">
    <div class="act-title">${esc(a.title)}</div>
    <div class="act-meta">${v} ${rep} <span>${a.section_count} sections</span></div>
  </div>`;
}

/* ── One act → sections list ── */
async function showAct(actId) {
  const view = document.getElementById("lib-view");
  view.innerHTML = `<div class="muted">Loading sections&hellip;</div>`;
  let act;
  try { act = await api.get(`/api/library/acts/${actId}`); }
  catch (_) { view.innerHTML = `<div class="muted">Could not load act.</div>`; return; }
  setCrumbs(`<a onclick="showActs()">All books</a> &nbsp;›&nbsp; ${esc(act.title)}`);
  const rows = act.sections.map(s => `
    <div class="sec-row" onclick="showSection('${actId}','${encodeURIComponent(s.num)}')">
      <span class="sec-num">${esc(s.num)}</span>
      <span class="sec-title">${esc(s.title || "(untitled)")}</span>
    </div>`).join("");
  view.innerHTML = rows || `<div class="muted">No sections.</div>`;
}

/* ── One section → text + summary ── */
async function showSection(actId, numEnc) {
  const num = decodeURIComponent(numEnc);
  const view = document.getElementById("lib-view");
  view.innerHTML = `<div class="muted">Loading section&hellip;</div>`;
  let sec;
  try { sec = await api.get(`/api/library/acts/${actId}/sections/${numEnc}`); }
  catch (_) { view.innerHTML = `<div class="muted">Could not load section.</div>`; return; }
  setCrumbs(`<a onclick="showActs()">All books</a> &nbsp;›&nbsp; <a onclick="showAct('${actId}')">${esc(sec.act_title)}</a> &nbsp;›&nbsp; s.${esc(sec.num)}`);
  const src = sec.source_url
    ? `<a class="src-link" href="${esc(sec.source_url)}" target="_blank" rel="noopener">Verify at official source ↗</a>` : "";
  view.innerHTML = `
    <div class="sec-detail">
      <h2>Section ${esc(sec.num)} — ${esc(sec.title || "")}</h2>
      <div class="act-meta">${esc(sec.act_title)} (${esc(String(sec.year||""))})
        ${sec.source_verified ? '<span class="vbadge v-yes">VERIFIED TEXT</span>' : '<span class="vbadge v-no">HEADING ONLY</span>'}</div>
      <div class="sec-body">${esc(sec.text || "(No full text stored — load the official PDF to enable verbatim text.)")}</div>
      <div class="sec-actions">
        <button class="lib-btn primary" onclick="summarize('${actId}','${numEnc}')" id="sum-btn">Summarise in plain English</button>
        ${src}
      </div>
      <div id="summary-slot"></div>
    </div>`;
}

async function summarize(actId, numEnc) {
  const slot = document.getElementById("summary-slot");
  const btn = document.getElementById("sum-btn");
  if (btn) { btn.textContent = "Summarising…"; btn.disabled = true; }
  try {
    const r = await api.get(`/api/library/acts/${actId}/sections/${numEnc}/summary`);
    slot.innerHTML = `<div class="summary-box">${esc(r.summary)}
      <div class="disc">${esc(r.disclaimer)}</div></div>`;
  } catch (_) {
    slot.innerHTML = `<div class="summary-box">Could not generate a summary for this section.</div>`;
  } finally {
    if (btn) { btn.textContent = "Summarise in plain English"; btn.disabled = false; }
  }
}

/* ── Search across all acts ── */
async function runSearch(q) {
  const view = document.getElementById("lib-view");
  setCrumbs(`Search results for “${esc(q)}”`);
  let hits;
  try { hits = await api.get(`/api/library/search?q=${encodeURIComponent(q)}`); }
  catch (_) { view.innerHTML = `<div class="muted">Search failed.</div>`; return; }
  if (!hits.length) { view.innerHTML = `<div class="muted">No matches.</div>`; return; }
  view.innerHTML = hits.map(h => `
    <div class="sec-row" onclick="showSection('${h.act_id}','${encodeURIComponent(h.num)}')">
      <span class="sec-num">${esc(h.num)}</span>
      <span class="sec-title">${esc(h.title || "")}<br><span style="font-size:.7rem;color:var(--text-3)">${esc(h.act_title)}</span></span>
    </div>`).join("");
}
