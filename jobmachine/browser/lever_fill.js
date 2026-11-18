// lever_fill.js - in-page helpers for jobs.lever.co/<company>/<id>/apply forms.
//
// ONE JavaScript expression (an object). Install once on the jobs.lever.co origin:
//   localStorage.jmLever = <contents of this file>
//   const L = (0,eval)(localStorage.jmLever); await L.fill(PLAN, EEO);   // PLAN/EEO come from levcall.py
//
// Upload the resume first (file input name="resume"); Lever parses it and pre-fills some fields.
// The location field is an autocomplete: type the city with real keystrokes and pick the suggestion,
// which sets the hidden selectedLocation value. Never submits; L.status() returns the submit button xy.
({
  SCREEN_W: 1512,
  SCREEN_H: 794,

  nrm(s) { return (s || '').toLowerCase().replace(/\s+/g, ' ').trim(); },

  setv(el, v) {
    const pr = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(pr, 'value').set.call(el, v);
    ['input', 'change', 'blur'].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
  },

  missingRequired() {
    return [...document.querySelectorAll('#application-form [required]')]
      .filter(e => (e.type === 'radio' || e.type === 'checkbox') ? !document.querySelector('[name="' + CSS.escape(e.name) + '"]:checked') : !e.value)
      .map(e => e.name).filter((v, i, a) => a.indexOf(v) === i);
  },

  coords(el, W, H) {
    const s = (W || this.SCREEN_W) / innerWidth, r = el.getBoundingClientRect();
    return [Math.round((r.x + r.width / 2) * s), Math.round((r.y + r.height / 2) * s + ((H || this.SCREEN_H) - innerHeight * s))];
  },

  // plan: [{n: input name, t: text|textarea|select|radio|checkbox, a: answer or [answers]}]
  // eeo:  {"eeo[gender]": "option text prefix", ...} - voluntary; pass {} to leave them blank.
  async fill(plan, eeo) {
    const out = { done: [], miss: [] };
    for (const p of plan) {
      if (p.n === 'location') continue;  // autocomplete: needs real typing
      const els = [...document.getElementsByName(p.n)];
      if (!els.length) { out.miss.push('noel ' + p.n); continue; }
      if (p.t === 'radio' || p.t === 'checkbox') {
        for (const w of (Array.isArray(p.a) ? p.a : [p.a])) {
          const el = els.find(e => this.nrm(e.value) === this.nrm(w)) || els.find(e => this.nrm(e.value).startsWith(this.nrm(w)));
          if (el) { if (!el.checked) el.click(); out.done.push(p.n.slice(-10) + '=' + el.value.slice(0, 20)); }
          else out.miss.push(p.n + ' ' + w);
        }
        continue;
      }
      if (p.t === 'select') {
        const s = els[0];
        const o = [...s.options].find(x => this.nrm(x.text) === this.nrm(p.a)) || [...s.options].find(x => this.nrm(x.text).startsWith(this.nrm(p.a)));
        if (o) { this.setv(s, o.value); out.done.push(p.n.slice(-10) + '=' + o.text.slice(0, 20)); } else out.miss.push(p.n + ' ' + p.a);
        continue;
      }
      this.setv(els[0], p.a);
      out.done.push(p.n.slice(-12));
    }
    for (const [n, prefix] of Object.entries(eeo || {})) {
      const s = document.getElementsByName(n)[0];
      const o = s && [...s.options].find(x => x.text.startsWith(prefix));
      if (o) { s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true })); }
    }
    out.req = this.missingRequired();
    out.file = (document.querySelector('.filename') || {}).textContent || '';
    out.resumeStored = !!((document.getElementsByName('resumeStorageId')[0] || {}).value);
    const L = document.querySelector('input[name=location]');
    if (L) { L.scrollIntoView({ block: 'center' }); out.loc = this.coords(L); }
    return JSON.stringify(out);
  },

  // Location/selectedLocation state, still-missing required inputs, and the submit button xy.
  status(W, H) {
    const g = n => (document.getElementsByName(n)[0] || {}).value || '';
    const b = document.getElementById('btn-submit');
    if (b) b.scrollIntoView({ block: 'center' });
    return JSON.stringify({ loc: g('location'), selected: !!g('selectedLocation'), resumeStored: !!g('resumeStorageId'),
      req: this.missingRequired(), sub: b ? this.coords(b, W, H) : null });
  },
})
