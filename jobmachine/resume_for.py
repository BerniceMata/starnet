#!/usr/bin/env python3
"""resume_for.py <key> -> path of the resume variant for this posting's job family (profile.json "resumes")."""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile import P, DATA  # noqa: E402
fam = sqlite3.connect(os.path.join(DATA, "jobs.db")).execute("SELECT family FROM postings WHERE key=?", (sys.argv[1],)).fetchone()
fam = fam[0] if fam else None
path = (P.get("resumes") or {}).get(fam or "", "")
if not path or not os.path.exists(path):
    sys.exit(f"HOLD: no resume for family {fam!r}")
print(path)
