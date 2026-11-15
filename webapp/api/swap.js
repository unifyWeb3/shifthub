// Vercel serverless proxy: POST /api/swap → n8n webhook (POST /webhook/swap-request).
// The n8n base URL is resolved at request time (see _n8n-base.js); if it cannot be
// resolved, the response is a clearly-labelled demo acknowledgement (nothing is persisted).
const { resolveN8NBase } = require('./_n8n-base');

const REQUIRED = ['name', 'contact', 'shiftDate', 'ward', 'reason'];

function readBody(req) {
  if (req.body && typeof req.body === 'object' && !Buffer.isBuffer(req.body)) return req.body;
  if (typeof req.body === 'string') {
    return Object.fromEntries(new URLSearchParams(req.body).entries());
  }
  return {};
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).json({ ok: false, error: 'method_not_allowed', message: 'Use POST for swap requests.' });
    return;
  }

  const body = readBody(req);
  const missing = REQUIRED.filter((f) => !String(body[f] ?? '').trim());
  if (missing.length) {
    res.status(400).json({
      ok: false,
      error: 'validation_error',
      message: `Missing required fields: ${missing.join(', ')}`,
    });
    return;
  }

  const N8N_BASE = await resolveN8NBase();
  if (!N8N_BASE) {
    res.status(200).json({
      ok: true,
      demo: true,
      requestId: 'DEMO-' + Date.now().toString(36).toUpperCase(),
      message: 'Offline demo mode: the request was accepted but NOT persisted. The n8n public URL could not be resolved.',
    });
    return;
  }

  const payload = new URLSearchParams();
  for (const [k, v] of Object.entries(body)) {
    if (v !== undefined && v !== null) payload.append(k, String(v));
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 12000);
  try {
    const upstream = await fetch(`${N8N_BASE}/webhook/swap-request`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
      body: payload.toString(),
      signal: ctrl.signal,
    });
    const text = await upstream.text();
    res.setHeader('content-type', 'application/json; charset=utf-8');
    res.setHeader('cache-control', 'no-store');
    try {
      const parsed = JSON.parse(text);
      res.status(upstream.ok ? 200 : upstream.status).json(parsed);
    } catch (_) {
      res.status(upstream.ok ? 200 : 502).json({
        ok: upstream.ok,
        message: upstream.ok ? 'Swap request accepted.' : 'The n8n webhook returned an unexpected response.',
        raw: text.slice(0, 200),
      });
    }
  } catch (err) {
    res.status(502).json({
      ok: false,
      error: 'upstream_unreachable',
      message: 'Could not reach the n8n swap webhook. Phone the ward directly and try again later.',
      detail: String((err && err.message) || err).slice(0, 140),
    });
  } finally {
    clearTimeout(timer);
  }
};
