// ShiftHub — swap request form → POST /api/swap (Vercel proxy → n8n webhook).
(() => {
  const form = document.getElementById('swapForm');
  if (!form) return;
  const status = document.getElementById('formStatus');
  const submitBtn = document.getElementById('submitBtn');

  const show = (kind, html) => {
    status.className = 'form-status ' + kind;
    status.innerHTML = html;
    status.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  // default the shift date to tomorrow — the common case for swaps
  const dateInput = form.querySelector('#shiftDate');
  if (dateInput && !dateInput.value) {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    dateInput.value = d.toISOString().slice(0, 10);
    dateInput.min = d.toISOString().slice(0, 10);
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const data = Object.fromEntries(new FormData(form).entries());
    const body = new URLSearchParams(data).toString();

    submitBtn.disabled = true;
    submitBtn.style.opacity = '0.7';

    try {
      const res = await fetch('/api/swap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      let payload = {};
      try { payload = await res.json(); } catch (_) { /* non-JSON */ }

      if (res.ok && payload.ok !== false) {
        const id = payload.requestId ? ` <span class="mono">${String(payload.requestId)}</span>` : '';
        const offline = payload.demo ? '<br><em>Offline demo mode — this request was NOT persisted (n8n webhook not configured).</em>' : '';
        show('ok', `<strong>Request received.</strong> Reference${id}. The supervisor has been notified on email and Telegram.${offline}`);
        form.querySelectorAll('input, textarea').forEach(el => { el.value = ''; });
      } else {
        const msg = payload && payload.message ? payload.message : `Request failed (HTTP ${res.status}).`;
        show('err', `<strong>Not sent.</strong> ${msg}`);
      }
    } catch (err) {
      show('err', `<strong>Network error.</strong> Could not reach the swap service. Try again, or phone the ward directly. <span class="mono">${String(err).slice(0, 80)}</span>`);
    } finally {
      submitBtn.disabled = false;
      submitBtn.style.opacity = '1';
    }
  });
})();
