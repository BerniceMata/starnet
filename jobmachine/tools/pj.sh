#!/bin/bash
# pj.sh <key> -> URL, RESUME, and one JS that dismisses Simplify, fills, sets Location and School by async search, and reports empties
mkdir -p ${JM_SCRATCH:-/tmp/jm}
cd /home/claude/jm/jobmachine
out=$(bash pk.sh $1) || { echo "$out"; exit 1; }
echo "$out" | grep -q '^SKIP' && { echo "$out"; exit 0; }
echo "$out" | sed -n 1,2p
plan=$(echo "$out" | sed -n 3p | sed 's/;const f=(0,eval).*//')
cat <<JS
for(const r of [...document.querySelectorAll('*')].filter(e=>e.shadowRoot).map(e=>e.shadowRoot)){const b=[...r.querySelectorAll('button')].find(b=>/^cancel\$/i.test(b.textContent.trim()));if(b){b.click();break}}
$plan;const f=(0,eval)(localStorage.jm);await f(P,4000);const r=JSON.parse(await f(P,300));
const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;const W=ms=>new Promise(x=>setTimeout(x,ms));
async function srch(el,q,rx){el.focus();set.call(el,q);el.dispatchEvent(new Event('input',{bubbles:true}));for(let i=0;i<10;i++){await W(500);const o=[...document.querySelectorAll('[class*=option]')].find(x=>rx.test(x.textContent.trim()));if(o){o.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));o.click();await W(300);return o.textContent.trim()}}return 'none'}
const res={};
for(const s of document.querySelectorAll('input[id^=school--]'))res.school=await srch(s,'University of Texas',/^University of Texas - Dallas\$/);
const loc=document.getElementById('candidate-location');if(loc){loc.scrollIntoView({block:'center'});loc.focus()};const G=(0,eval)(localStorage.jmGh);JSON.stringify({res,empty:G.empty(),file:r.file,sel:r.select,cb:[...document.querySelectorAll('#application-form input[type=checkbox]')].filter(c=>!c.checked).map(c=>(c.labels[0]||{}).textContent.slice(0,60))})
JS
