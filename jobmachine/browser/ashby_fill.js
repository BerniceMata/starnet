// ashby_fill.js - in-page helpers for jobs.ashbyhq.com application forms.
//
// The file is ONE JavaScript expression (an object of functions). Install it once per browser profile
// on the jobs.ashbyhq.com origin, then load it at the very top of each script:
//
//   localStorage.jmAshby = <contents of this file>          // install (one time)
//   const J = (0,eval)(localStorage.jmAshby);                // load: must run BEFORE any await (Ashby CSP)
//   await J.fill(PLAN); await J.fill(PLAN);                  // PLAN comes from ashcall.py; run twice
//
// It never submits. Fields React will not accept from script (Yes buttons, location comboboxes, some
// email/phone inputs) are reported back so the driver can do a real click / real typing at J.xy(...).
// Screen coordinates assume a screenshot frame of SCREEN_W x SCREEN_H; pass your own if different.
({
  SCREEN_W: 1512,
  SCREEN_H: 794,

  norm(s) { return (s || '').replace(/[\u{1F300}-\u{1FAFF}☀-➿]/gu, '').replace(/\*/g, '').replace(/\s+/g, ' ').trim().toLowerCase(); },

  entries() { return [...document.querySelectorAll('[class*=fieldEntry]')]; },

  labelOf(e) { const l = e.querySelector('label'); return this.norm(l ? l.textContent : ''); },

  // Find the field entry for a plan item: by input name (Ashby field path) first, then by label prefix.
  find(p) {
    if (p.path) {
      const el = document.querySelector(`[name="${CSS.escape(p.path)}"]`);
      if (el) return el.closest('[class*=fieldEntry]');
    }
    if (!p.title) return null;  // an untitled item must never match by label (it would hit "Name")
    const want = this.norm(p.title).slice(0, 40);
    return this.entries().find(e => this.labelOf(e).startsWith(want)) || null;
  },

  setText(el, v) {
    el.focus();
    if (el.select) el.select();
    const ok = document.execCommand && document.execCommand('insertText', false, v);
    if (!ok || el.value !== v) {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      ['input', 'change'].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
    }
    el.blur();
  },

  async fill(plan) {
    const done = [], skipped = [];
    for (const p of plan) {
      const e = this.find(p);
      if (!e) { skipped.push('nofield ' + (p.title || p.path || '').slice(0, 30)); continue; }
      const tag = (p.title || '').slice(0, 20);
      const combo = e.querySelector('input[role=combobox]');
      const buttons = [...e.querySelectorAll('button')].filter(b => /^(yes|no)$/i.test(b.textContent.trim()));
      if (combo || p.type === 'Location') { done.push('COMBO ' + (p.title || '').slice(0, 30)); continue; }
      if (buttons.length) {
        const b = buttons.find(x => x.textContent.trim().toLowerCase() === String(p.answer).toLowerCase());
        if (!b) { skipped.push('noopt ' + tag); continue; }
        if (/yes/i.test(p.answer)) { b.setAttribute('data-jmyes', '1'); done.push('YES-REAL'); continue; }
        if (!/_active/.test(b.className)) b.click();
        done.push('btn ' + b.textContent.trim());
        continue;
      }
      const choices = [...e.querySelectorAll('input[type=radio],input[type=checkbox]')];
      if (choices.length) {
        const wants = Array.isArray(p.answer) ? p.answer : [p.answer];
        for (const w of wants) {
          const lab = [...e.querySelectorAll('label')].slice(1).find(l => this.norm(l.textContent).startsWith(this.norm(w).slice(0, 25)));
          if (!lab) { skipped.push('noopt ' + String(w).slice(0, 25)); continue; }
          const inp = lab.querySelector('input') || document.getElementById(lab.getAttribute('for')) || lab.previousElementSibling;
          if (!(inp && inp.checked)) lab.click();
          done.push('opt ' + String(w).slice(0, 20));
        }
        continue;
      }
      const el = e.querySelector('textarea, input:not([type=file]):not([type=hidden]):not([type=radio]):not([type=checkbox])');
      if (!el) { skipped.push('noinput ' + tag); continue; }
      this.setText(el, String(p.answer));
      done.push('txt ' + tag);
    }
    await new Promise(r => setTimeout(r, 300));
    return JSON.stringify({ done, skipped, empty: this.empty() });
  },

  // Required entries that still look unanswered.
  empty() {
    return this.entries().filter(e => {
      const l = e.querySelector('label');
      if (!l || !(/\*/.test(l.textContent) || /required/i.test(l.className))) return false;
      if (e.querySelector('input[type=file]')) return false;
      const filled = [...e.querySelectorAll('textarea, input:not([type=hidden])')].some(i =>
        (i.type === 'radio' || i.type === 'checkbox') ? i.checked : !!i.value);
      const active = [...e.querySelectorAll('button')].some(b => /_active/.test(b.className));
      return !(filled || active);
    }).map(e => this.labelOf(e).slice(0, 60));
  },

  // Screen coordinates (in the screenshot frame) of an element, after centering it.
  coords(el, W, H) {
    const s = (W || this.SCREEN_W) / innerWidth, r = el.getBoundingClientRect();
    return [Math.round((r.x + r.width / 2) * s), Math.round((r.y + r.height / 2) * s + ((H || this.SCREEN_H) - innerHeight * s)), Math.round(r.width * s)];
  },

  center(el) {
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    el.scrollIntoView({ block: 'center' });
  },

  // After calling, wait ~1.5s (scroll settles) before using the coordinates.
  xy(sel, W, H) { const el = document.querySelector(sel); if (!el) return null; this.center(el); return this.coords(el, W, H); },

  // The input of the entry whose label starts with `label` (for real typing / combobox clicks).
  fix(label, W, H) {
    const want = this.norm(label).slice(0, 40);
    const e = this.entries().find(x => this.labelOf(x).startsWith(want));
    if (!e) return null;
    const el = e.querySelector('textarea, input:not([type=file]):not([type=hidden])');
    this.center(el); return this.coords(el, W, H);
  },

  // The i-th Yes button marked by fill() as needing a real click.
  yesN(i, W, H) {
    const b = document.querySelectorAll('[data-jmyes]')[i || 0];
    if (!b) return null;
    this.center(b); return this.coords(b, W, H);
  },

  // A radio/checkbox option (label text matching `ore`) in the entry whose text matches `qre`.
  opt(qre, ore, W, H) {
    const e = this.entries().find(x => new RegExp(qre, 'i').test(x.textContent));
    if (!e) return 'noq';
    const labs = [...e.querySelectorAll('label')].slice(1);
    const lab = labs.find(l => new RegExp(ore, 'i').test(l.textContent));
    if (!lab) return 'noopt ' + labs.map(l => l.textContent.slice(0, 30)).join('|');
    this.center(lab);
    const s = (W || this.SCREEN_W) / innerWidth, r = lab.getBoundingClientRect();
    return [Math.round((r.x + 12) * s), Math.round((r.y + r.height / 2) * s + ((H || this.SCREEN_H) - innerHeight * s))];
  },

  // Strict submission check: a confirmation message AND no form left on the page.
  ok() {
    const t = document.body.innerText;
    const miss = [...document.querySelectorAll('*')].filter(x => x.children.length === 0 && /Missing entry for required field/i.test(x.textContent)).map(x => x.textContent.trim().slice(0, 100));
    const ok = /success|thank you|received your application/i.test(t) && !document.querySelector('[class*=fieldEntry]') && !/submit application/i.test(t);
    return { ok, miss };
  },
})
