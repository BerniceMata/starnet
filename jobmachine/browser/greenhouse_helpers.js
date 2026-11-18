// greenhouse_helpers.js - small companions to greenhouse_fill.js for job-boards.greenhouse.io forms.
// ONE expression. Install: localStorage.jmGh = <contents>; use: const G = (0,eval)(localStorage.jmGh);
({
  SCREEN_W: 1512,
  SCREEN_H: 794,
  // Screen coordinates of an element after centering it (wait ~1.5s for the scroll to settle).
  xy(sel, W, H) {
    const el = document.querySelector(sel); if (!el) return null;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    el.scrollIntoView({ block: 'center' });
    const s = (W || this.SCREEN_W) / innerWidth, r = el.getBoundingClientRect();
    return [Math.round((r.x + r.width / 2) * s), Math.round((r.y + r.height / 2) * s + ((H || this.SCREEN_H) - innerHeight * s))];
  },
  // Required labels (marked *) whose input is still empty, including react-select comboboxes.
  empty() {
    const out = [];
    document.querySelectorAll('#application-form label').forEach(l => {
      if (!/\*/.test(l.textContent)) return;
      const id = l.getAttribute('for'); const el = id && document.getElementById(id);
      if (!el || el.type === 'file') return;
      let v = el.value;
      if (el.getAttribute('role') === 'combobox') {
        const c = el.closest('[class*=select__control]') || el.parentElement.parentElement.parentElement;
        v = (c.querySelector('[class*=single-value]') || {}).textContent || '';
      }
      if (!v) out.push(l.textContent.replace(/\s+/g, ' ').trim().slice(0, 70));
    });
    return out;
  },
  // Confirmation check after submit.
  ok() { return /thank you|application (has been )?(submitted|received)|we.ve received/i.test(document.body.innerText) && !document.querySelector('#application-form'); },
})
