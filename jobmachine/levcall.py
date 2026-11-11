#!/usr/bin/env python3
"""levcall.py <lever:slug:id> [waitMs] -> one in-page JS call that fills a Lever apply form with
browser/lever_fill.js (installed as localStorage.jmLever), plus an audit line on stderr."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from profile import OVERRIDES, P as PROF  # noqa: E402
k = sys.argv[1]
d = json.loads(subprocess.check_output([sys.executable, os.path.join(HERE, "lever_answers.py"), k]))
f = os.path.join(OVERRIDES, k.replace(":", "_") + ".json")
o = json.load(open(f)) if os.path.exists(f) else {}
P = []
for x in d["fields"] + d["unknown"]:
    mk = next((t for t in o if t.strip()[:40].lower() == x["title"].strip()[:40].lower()), None)
    a = o.pop(mk) if mk else x.get("answer")
    if a in ("__RESUME__", "", None): continue
    P.append({"n": x["name"], "t": x["type"], "a": a})
# Voluntary EEO selects: option-text prefixes from profile.json "eeo_select"; nothing is filled by default.
EEO = {f"eeo[{k}]": v for k, v in (PROF.get("eeo_select") or {}).items() if v}
WAIT = sys.argv[2] if len(sys.argv) > 2 else "3000"
print(f"const L=(0,eval)(localStorage.jmLever);await new Promise(r=>setTimeout(r,{WAIT}));await L.fill({json.dumps(P, ensure_ascii=False)},{json.dumps(EEO, ensure_ascii=False)})")
unk = [u["title"] for u in d["unknown"] if u["title"].strip()[:40].lower() not in [t.strip()[:40].lower() for t in json.load(open(f))]] if os.path.exists(f) else [u["title"] for u in d["unknown"]]
print("// URL", d["url"], "| UNKNOWN:", unk, "| BLOCK:", d["blockers"], file=sys.stderr)
