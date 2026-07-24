/* ── State ── */
let allCases = [];

function buildCalStrip(hearingDates = []) {
  const el = document.getElementById('cal-strip');
  if (!el) return;
  const days = ['Su','Mo','Tu','We','Th','Fr','Sa'];
  const today = new Date();
  const todayStr = todayISO();
  let html = '';
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const isToday = iso === todayStr;
    const hasDot = hearingDates.includes(iso);
    // Urgency tiers (Midnight Executive): today=sapphire, tomorrow=emerald,
    // rest of the week (with a hearing)=champagne. Colour = when, not what.
    let urg = "";
    if (isToday) urg = " today";
    else if (i === 1 && hasDot) urg = " urg-tomorrow";
    else if (hasDot) urg = " urg-week";
    html += `<div class="cal-day${urg}">
      <div class="wd">${days[d.getDay()]}</div>
      <div class="dd">${d.getDate()}</div>
      ${hasDot ? '<div class="cal-dot"></div>' : '<div style="height:9px"></div>'}
    </div>`;
  }
  el.innerHTML = html;
}

/* ══════════════════════════════════════
   BOOT
══════════════════════════════════════ */
async function boot() {
  document.getElementById('hero-date').textContent =
    new Date().toLocaleDateString('en-IN', { weekday:'long', day:'numeric', month:'long', year:'numeric' });

  initTabs('#diary-tabs');

  allCases = await api.get('/api/cases/');
  populateCaseSelects();

  await Promise.all([loadHeroStats(), loadTodayTab(), loadEntriesTab(), loadTasksTab(), loadDeadlinesTab()]);

  /* re-load active tab on filter changes */
  document.getElementById('filter-case-entries').addEventListener('change', loadEntriesTab);
  document.getElementById('filter-case-tasks').addEventListener('change', loadTasksTab);
  document.getElementById('pending-only').addEventListener('change', loadTasksTab);
  document.getElementById('filter-case-deadlines').addEventListener('change', loadDeadlinesTab);
  document.getElementById('unfiled-only').addEventListener('change', loadDeadlinesTab);
}

function populateCaseSelects() {
  const opts = '<option value="">All Cases</option>' +
    allCases.map(c => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
  const formOpts = '<option value="">— Select case —</option>' +
    allCases.map(c => `<option value="${c.id}">${esc(c.title)}</option>`).join('');

  document.getElementById('filter-case-entries').innerHTML   = opts;
  document.getElementById('filter-case-tasks').innerHTML     = opts;
  document.getElementById('filter-case-deadlines').innerHTML = opts;
  document.getElementById('entry-case-select').innerHTML     = formOpts;
  document.getElementById('task-case-select').innerHTML      = formOpts;
  document.getElementById('deadline-case-select').innerHTML  = formOpts;
}

const caseTitle = id => allCases.find(c => c.id === id)?.title || `Case #${id}`;

/* ══════════════════════════════════════
   HERO STATS
══════════════════════════════════════ */
async function loadHeroStats() {
  try {
    const [todayData, tasks, deadlines] = await Promise.all([
      api.get('/api/diary/today'),
      api.get('/api/diary/tasks?pending_only=true'),
      api.get('/api/diary/deadlines?unfiled_only=true'),
    ]);
    document.getElementById('hero-today').textContent   = todayData.today.length;
    document.getElementById('hero-week').textContent    = todayData.upcoming.length;
    document.getElementById('hero-tasks').textContent   = tasks.length;
    document.getElementById('hero-overdue').textContent = deadlines.filter(d => d.is_overdue).length;

    const hearingDates = [
      ...todayData.today.map(h => h.hearing_date),
      ...todayData.upcoming.map(h => h.hearing_date),
    ];
    buildCalStrip(hearingDates);
  } catch { /* silently skip if endpoints not ready */ }
}

/* ══════════════════════════════════════
   TODAY TAB
══════════════════════════════════════ */
async function loadTodayTab() {
  try {
    const data = await api.get('/api/diary/today');
    renderHearingCards('today-hearing-list', data.today, true);
    renderHearingCards('week-hearing-list', data.upcoming, false);
  } catch { toast('Failed to load today\'s hearings', 'error'); }
}

function renderHearingCards(elId, items, isToday) {
  const el = document.getElementById(elId);
  if (!items.length) { el.innerHTML = '<div class="empty-state">None.</div>'; return; }
  // Per-item urgency (Midnight Executive): overdue=red · today=sapphire ·
  // tomorrow=emerald · this week=champagne. Colour communicates WHEN, not what.
  const urgClass = (h) => {
    if (isToday) return 'today-flag';
    const t = new Date(); t.setHours(0, 0, 0, 0);
    const d = new Date(h.hearing_date); d.setHours(0, 0, 0, 0);
    const diff = Math.round((d - t) / 86400000);
    if (diff < 0) return 'urg-overdue';
    if (diff === 0) return 'today-flag';
    if (diff === 1) return 'urg-tomorrow';
    if (diff <= 7) return 'urg-week';
    return '';
  };
  el.innerHTML = items.map(h => `
    <div class="list-item ${urgClass(h)}">
      <div class="list-item-body">
        <strong>${esc(h.case_title)}</strong>
        <small><svg class="lc" aria-hidden="true"><use href="/static/lucide.svg#lc-map-pin"/></svg> ${esc(h.court_name)}${h.court_room ? ' · Room ' + esc(h.court_room) : ''}</small>
        <small>${fmtDate(h.hearing_date)}${h.hearing_time ? ' · ' + h.hearing_time.slice(0,5) : ''}</small>
      </div>
      <div class="list-item-actions">
        ${badge(h.stage)} ${badge(h.outcome)}
      </div>
    </div>`).join('');
}

/* ══════════════════════════════════════
   ALL ENTRIES TAB
══════════════════════════════════════ */
async function loadEntriesTab() {
  const caseFilter = document.getElementById('filter-case-entries').value;
  const url = '/api/diary/entries' + (caseFilter ? `?case_id=${caseFilter}` : '');
  try {
    const entries = await api.get(url);
    const tbody = document.getElementById('entries-tbody');
    if (!entries.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No diary entries yet.</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map(e => `
      <tr>
        <td>${fmtDate(e.hearing_date)}</td>
        <td><a href="/cases" onclick="sessionStorage.setItem('openCase',${e.case_id})" style="color:var(--navy);font-weight:500">${esc(caseTitle(e.case_id))}</a></td>
        <td>${esc(e.court_name)}${e.court_room ? ' · ' + esc(e.court_room) : ''}</td>
        <td>${badge(e.stage)}</td>
        <td>${badge(e.outcome)}</td>
        <td style="color:var(--info)">${fmtDate(e.next_date)}</td>
        <td>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteEntry(${e.id})">✕</button>
        </td>
      </tr>`).join('');
  } catch { toast('Failed to load entries', 'error'); }
}

async function deleteEntry(id) {
  if (!confirm('Delete this diary entry?')) return;
  await api.del(`/api/diary/entries/${id}`);
  toast('Deleted');
  loadEntriesTab(); loadHeroStats();
}

/* Entry form */
document.getElementById('entry-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = parseInt(body.case_id);
  ['hearing_time','court_room','adjournment_reason','order_notes','next_date'].forEach(k => {
    if (!body[k]) delete body[k];
  });
  try {
    await api.post('/api/diary/entries', body);
    toast('Entry saved', 'success');
    closeModal('entry-modal'); e.target.reset();
    loadTodayTab(); loadEntriesTab(); loadHeroStats();
  } catch { toast('Error saving entry', 'error'); }
});

/* ══════════════════════════════════════
   TASKS TAB
══════════════════════════════════════ */
async function loadTasksTab() {
  const caseFilter  = document.getElementById('filter-case-tasks').value;
  const pendingOnly = document.getElementById('pending-only').checked;
  let url = '/api/diary/tasks';
  const params = [];
  if (caseFilter)  params.push(`case_id=${caseFilter}`);
  if (pendingOnly) params.push('pending_only=true');
  if (params.length) url += '?' + params.join('&');

  try {
    const tasks = await api.get(url);
    const today = todayISO();
    const el = document.getElementById('tasks-list');
    if (!tasks.length) { el.innerHTML = '<div class="empty-state">No tasks found.</div>'; return; }
    el.innerHTML = tasks.map(t => {
      const overdue = !t.is_completed && t.due_date && t.due_date < today;
      return `
        <div class="list-item ${overdue ? 'overdue-flag' : ''}">
          <div style="margin-right:0.75rem;margin-top:0.1rem">
            <input type="checkbox" ${t.is_completed ? 'checked' : ''} onchange="toggleTask(${t.id}, this.checked)" style="width:18px;height:18px;cursor:pointer"/>
          </div>
          <div class="list-item-body" style="${t.is_completed ? 'opacity:0.5;text-decoration:line-through' : ''}">
            <strong>${esc(t.title)}</strong>
            <small>📁 ${esc(caseTitle(t.case_id))}</small>
            ${t.due_date ? `<small ${overdue ? 'style="color:var(--danger);font-weight:600"' : ''}>Due: ${fmtDate(t.due_date)}${overdue ? ' ⚠ Overdue' : ''}</small>` : ''}
            ${t.description ? `<small>${esc(t.description)}</small>` : ''}
          </div>
          <div class="list-item-actions">
            ${overdue ? badge('overdue') : t.is_completed ? badge('completed') : badge('pending')}
            <button class="btn btn-danger btn-sm btn-icon" onclick="deleteTask(${t.id})">✕</button>
          </div>
        </div>`;
    }).join('');
  } catch { toast('Failed to load tasks', 'error'); }
}

async function toggleTask(id, checked) {
  await api.patch(`/api/diary/tasks/${id}`, { is_completed: checked });
  toast(checked ? 'Task completed ✓' : 'Task re-opened', 'success');
  loadTasksTab(); loadHeroStats();
}

async function deleteTask(id) {
  if (!confirm('Delete this task?')) return;
  await api.del(`/api/diary/tasks/${id}`);
  toast('Deleted'); loadTasksTab(); loadHeroStats();
}

document.getElementById('task-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = parseInt(body.case_id);
  ['due_date','description'].forEach(k => { if (!body[k]) delete body[k]; });
  try {
    await api.post('/api/diary/tasks', body);
    toast('Task added', 'success');
    closeModal('task-modal'); e.target.reset();
    loadTasksTab(); loadHeroStats();
  } catch { toast('Error adding task', 'error'); }
});

/* ══════════════════════════════════════
   DEADLINES TAB
══════════════════════════════════════ */
async function loadDeadlinesTab() {
  const caseFilter  = document.getElementById('filter-case-deadlines').value;
  const unfiledOnly = document.getElementById('unfiled-only').checked;
  let url = '/api/diary/deadlines';
  const params = [];
  if (caseFilter)  params.push(`case_id=${caseFilter}`);
  if (unfiledOnly) params.push('unfiled_only=true');
  if (params.length) url += '?' + params.join('&');

  try {
    const deadlines = await api.get(url);
    const today = todayISO();
    const el = document.getElementById('deadlines-list');
    if (!deadlines.length) { el.innerHTML = '<div class="empty-state">No deadlines found.</div>'; return; }
    el.innerHTML = deadlines.map(d => {
      const overdue = !d.is_filed && d.deadline_date < today;
      return `
        <div class="list-item ${overdue ? 'overdue-flag' : ''}">
          <div class="list-item-body">
            <strong>📋 ${esc(d.title)}</strong>
            <small>📁 ${esc(caseTitle(d.case_id))}</small>
            <small ${overdue ? 'style="color:var(--danger);font-weight:600"' : 'style="color:var(--info)"'}>
              Due: ${fmtDate(d.deadline_date)}${overdue ? ' ⚠ OVERDUE' : ''}
            </small>
            ${d.notes ? `<small>${esc(d.notes)}</small>` : ''}
          </div>
          <div class="list-item-actions">
            ${d.is_filed ? badge('completed') : overdue ? badge('overdue') : badge('pending')}
            ${!d.is_filed ? `<button class="btn btn-success btn-sm" onclick="markFiled(${d.id})">Mark Filed</button>` : ''}
            <button class="btn btn-danger btn-sm btn-icon" onclick="deleteDeadline(${d.id})">✕</button>
          </div>
        </div>`;
    }).join('');
  } catch { toast('Failed to load deadlines', 'error'); }
}

async function markFiled(id) {
  await api.patch(`/api/diary/deadlines/${id}`, { is_filed: true });
  toast('Marked as filed ✓', 'success');
  loadDeadlinesTab(); loadHeroStats();
}

async function deleteDeadline(id) {
  if (!confirm('Delete this deadline?')) return;
  await api.del(`/api/diary/deadlines/${id}`);
  toast('Deleted'); loadDeadlinesTab(); loadHeroStats();
}

document.getElementById('deadline-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = parseInt(body.case_id);
  if (!body.notes) delete body.notes;
  try {
    await api.post('/api/diary/deadlines', body);
    toast('Deadline added', 'success');
    closeModal('deadline-modal'); e.target.reset();
    loadDeadlinesTab(); loadHeroStats();
  } catch { toast('Error adding deadline', 'error'); }
});

/* ── Boot ── */
boot();

/* ── Calendar export (.ics) + eCourts import ── */
async function addDiaryToCalendar() {
  try {
    const token = auth.getToken();
    const res = await fetch("/api/calendar/diary.ics", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) { toast("Could not export calendar", "error"); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "court_diary.ics"; a.click();
    URL.revokeObjectURL(url);
    toast("Calendar downloaded — open it to add to your device calendar.", "success");
  } catch (_) { toast("Calendar export failed", "error"); }
}

async function openEcourtsModal() {
  const sel = document.getElementById("ec-case");
  const statusEl = document.getElementById("ec-status");
  sel.innerHTML = "<option>Loading cases…</option>";
  openModal("ecourts-modal");
  try {
    const [cases, st] = await Promise.all([
      api.get("/api/cases/"),
      api.get("/api/ecourts/status"),
    ]);
    sel.innerHTML = cases.length
      ? cases.map(c => `<option value="${c.id}">${esc(c.title)}</option>`).join("")
      : "<option value=''>No cases — create one first</option>";
    statusEl.innerHTML = st.enabled
      ? "<span style='color:#059669'>eCourts API connected.</span>"
      : "<span style='color:#d97706'>eCourts API not configured yet (set ECOURTS_API_BASE). You can still add hearings manually.</span>";
  } catch (_) { statusEl.textContent = "Could not load."; }
}

async function doEcourtsImport() {
  const caseId = document.getElementById("ec-case").value;
  const cnr = document.getElementById("ec-cnr").value.trim();
  const btn = document.getElementById("ec-go");
  if (!caseId) { toast("Select a case", "error"); return; }
  if (!cnr)    { toast("Enter a CNR number", "error"); return; }
  btn.textContent = "Importing…"; btn.disabled = true;
  try {
    const r = await api.post("/api/ecourts/sync", { case_id: Number(caseId), cnr });
    if (r.status === "ok") {
      toast(`Imported ${r.imported} hearing(s) from eCourts.`, "success");
      closeModal("ecourts-modal");
      if (typeof loadDiary === "function") loadDiary();
      else location.reload();
    } else {
      toast(r.message || "No hearings found for that CNR.", "");
    }
  } catch (e) {
    const msg = String(e.message || "");
    toast(msg.includes("503") ? "eCourts API not configured yet." : "Import failed.", "error");
  } finally { btn.textContent = "Import hearings"; btn.disabled = false; }
}
