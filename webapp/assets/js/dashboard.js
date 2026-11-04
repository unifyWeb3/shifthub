// ShiftHub — supervisor dashboard. Fetches /api/dashboard (Vercel proxy → n8n webhook),
// renders coverage stats + upcoming shifts, refreshes every 30s.
(() => {
  const REFRESH_SECONDS = 30;
  const $ = (id) => document.getElementById(id);
  let secondsLeft = REFRESH_SECONDS;
  let timer = null;

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtDate = (iso) => {
    try {
      const d = new Date(iso + 'T00:00:00');
      return d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });
    } catch { return String(iso); }
  };
  const fmtIso = (iso) => {
    try { return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); } catch { return String(iso); }
  };

  function coverageClass(rate, understaffed) {
    if (understaffed || rate < 50) return 'low';
    if (rate < 100) return 'mid';
    return '';
  }

  function render(data) {
    const stats = data.stats || {};
    const shifts = Array.isArray(data.upcoming) ? data.upcoming : [];
    const atRisk = Array.isArray(data.atRisk) ? data.atRisk : [];

    $('facilityName').textContent = data.facility || 'ShiftHub Rota';
    $('generatedAt').textContent = 'updated ' + fmtIso(data.generatedAt || new Date().toISOString());

    $('coverage').textContent = typeof stats.coverageRate === 'number' ? stats.coverageRate.toFixed(1) : '–';
    $('statShifts').textContent = stats.shifts ?? '–';
    $('statConfirmed').textContent = `${stats.confirmedSlots ?? '–'}/${stats.requiredSlots ?? '–'}`;
    $('statPending').textContent = stats.pendingConfirmations ?? '–';
    $('statUnderstaffed').textContent = stats.understaffedShifts ?? '–';

    $('demoBanner').hidden = !data.demo;

    const riskBanner = $('riskBanner');
    if (atRisk.length > 0) {
      $('riskCount').textContent = atRisk.length;
      $('riskList').innerHTML = atRisk.slice(0, 5).map(r =>
        `<li>${esc(r.ward)} · ${esc(fmtDate(r.date))} ${esc(r.startTime)} — starts in ~${Math.max(0, r.minutesUntilStart ?? 0)} min, ${r.pending} unconfirmed</li>`
      ).join('');
      riskBanner.hidden = false;
    } else {
      riskBanner.hidden = true;
    }

    const tbody = $('shiftsBody');
    if (!shifts.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--ink-soft); padding: 2rem;">No shifts in the next 14 days — seed the rota or check the Google Sheet.</td></tr>';
      return;
    }

    tbody.innerHTML = shifts.map((s) => {
      const req = Number(s.requiredCount) || 1;
      const confirmed = Number(s.confirmed) || 0;
      const pct = Math.min(100, Math.round((Math.min(confirmed, req) / req) * 100));
      const under = !!s.understaffed;
      const pill = under
        ? '<span class="pill pill-under">UNDERSTAFFED</span>'
        : (confirmed >= req
          ? '<span class="pill pill-full">FULLY COVERED</span>'
          : '<span class="pill pill-pending">PENDING YES</span>');
      const confirmedPill = confirmed > 0 ? `<span class="pill pill-confirmed">${confirmed} confirmed</span>` : '';
      return `<tr class="${under ? 'understaffed' : ''}">
        <td><strong>${esc(fmtDate(s.date))}</strong></td>
        <td class="mono">${esc(s.startTime)}–${esc(s.endTime)}</td>
        <td>${esc(s.ward)}<br><span style="color: var(--ink-soft); font-size: .78rem;">${esc(s.role)} · ${esc(s.shiftId)}</span></td>
        <td><div style="display:flex; align-items:center; gap:.55rem;"><div class="progress ${coverageClass(pct, under)}"><i style="width:${pct}%"></i></div><span class="mono" style="font-size:.75rem;">${confirmed}/${req}</span></div></td>
        <td>${pill} ${confirmedPill}</td>
      </tr>`;
    }).join('');
  }

  function renderFailure(err) {
    $('facilityName').textContent = 'Dashboard unavailable';
    $('generatedAt').textContent = 'could not load rota';
    $('shiftsBody').innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--red);">Failed to load dashboard data.<br><span class="mono" style="font-size:.75rem;">${esc(String(err).slice(0, 140))}</span></td></tr>`;
  }

  async function refresh() {
    try {
      const res = await fetch('/api/dashboard', { headers: { 'accept': 'application/json' } });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      render(data);
    } catch (err) {
      renderFailure(err);
    } finally {
      secondsLeft = REFRESH_SECONDS;
    }
  }

  function tick() {
    secondsLeft -= 1;
    if (secondsLeft <= 0) { refresh(); return; }
    $('countdown').textContent = String(secondsLeft);
  }

  refresh();
  timer = setInterval(tick, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('beforeunload', () => clearInterval(timer));
})();
