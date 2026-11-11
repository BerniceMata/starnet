#!/usr/bin/env python3
"""fillcall.py <key> -> one-line in-page JS for a Greenhouse form: the full answer plan (labels trimmed to 110
chars) run through the fill library stored in localStorage.jm (see browser/README.md). Runs the fill twice:
the first react-select pick after page load often fails validation."""
import json, re, subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from profile import OVERRIDES  # noqa: E402
k = sys.argv[1]
f = os.path.join(OVERRIDES, k.replace(":", "_") + ".json")
o = open(f).read() if os.path.exists(f) else "{}"
s = subprocess.run([sys.executable, os.path.join(HERE, "genjs.py"), k, o], capture_output=True, text=True)
P = json.loads(re.search(r"const P=(.*?);const f", s.stdout).group(1))
X = [{"label": p["label"][:110], "answer": p["answer"]} for p in P]
print(f"const P={json.dumps(X, ensure_ascii=False)};const f=(0,eval)(localStorage.jm);await f(P,4000);await f(P,300)")
if s.stderr.strip():
    print("//", s.stderr.strip()[:500], file=sys.stderr)
