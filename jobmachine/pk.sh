#!/bin/bash
# pk.sh <key> -> embed url, resume path, fill JS (one packet for the Chrome worker); SKIP line if the form says hybrid/on-site
cd "$(dirname "$0")"
k=$1; s=$(echo $k|cut -d: -f2); id=$(echo $k|cut -d: -f3)
js=$(python3 fillcall.py $k 2>/dev/null)
if echo "$js" | grep -qiE '"label": "[^"]*(hybrid|in[- ]office|on[- ]?site|commut|relocat[^"]*required)[^"]*", "answer": "No"'; then echo "SKIP hybrid/on-site per form"; python3 jobq.py mark $k skipped "hybrid/on-site per form" >/dev/null; exit 0; fi
echo "URL https://job-boards.greenhouse.io/embed/job_app?for=$s&token=$id"
echo "RESUME $(python3 resume_for.py $k)"
echo "$js" | sed 's#await f(P,4000);await f(P,300)$#await f(P,4000);const r=JSON.parse(await f(P,300));const G=(0,eval)(localStorage.jmGh);const el=document.getElementById("candidate-location");if(el)el.scrollIntoView({block:"center"});await new Promise(r=>setTimeout(r,700));JSON.stringify({empty:G.empty(),file:r.file,cb:[...document.querySelectorAll("\#application-form input[type=checkbox]")].filter(c=>!c.checked).map(c=>(c.labels[0]||{}).textContent.slice(0,50)),loc:!!el})#'
