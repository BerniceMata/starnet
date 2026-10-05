#!/usr/bin/env python3
"""ashcall.py <ashby:slug:id> -> one in-page JS program that fills an Ashby form with browser/ashby_fill.js
(installed as localStorage.jmAshby), plus an audit line on stderr listing unknown questions and blockers."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from profile import OVERRIDES  # noqa: E402
k = sys.argv[1]
d = json.loads(subprocess.check_output([sys.executable, os.path.join(HERE, "ashby_answers.py"), k]))
f = os.path.join(OVERRIDES, k.replace(":", "_") + ".json")
o = json.load(open(f)) if os.path.exists(f) else {}
P = []
for x in d["fields"]:
    mk = next((t for t in o if t.strip()[:40].lower() == x["title"].strip()[:40].lower()), None)
    a = o.pop(mk) if mk else x["answer"]
    if a in ("__RESUME__", "", None): continue
    P.append({"path": x["path"], "title": x["title"][:80], "type": x["type"], "answer": a})
for t, a in o.items():
    u = next((u for u in d["unknown"] if isinstance(u, dict) and u["title"].strip()[:40].lower() == t.strip()[:40].lower()), None)
    P.append({"path": u.get("path", "") if u else "", "title": t[:80], "type": u["type"] if u else "", "answer": a})
print(f"const J=(0,eval)(localStorage.jmAshby);const P={json.dumps(P, ensure_ascii=False)};await new Promise(r=>setTimeout(r,5000));await J.fill(P);await new Promise(r=>setTimeout(r,800));await J.fill(P)")
unk = [u for u in d["unknown"] if (u if isinstance(u, str) else u["title"]) not in o]
print("// URL", d["url"], "| UNKNOWN:", json.dumps(d["unknown"], ensure_ascii=False)[:600], "| BLOCK:", d["blockers"], file=sys.stderr)
