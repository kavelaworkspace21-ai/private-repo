/* ══════════════════════════════════════
   Dashboard — index.html
══════════════════════════════════════ */

function buildCalStrip(containerId, hearingDates = []) {
  const el = document.getElementById(containerId);
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
    // Urgency tiers: today=sapphire, tomorrow=emerald, later this week=champagne
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

let statusChart = null;

function buildStatusChart(cases) {
  const canvas = document.getElementById('status-chart');
  if (!canvas || typeof Chart === 'undefined') return;   // charts are optional — never fatal
  const counts = {
    Open:        cases.filter(c => c.status === 'open').length,
    'In Progress': cases.filter(c => c.status === 'in_progress').length,
    Closed:      cases.filter(c => c.status === 'closed').length,
    Archived:    cases.filter(c => c.status === 'archived').length,
  };
  if (statusChart) statusChart.destroy();
  statusChart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: Object.keys(counts),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: ['#3b82f6','#f59e0b','#10b981','#9ca3af'],
        borderWidth: 0,
        hoverOffset: 6,
      }]
    },
    options: {
      cutout: '70%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { font: { family: 'Inter', size: 11, weight: '600' }, padding: 12, boxWidth: 10, color: '#374151' }
        }
      }
    }
  });
}

let monthlyChart = null;

async function buildMonthlyChart() {
  const canvas = document.getElementById('monthly-hearings-chart');
  if (!canvas || typeof Chart === 'undefined') return;   // charts are optional — never fatal
  let data;
  try {
    data = await api.get('/api/diary/analytics/monthly-hearings?months=6');
  } catch (_) { return; }
  if (monthlyChart) monthlyChart.destroy();
  monthlyChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [{
        label: 'Hearings',
        data: data.counts,
        backgroundColor: '#C8A96A',
        borderRadius: 6,
        maxBarThickness: 38,
      }]
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#9ca3af', font: { family: 'Inter', size: 11, weight: '600' } } },
        y: { beginAtZero: true, ticks: { precision: 0, color: '#9ca3af', font: { family: 'Inter', size: 11 } }, grid: { color: 'rgba(255,255,255,.06)' } }
      }
    }
  });
}

async function loadDashboard() {
  document.getElementById('hero-date').textContent =
    new Date().toLocaleDateString('en-IN', { weekday:'long', day:'numeric', month:'long', year:'numeric' });

  /* Greet with stored name if available */
  try {
    const me = await api.get('/api/auth/me');
    if (me && me.full_name) {
      const el = document.getElementById('user-name');
      if (el) el.textContent = me.full_name.split(' ')[0];
    }
  } catch (_) { /* name is optional */ }

  const today = todayISO();

  try {
    const [todayData, tasks, deadlines, cases] = await Promise.all([
      api.get('/api/diary/today'),
      api.get('/api/diary/tasks?pending_only=true'),
      api.get('/api/diary/deadlines?unfiled_only=true'),
      api.get('/api/cases/'),
    ]);

    /* ── Hero stats ── */
    document.getElementById('stat-today').textContent   = todayData.today.length;
    document.getElementById('stat-week').textContent    = todayData.upcoming.length;
    document.getElementById('stat-tasks').textContent   = tasks.length;
    document.getElementById('stat-overdue').textContent = deadlines.filter(d => d.is_overdue).length;

    /* ── 7-day calendar strip ── */
    const hearingDates = [
      ...todayData.today.map(h => h.hearing_date),
      ...todayData.upcoming.map(h => h.hearing_date),
    ];
    buildCalStrip('cal-strip', hearingDates);

    /* ── Cases stats ── */
    document.getElementById('c-total').textContent    = cases.length;
    document.getElementById('c-open').textContent     = cases.filter(c => c.status === 'open').length;
    document.getElementById('c-progress').textContent = cases.filter(c => c.status === 'in_progress').length;
    document.getElementById('c-closed').textContent   = cases.filter(c => c.status === 'closed').length;

    /* ── Charts (best-effort: a chart error must NEVER abort the rest of the dashboard —
          "Chart is not defined" from the old CDN tag once blanked every panel below) ── */
    try { buildStatusChart(cases); } catch (e) { console.warn('status chart skipped:', e); }
    try { buildMonthlyChart(); }   catch (e) { console.warn('monthly chart skipped:', e); }

    /* ── Recent cases table ── */
    const tbody = document.getElementById('recent-cases-tbody');
    if (tbody) {
      const recent = [...cases].sort((a,b) => b.id - a.id).slice(0, 8);
      if (recent.length) {
        const statusLabel = { open:'Open', in_progress:'In Progress', closed:'Closed', archived:'Archived' };
        const statusClass = { open:'status-open', in_progress:'status-in_progress', closed:'status-closed', archived:'status-archived' };
        tbody.innerHTML = recent.map(c => `
          <tr style="cursor:pointer" onclick="window.location='/cases'">
            <td style="font-weight:600;max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(c.title)}</td>
            <td style="color:var(--text-3)">${esc(c.client_name || '—')}</td>
            <td><span class="status-badge ${statusClass[c.status]||''}">${statusLabel[c.status]||c.status}</span></td>
            <td style="color:var(--text-3);white-space:nowrap">${fmtDate(c.created_at?.slice(0,10)||'')}</td>
          </tr>`).join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="4" style="padding:2rem;text-align:center;color:var(--text-3);font-size:.83rem">No cases yet — <a href="/cases">add one</a></td></tr>';
      }
    }

    /* ── Quick-view: today's hearings ── */
    const qsToday = document.getElementById('qs-today');
    if (todayData.today.length) {
      qsToday.innerHTML = todayData.today.slice(0, 4).map(h => `
        <div style="padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.07)">
          <div style="color:#fff;font-size:.85rem;font-weight:600;letter-spacing:-.01em">${esc(h.case_title)}</div>
          <div style="color:rgba(255,255,255,.35);font-size:.76rem;margin-top:.1rem">${esc(h.court_name)}</div>
        </div>`).join('');
    } else {
      qsToday.innerHTML = '<div style="color:rgba(255,255,255,.3);font-size:.82rem;font-style:italic">No hearings today.</div>';
    }

    /* ── Quick-view: open tasks ── */
    const qsTasks = document.getElementById('qs-tasks');
    if (tasks.length) {
      qsTasks.innerHTML = tasks.slice(0, 4).map(t => {
        const overdue = t.due_date && t.due_date < today;
        return `
          <div style="padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.07)">
            <div style="color:${overdue ? '#DC4C64' : '#fff'};font-size:.85rem;font-weight:600;letter-spacing:-.01em">${esc(t.title)}</div>
            <div style="color:rgba(255,255,255,.35);font-size:.76rem;margin-top:.1rem">${esc(t.case_title)}${t.due_date ? ' · ' + fmtDate(t.due_date) : ''}</div>
          </div>`;
      }).join('');
    } else {
      qsTasks.innerHTML = '<div style="color:rgba(255,255,255,.3);font-size:.82rem;font-style:italic">No pending tasks.</div>';
    }

    /* ── Quick-view: upcoming deadlines ── */
    const qsDl = document.getElementById('qs-deadlines');
    if (deadlines.length) {
      qsDl.innerHTML = deadlines.slice(0, 4).map(d => `
        <div style="padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.07)">
          <div style="color:${d.is_overdue ? '#DC4C64' : '#fff'};font-size:.85rem;font-weight:600;letter-spacing:-.01em">
            ${esc(d.title)}${d.is_overdue ? ' ⚠' : ''}
          </div>
          <div style="color:rgba(255,255,255,.35);font-size:.76rem;margin-top:.1rem">${esc(d.case_title)} · ${fmtDate(d.deadline_date)}</div>
        </div>`).join('');
    } else {
      qsDl.innerHTML = '<div style="color:rgba(255,255,255,.3);font-size:.82rem;font-style:italic">No upcoming deadlines.</div>';
    }

  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

loadDashboard();
