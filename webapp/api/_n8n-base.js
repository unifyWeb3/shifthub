// Resolves the public n8n base URL used by the proxy functions.
//
// The public URL is a Cloudflare quick tunnel, and a quick tunnel gets a new
// random hostname every time it restarts. Baking that URL into a Vercel
// environment variable means the web app breaks (and needs a redeploy) every
// time the tunnel restarts.
//
// So the URL lives in ONE place in the repo - webapp/n8n-url.txt - and this
// module reads it at request time. `scripts/sync-tunnel-url.py` writes that
// file whenever the tunnel URL changes; a git push is enough to publish it,
// no Vercel redeploy needed.
//
// Order:
//   1. webapp/n8n-url.txt on GitHub (always the freshest value)
//   2. N8N_WEBHOOK_BASE (Vercel environment variable, fallback)
//   3. '' -> the caller falls back to the clearly-labelled offline demo
const URL_FILE =
  'https://raw.githubusercontent.com/unifyWeb3/shifthub/main/webapp/n8n-url.txt';

let cached = { value: '', at: 0 };
const TTL_MS = 20000;

function clean(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

async function resolveN8NBase() {
  const now = Date.now();
  if (cached.value && now - cached.at < TTL_MS) return cached.value;

  try {
    const response = await fetch(`${URL_FILE}?t=${now}`, {
      headers: { accept: 'text/plain' },
      cache: 'no-store',
      signal: AbortSignal.timeout(4000),
    });
    if (response.ok) {
      const value = clean(await response.text());
      if (value) {
        cached = { value, at: now };
        return value;
      }
    }
  } catch (_) {
    // fall through to the environment variable
  }

  const fromEnv = clean(process.env.N8N_WEBHOOK_BASE);
  if (fromEnv) {
    cached = { value: fromEnv, at: now };
    return fromEnv;
  }
  return '';
}

module.exports = { resolveN8NBase };
