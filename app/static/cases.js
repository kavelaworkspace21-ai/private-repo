/* ── State ── */
let allCases = [];
let allClients = [];
let activeCaseId = null;
let sortCol = 'created_at';
let sortDir = -1;   // -1 = desc, 1 = asc

/* ══════════════════════════════════════
   CASES LIST
══════════════════════════════════════ */
async function loadCases() {
  try {
    [allCases, allClients] = await Promise.all([
      api.get('/api/cases/'),
      api.get('/api/clients/'),
    ]);
    renderCaseStats();
    renderCasesTable();
    populateClientSelect();
  } catch (e) { toast('Failed to load cases', 'error'); }
}

function renderCaseStats() {
  document.getElementById('st-total').textContent    = allCases.length;
  document.getElementById('st-open').textContent     = allCases.filter(c => c.status === 'open').length;
  document.getElementById('st-progress').textContent = allCases.filter(c => c.status === 'in_progress').length;
  document.getElementById('st-closed').textContent   = allCases.filter(c => c.status === 'closed').length;
}

function renderCasesTable(filter = '', status = '') {
  const clientMap = Object.fromEntries(allClients.map(c => [c.id, c.full_name]));
  let rows = allCases;
  if (filter) rows = rows.filter(c =>
    c.title.toLowerCase().includes(filter.toLowerCase()) ||
    (clientMap[c.client_id] || '').toLowerCase().includes(filter.toLowerCase())
  );
  if (status) rows = rows.filter(c => c.status === status);

  rows = rows.slice().sort((a, b) => {
    let x = a[sortCol], y = b[sortCol];
    if (sortCol === 'title') { x = (x || '').toLowerCase(); y = (y || '').toLowerCase(); }
    if (x < y) return -1 * sortDir;
    if (x > y) return 1 * sortDir;
    return 0;
  });

  const tbody = document.getElementById('cases-tbody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No cases found.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(c => `
    <tr style="cursor:pointer" onclick="openCase(${c.id})">
      <td style="color:var(--text-3);font-size:0.8rem">#${c.id}</td>
      <td><strong>${esc(c.title)}</strong></td>
      <td>${esc(clientMap[c.client_id] || '—')}</td>
      <td>${badge(c.status)}</td>
      <td style="color:var(--text-3)">${fmtDate(c.created_at?.slice(0,10))}</td>
      <td><button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();openCase(${c.id})">View →</button></td>
    </tr>`).join('');
}

function populateClientSelect() {
  const sel = document.getElementById('client-select');
  sel.innerHTML = '<option value="">— Select client —</option>' +
    allClients.map(c => `<option value="${c.id}">${esc(c.full_name)} (${esc(c.email)})</option>`).join('');
}

/* Search + filter */
document.getElementById('search').addEventListener('input', e =>
  renderCasesTable(e.target.value, document.getElementById('filter-status').value));
document.getElementById('filter-status').addEventListener('change', e =>
  renderCasesTable(document.getElementById('search').value, e.target.value));

/* Sortable column headers */
document.querySelectorAll('.sortable').forEach(th => th.addEventListener('click', () => {
  const col = th.dataset.col;
  if (sortCol === col) sortDir *= -1; else { sortCol = col; sortDir = 1; }
  renderCasesTable(document.getElementById('search').value, document.getElementById('filter-status').value);
}));

/* New Client form */
document.getElementById('client-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  Object.keys(body).forEach(k => { if (!body[k]) delete body[k]; });
  try {
    await api.post('/api/clients/', body);
    toast('Client created', 'success');
    closeModal('client-modal');
    e.target.reset();
    loadCases();
  } catch { toast('Error creating client', 'error'); }
});

/* New Case form */
document.getElementById('case-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.client_id = parseInt(body.client_id);
  if (!body.description) delete body.description;
  try {
    await api.post('/api/cases/', body);
    toast('Case created', 'success');
    closeModal('case-modal');
    e.target.reset();
    loadCases();
  } catch { toast('Error creating case', 'error'); }
});

/* ══════════════════════════════════════
   CASE DETAIL
══════════════════════════════════════ */
function showList() {
  document.getElementById('list-view').style.display = '';
  document.getElementById('detail-view').style.display = 'none';
  activeCaseId = null;
  loadCases();
}

async function openCase(id) {
  activeCaseId = id;
  document.getElementById('list-view').style.display = 'none';
  document.getElementById('detail-view').style.display = '';

  try {
    const [caseData, clients] = await Promise.all([
      api.get(`/api/cases/${id}`),
      api.get('/api/clients/'),
    ]);
    const client = clients.find(c => c.id === caseData.client_id);

    document.getElementById('detail-title').textContent = caseData.title;
    document.getElementById('detail-status-badge').innerHTML = badge(caseData.status);

    document.getElementById('case-info-block').innerHTML = `
      <div class="info-row"><span class="info-key">Case ID</span><span class="info-value">#${caseData.id}</span></div>
      <div class="info-row"><span class="info-key">Status</span><span class="info-value">${badge(caseData.status)}</span></div>
      <div class="info-row"><span class="info-key">Created</span><span class="info-value">${fmtDate(caseData.created_at?.slice(0,10))}</span></div>
      ${caseData.description ? `<div style="margin-top:.75rem;color:var(--text-2);font-size:.83rem;line-height:1.5">${esc(caseData.description)}</div>` : ''}
    `;

    document.getElementById('client-info-block').innerHTML = client ? `
      <div class="info-row"><span class="info-key">Name</span><span class="info-value" style="font-weight:700">${esc(client.full_name)}</span></div>
      <div class="info-row"><span class="info-key">Email</span><span class="info-value">${esc(client.email)}</span></div>
      ${client.phone ? `<div class="info-row"><span class="info-key">Phone</span><span class="info-value">${esc(client.phone)}</span></div>` : ''}
      ${client.address ? `<div class="info-row"><span class="info-key">Address</span><span class="info-value" style="font-size:.8rem">${esc(client.address)}</span></div>` : ''}
    ` : '<div class="empty-state"><div class="icon">👤</div><p>Client not found</p></div>';

    document.getElementById('edit-case-btn').onclick = () => {
      document.getElementById('status-select').value = caseData.status;
      openModal('status-modal');
    };
    document.getElementById('delete-case-btn').onclick = () => deleteCaseConfirm(id);

    initTabs('.detail-layout');
    await Promise.all([
      loadHearings(id),
      loadFees(id),
      loadTasks(id),
      loadDeadlines(id),
      loadDocuments(id),
      loadDrafts(id),
      loadOpposingCounsel(id),
    ]);
  } catch (e) { toast('Failed to load case', 'error'); }
}

/* Edit status */
document.getElementById('status-form').addEventListener('submit', async e => {
  e.preventDefault();
  const status = document.getElementById('status-select').value;
  try {
    await api.patch(`/api/cases/${activeCaseId}`, { status });
    toast('Status updated', 'success');
    closeModal('status-modal');
    openCase(activeCaseId);
  } catch { toast('Error updating status', 'error'); }
});

async function deleteCaseConfirm(id) {
  if (!confirm('Delete this case and all its data? This cannot be undone.')) return;
  try {
    await api.del(`/api/cases/${id}`);
    toast('Case deleted');
    showList();
  } catch { toast('Error deleting case', 'error'); }
}

/* ── Hearings ── */
async function loadHearings(caseId) {
  const list = await api.get(`/api/hearings/?case_id=${caseId}`);
  const el = document.getElementById('hearings-list');
  if (!list.length) { el.innerHTML = '<div class="empty-state">No hearings yet.</div>'; return; }
  el.innerHTML = list.map(h => `
    <div class="list-item">
      <div class="list-item-body">
        <strong>${esc(h.court_name)}</strong>
        <small>${fmtDate(h.hearing_date)} ${h.judge_name ? '· Judge: ' + esc(h.judge_name) : ''}</small>
        ${h.notes ? `<div style="font-size:0.82rem;margin-top:0.3rem;color:#555">${esc(h.notes)}</div>` : ''}
        ${h.next_hearing_date ? `<small style="color:var(--info)">Next: ${fmtDate(h.next_hearing_date)}</small>` : ''}
      </div>
      <div class="list-item-actions">
        ${badge(h.status)}
        <button class="btn btn-danger btn-sm btn-icon" onclick="deleteHearing(${h.id})">✕</button>
      </div>
    </div>`).join('');
}

document.getElementById('hearing-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = activeCaseId;
  if (!body.next_hearing_date) delete body.next_hearing_date;
  if (!body.judge_name) delete body.judge_name;
  if (!body.notes) delete body.notes;
  try {
    await api.post('/api/hearings/', body);
    toast('Hearing added', 'success');
    closeModal('hearing-modal');
    e.target.reset();
    loadHearings(activeCaseId);
  } catch { toast('Error adding hearing', 'error'); }
});

async function deleteHearing(id) {
  if (!confirm('Delete this hearing?')) return;
  await api.del(`/api/hearings/${id}`);
  toast('Deleted'); loadHearings(activeCaseId);
}

/* ── Fees ── */
async function loadFees(caseId) {
  const [collected, due] = await Promise.all([
    api.get(`/api/fees/collected?case_id=${caseId}`),
    api.get(`/api/fees/due?case_id=${caseId}`),
  ]);

  const totalCol = collected.reduce((s, f) => s + parseFloat(f.amount), 0);
  const totalDue = due.filter(f => !f.is_paid).reduce((s, f) => s + parseFloat(f.amount), 0);
  document.getElementById('total-collected').textContent = fmtAmt(totalCol);
  document.getElementById('total-due').textContent = fmtAmt(totalDue);

  const colEl = document.getElementById('fees-collected-list');
  colEl.innerHTML = collected.length ? collected.map(f => `
    <div class="list-item">
      <div class="list-item-body">
        <strong>${fmtAmt(f.amount)}</strong>
        <small>${fmtDate(f.payment_date)} · ${esc(f.payment_mode.replace('_',' '))}</small>
        ${f.reference_number ? `<small>Ref: ${esc(f.reference_number)}</small>` : ''}
      </div>
      <button class="btn btn-danger btn-sm btn-icon" onclick="deleteFeeCollected(${f.id})">✕</button>
    </div>`).join('') : '<div class="empty-state">No payments recorded.</div>';

  const dueEl = document.getElementById('fees-due-list');
  dueEl.innerHTML = due.length ? due.map(f => `
    <div class="list-item ${f.is_paid ? '' : new Date(f.due_date) < new Date() ? 'overdue-flag' : ''}">
      <div class="list-item-body">
        <strong>${fmtAmt(f.amount)}</strong>
        <small>${esc(f.fee_type.replace('_',' '))} · Due ${fmtDate(f.due_date)}</small>
        ${f.description ? `<small>${esc(f.description)}</small>` : ''}
      </div>
      <div class="list-item-actions">
        ${f.is_paid ? badge('closed') : badge('pending')}
        ${!f.is_paid ? `<button class="btn btn-success btn-sm" onclick="markFeePaid(${f.id})">Mark Paid</button>` : ''}
        <button class="btn btn-danger btn-sm btn-icon" onclick="deleteFeeDue(${f.id})">✕</button>
      </div>
    </div>`).join('') : '<div class="empty-state">No dues recorded.</div>';
}

document.getElementById('fee-collected-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = activeCaseId; body.amount = parseFloat(body.amount);
  if (!body.reference_number) delete body.reference_number;
  if (!body.notes) delete body.notes;
  try {
    await api.post('/api/fees/collected', body);
    toast('Fee recorded', 'success');
    closeModal('fee-collected-modal'); e.target.reset(); loadFees(activeCaseId);
  } catch { toast('Error', 'error'); }
});

document.getElementById('fee-due-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = activeCaseId; body.amount = parseFloat(body.amount);
  if (!body.description) delete body.description;
  try {
    await api.post('/api/fees/due', body);
    toast('Fee due added', 'success');
    closeModal('fee-due-modal'); e.target.reset(); loadFees(activeCaseId);
  } catch { toast('Error', 'error'); }
});

async function markFeePaid(id) {
  await api.patch(`/api/fees/due/${id}`, { is_paid: true });
  toast('Marked as paid', 'success'); loadFees(activeCaseId);
}
async function deleteFeeCollected(id) {
  if (!confirm('Delete this payment?')) return;
  await api.del(`/api/fees/collected/${id}`); toast('Deleted'); loadFees(activeCaseId);
}
async function deleteFeeDue(id) {
  if (!confirm('Delete this fee due entry?')) return;
  await api.del(`/api/fees/due/${id}`); toast('Deleted'); loadFees(activeCaseId);
}

/* ── Documents ── */
async function loadDocuments(caseId) {
  const list = await api.get(`/api/documents/?case_id=${caseId}`);
  const el = document.getElementById('docs-list');
  el.innerHTML = list.length ? list.map(d => `
    <div class="list-item">
      <div class="list-item-body">
        <strong>📄 ${esc(d.filename)}</strong>
        <small>${esc(d.file_path)}</small>
        ${d.notes ? `<small>${esc(d.notes)}</small>` : ''}
      </div>
      <button class="btn btn-danger btn-sm btn-icon" onclick="deleteDoc(${d.id})">✕</button>
    </div>`).join('') : '<div class="empty-state">No documents yet.</div>';
}

document.getElementById('doc-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = activeCaseId;
  if (!body.notes) delete body.notes;
  try {
    await api.post('/api/documents/', body);
    toast('Document added', 'success');
    closeModal('doc-modal'); e.target.reset(); loadDocuments(activeCaseId);
  } catch { toast('Error', 'error'); }
});

async function deleteDoc(id) {
  if (!confirm('Delete this document record?')) return;
  await api.del(`/api/documents/${id}`); toast('Deleted'); loadDocuments(activeCaseId);
}

/* ── Opposing Counsel ── */
async function loadOpposingCounsel(caseId) {
  const list = await api.get(`/api/diary/opposing-counsel?case_id=${caseId}`);
  const el = document.getElementById('oc-list');
  el.innerHTML = list.length ? list.map(o => `
    <div class="list-item">
      <div class="list-item-body">
        <strong>⚖️ ${esc(o.advocate_name)}</strong>
        ${o.bar_registration_number ? `<small>Bar No: ${esc(o.bar_registration_number)}</small>` : ''}
        ${o.firm_name ? `<small>Firm: ${esc(o.firm_name)}</small>` : ''}
        ${o.contact ? `<small>Contact: ${esc(o.contact)}</small>` : ''}
      </div>
      <button class="btn btn-danger btn-sm btn-icon" onclick="deleteOC(${o.id})">✕</button>
    </div>`).join('') : '<div class="empty-state">No opposing counsel recorded.</div>';
}

document.getElementById('oc-form').addEventListener('submit', async e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.case_id = activeCaseId;
  ['bar_registration_number','firm_name','contact'].forEach(k => { if (!body[k]) delete body[k]; });
  try {
    await api.post('/api/diary/opposing-counsel', body);
    toast('Saved', 'success');
    closeModal('oc-modal'); e.target.reset(); loadOpposingCounsel(activeCaseId);
  } catch { toast('Error', 'error'); }
});

async function deleteOC(id) {
  if (!confirm('Delete this record?')) return;
  await api.del(`/api/diary/opposing-counsel/${id}`); toast('Deleted'); loadOpposingCounsel(activeCaseId);
}

/* ── Tasks ── */
async function loadTasks(caseId) {
  const list = await api.get(`/api/diary/tasks?case_id=${caseId}`);
  const el = document.getElementById('tasks-list');
  el.innerHTML = list.length ? list.map(t => `
    <div class="list-item ${!t.is_completed && t.is_overdue ? 'overdue-flag' : ''}">
      <div class="list-item-body">
        <strong style="${t.is_completed ? 'text-decoration:line-through;opacity:.6' : ''}">${esc(t.title)}</strong>
        ${t.due_date ? `<small>Due ${fmtDate(t.due_date)}</small>` : ''}
        ${t.description ? `<small>${esc(t.description)}</small>` : ''}
      </div>
      <div class="list-item-actions">
        ${t.is_completed ? badge('closed') : (t.is_overdue ? badge('pending') : '')}
        ${!t.is_completed ? `<button class="btn btn-success btn-sm" onclick="markTaskDone(${t.id})">Done</button>` : ''}
        <button class="btn btn-danger btn-sm btn-icon" onclick="deleteTask(${t.id})">✕</button>
      </div>
    </div>`).join('') : '<div class="empty-state">No tasks yet.</div>';
}

document.getElementById('task-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  body.case_id = activeCaseId;
  if (!body.due_date) delete body.due_date;
  if (!body.description) delete body.description;
  try {
    await api.post('/api/diary/tasks', body);
    toast('Task added', 'success'); closeModal('task-modal'); e.target.reset(); loadTasks(activeCaseId);
  } catch { toast('Error adding task', 'error'); }
});

async function markTaskDone(id) {
  await api.patch(`/api/diary/tasks/${id}`, { is_completed: true });
  toast('Task completed', 'success'); loadTasks(activeCaseId);
}
async function deleteTask(id) {
  if (!confirm('Delete this task?')) return;
  await api.del(`/api/diary/tasks/${id}`); toast('Deleted'); loadTasks(activeCaseId);
}

/* ── Filing Deadlines ── */
async function loadDeadlines(caseId) {
  const list = await api.get(`/api/diary/deadlines?case_id=${caseId}`);
  const el = document.getElementById('deadlines-list');
  el.innerHTML = list.length ? list.map(d => `
    <div class="list-item ${!d.is_filed && d.is_overdue ? 'overdue-flag' : ''}">
      <div class="list-item-body">
        <strong style="${d.is_filed ? 'text-decoration:line-through;opacity:.6' : ''}">${esc(d.title)}</strong>
        <small>Deadline ${fmtDate(d.deadline_date)}</small>
        ${d.notes ? `<small>${esc(d.notes)}</small>` : ''}
      </div>
      <div class="list-item-actions">
        ${d.is_filed ? badge('closed') : (d.is_overdue ? badge('pending') : '')}
        ${!d.is_filed ? `<button class="btn btn-success btn-sm" onclick="markDeadlineFiled(${d.id})">Filed</button>` : ''}
        <button class="btn btn-danger btn-sm btn-icon" onclick="deleteDeadline(${d.id})">✕</button>
      </div>
    </div>`).join('') : '<div class="empty-state">No deadlines yet.</div>';
}

document.getElementById('deadline-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target).entries());
  body.case_id = activeCaseId;
  if (!body.notes) delete body.notes;
  try {
    await api.post('/api/diary/deadlines', body);
    toast('Deadline added', 'success'); closeModal('deadline-modal'); e.target.reset(); loadDeadlines(activeCaseId);
  } catch { toast('Error adding deadline', 'error'); }
});

async function markDeadlineFiled(id) {
  await api.patch(`/api/diary/deadlines/${id}`, { is_filed: true });
  toast('Marked as filed', 'success'); loadDeadlines(activeCaseId);
}
async function deleteDeadline(id) {
  if (!confirm('Delete this deadline?')) return;
  await api.del(`/api/diary/deadlines/${id}`); toast('Deleted'); loadDeadlines(activeCaseId);
}

/* ── Drafts (linked to this matter) ── */
async function loadDrafts(caseId) {
  const all = await api.get('/api/drafts/');
  const list = all.filter(d => d.case_id === caseId);
  const el = document.getElementById('drafts-list');
  el.innerHTML = list.length ? list.map(d => `
    <div class="list-item">
      <div class="list-item-body">
        <strong>📝 ${esc(d.title)}</strong>
        <small>${esc(d.document_type.replace(/_/g, ' '))} · ${fmtDate((d.created_at || '').slice(0,10))}</small>
      </div>
      <div class="list-item-actions">
        ${d.status === 'ADVOCATE_APPROVED' ? badge('closed') : badge('pending')}
        <a class="btn btn-ghost btn-sm" href="/drafts">Open →</a>
      </div>
    </div>`).join('')
    : '<div class="empty-state">No drafts linked to this matter. <a href="/drafting" style="color:var(--gold)">Generate one →</a></div>';
}

/* ── Boot ── */
loadCases();
