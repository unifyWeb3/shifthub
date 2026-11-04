// Vercel serverless proxy: GET /api/dashboard → n8n webhook (GET /webhook/shifthub-dashboard).
// If N8N_WEBHOOK_BASE is not set, returns a clearly-labelled demo payload (offline preview).
const N8N_BASE = (process.env.N8N_WEBHOOK_BASE || '').replace(/\/+$/, '');

function demoPayload() {
  const now = new Date();
  const minsUntil = (dateStr, timeStr) => Math.round((new Date(`${dateStr}T${timeStr}:00`) - now) / 60000);
  const pad = (n) => String(n).padStart(2, '0');
  const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const inHours = (h) => new Date(now.getTime() + h * 3600 * 1000);
  const today = new Date(now);
  const tomorrow = new Date(now.getTime() + 86400000);
  const in6d = new Date(now.getTime() + 6 * 86400000);
  const demoStart = inHours(3.1); // the '3-hour mark' unconfirmed shift
  const demoEnd = inHours(15);

  const upcoming = [
    { shiftId: 'SHIFT-DEMO-01', date: isoDate(today), startTime: hhmm(demoStart), endTime: hhmm(demoEnd),
      ward: 'ICU', role: 'Nurse', requiredCount: 2, confirmed: 0, pending: 2, declined: 0,
      staff: [{ name: 'Ngozi Eze', status: 'PENDING', role: 'Nurse' }, { name: 'Kemi Adeyemi', status: 'PENDING', role: 'Nurse' }],
      missingCount: 2, understaffed: true, minutesUntilStart: Math.round((demoStart - now) / 60000), atRisk: true },
    { shiftId: 'SHIFT-DEMO-02', date: isoDate(tomorrow), startTime: '07:00', endTime: '19:00',
      ward: 'Ward A (Medical)', role: 'Nurse', requiredCount: 2, confirmed: 1, pending: 1, declined: 0,
      staff: [{ name: 'Adaeze Nnamdi', status: 'CONFIRMED', role: 'Nurse' }, { name: 'Fatima Bello', status: 'PENDING', role: 'Nurse' }],
      missingCount: 1, understaffed: true, minutesUntilStart: minsUntil(isoDate(tomorrow), '07:00'), atRisk: false },
    { shiftId: 'SHIFT-DEMO-03', date: isoDate(tomorrow), startTime: '08:00', endTime: '16:00',
      ward: 'Outpatient', role: 'Pharmacist', requiredCount: 1, confirmed: 1, pending: 0, declined: 0,
      staff: [{ name: 'Halima Sule', status: 'CONFIRMED', role: 'Pharmacist' }],
      missingCount: 0, understaffed: false, minutesUntilStart: minsUntil(isoDate(tomorrow), '08:00'), atRisk: false },
    { shiftId: 'SHIFT-DEMO-04', date: isoDate(in6d), startTime: '09:00', endTime: '17:00',
      ward: 'Ward B (Surgical)', role: 'Care Assistant', requiredCount: 2, confirmed: 0, pending: 2, declined: 0,
      staff: [{ name: 'Emeka Obi', status: 'PENDING', role: 'Care Assistant' }, { name: 'Chibuike Okoro', status: 'PENDING', role: 'Care Assistant' }],
      missingCount: 2, understaffed: true, minutesUntilStart: minsUntil(isoDate(in6d), '09:00'), atRisk: false },
  ];

  const requiredSlots = upcoming.reduce((a, s) => a + s.requiredCount, 0);
  const confirmedSlots = upcoming.reduce((a, s) => a + Math.min(s.confirmed, s.requiredCount), 0);
  const understaffedShifts = upcoming.filter((s) => s.understaffed).length;
  const atRisk = upcoming.filter((s) => s.atRisk);

  return {
    facility: 'Federal Medical Centre (SIWES Demo)',
    generatedAt: now.toISOString(),
    timezone: 'Africa/Lagos',
    windowDays: 14,
    demo: true,
    stats: {
      shifts: upcoming.length,
      requiredSlots,
      confirmedSlots,
      coverageRate: requiredSlots ? Math.round((confirmedSlots / requiredSlots) * 1000) / 10 : 100,
      pendingConfirmations: upcoming.reduce((a, s) => a + s.pending, 0),
      understaffedShifts,
      atRiskShifts: atRisk.length,
    },
    upcoming,
    atRisk,
  };
}

module.exports = async (req, res) => {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method_not_allowed' });
    return;
  }
  if (!N8N_BASE) {
    res.status(200).json(demoPayload());
    return;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  try {
    const upstream = await fetch(`${N8N_BASE}/webhook/shifthub-dashboard`, {
      method: 'GET',
      headers: { accept: 'application/json' },
      signal: ctrl.signal,
    });
    const text = await upstream.text();
    res.setHeader('content-type', 'application/json; charset=utf-8');
    res.setHeader('cache-control', 'no-store');
    res.status(upstream.status >= 200 && upstream.status < 300 ? 200 : 502).send(text);
  } catch (err) {
    res.status(200).json({ ...demoPayload(), demo: true, upstreamError: String(err && err.message || err).slice(0, 120) });
  } finally {
    clearTimeout(timer);
  }
};
