// ShiftHub — shared bits (footer year, smooth anchor highlight). No dependencies.
(() => {
  document.querySelectorAll('[data-year]').forEach(el => { el.textContent = String(new Date().getFullYear()); });
})();
