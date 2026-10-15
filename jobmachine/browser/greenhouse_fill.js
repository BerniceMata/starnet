// greenhouse_fill.js - fill library for job-boards.greenhouse.io forms (react-select aware).
// ONE expression: an async function (plan, waitMs). Install: localStorage.jm = <contents>;
// run: const f = (0,eval)(localStorage.jm); await f(PLAN, 4000); await f(PLAN, 300);  // PLAN from fillcall.py
// Returns JSON {text, select, empty_required, file}. Never submits.
async(plan,wait)=>{await new Promise(r=>setTimeout(r,wait||1500));
const norm=s=>(s||'').toLowerCase().replace(/\*/g,'').replace(/\s+/g,' ').trim();
const setVal=(el,v)=>{const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,v);['input','change','blur'].forEach(t=>el.dispatchEvent(new Event(t,{bubbles:true})));};
const labelOf=el=>{const l=el.id&&document.querySelector(`label[for="${CSS.escape(el.id)}"]`);return norm(l?l.textContent:(el.getAttribute('aria-label')||''));};
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const uiPick=async(el,want)=>{const ctl=el.closest('[class*=select__control]')||el.closest('[class*=control]');if(!ctl)return null;ctl.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));await new Promise(r=>setTimeout(r,250));const menu=document.querySelector('[class*=select__menu]');if(!menu)return null;const opts=[...menu.querySelectorAll('[class*=select__option]')];let o=opts.find(x=>norm(x.textContent)===norm(want))||opts.find(x=>new RegExp('^'+esc(want),'i').test(x.textContent.trim()))||opts.find(x=>new RegExp(esc(want),'i').test(x.textContent));if(!o){document.body.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));return 'NO MATCH '+want+' in '+opts.slice(0,8).map(x=>x.textContent.trim()).join('|');}o.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));o.click();await new Promise(r=>setTimeout(r,150));return '= '+o.textContent.trim();};
const pick=(el,want)=>{const fk=Object.keys(el).find(k=>k.startsWith('__reactFiber'));let f=el[fk],n=0;while(f&&n<60){const sn=f.stateNode;if(sn&&typeof sn.selectOption==='function'&&sn.props&&sn.props.options){const flat=sn.props.options.flatMap(o=>o.options?o.options:[o]);let opt=flat.find(o=>norm(o.label)===norm(want))||flat.find(o=>new RegExp('^'+esc(want),'i').test(o.label||''))||flat.find(o=>new RegExp(esc(want),'i').test(o.label||''));if(!opt)return 'NO MATCH '+want+' in '+flat.slice(0,8).map(o=>o.label).join('|');sn.selectOption(opt);return '= '+opt.label;}f=f.return;n++;}return 'no select';};
const out={text:[],select:[],empty_required:[]};
for(const el of [...document.querySelectorAll('#application-form input, #application-form textarea')].filter(e=>!['hidden','file','checkbox','radio','submit'].includes(e.type))){
 const lab=labelOf(el); if(!lab)continue;
 const hit=plan.find(p=>norm(p.label)===lab)||plan.find(p=>lab.length>12&&norm(p.label).startsWith(lab.slice(0,50)));
 if(el.getAttribute('role')==='combobox'){
   if(el.id==='country'){const r=await uiPick(el,'United States');out.select.push('country '+(r||pick(el,'United States')));continue;}
   if(hit&&hit.answer){const r=await uiPick(el,hit.answer);out.select.push(lab.slice(0,40)+' '+(r||pick(el,hit.answer)));}
   continue;}
 if(hit&&hit.answer){setVal(el,hit.answer);out.text.push(lab.slice(0,30));}
}
await new Promise(r=>setTimeout(r,400));
document.querySelectorAll('#application-form label').forEach(l=>{if(!/\*/.test(l.textContent))return;const id=l.getAttribute('for');const el=id&&document.getElementById(id);if(!el||el.type==='file')return;let v=el.value;if(el.getAttribute('role')==='combobox'){const c=el.closest('[class*=select__control]')||el.parentElement.parentElement.parentElement;v=(c.querySelector('[class*=single-value]')||{}).textContent||'';}if(!v)out.empty_required.push(norm(l.textContent).slice(0,70)+' #'+id);});
out.file=[...document.querySelectorAll('#application-form [class*=filename]')].map(e=>e.textContent.trim()).join(',');
return JSON.stringify(out);}