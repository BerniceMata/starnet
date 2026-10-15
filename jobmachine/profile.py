"""profile.py - the candidate's private facts, loaded from a local, git-ignored profile.json.

Nothing personal lives in this repo. Every name, contact detail, location, employer, and
answer that describes the candidate comes from profile.json (copy profile.example.json and
fill it in). Answer templates elsewhere use <<key>> tokens that are filled from this file.

Paths:
  JOBMACHINE_PROFILE  path to profile.json      (default: jobmachine/profile.json)
  JOBMACHINE_DATA     data dir: jobs.db, overrides/, resume  (default: jobmachine/data)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("JOBMACHINE_DATA") or os.path.join(HERE, "data")
PROFILE_PATH = os.environ.get("JOBMACHINE_PROFILE") or os.path.join(HERE, "profile.json")
OVERRIDES = os.path.join(DATA, "overrides")

REQUIRED = [
    "first_name", "last_name", "email", "phone", "linkedin_url", "city", "state", "state_abbr",
    "country", "home_metro_regex", "current_employer", "current_title", "salary_text",
]


def _derive(p):
    p.setdefault("full_name", f"{p['first_name']} {p['last_name']}")
    p.setdefault("location", f"{p['city']}, {p['state']}")
    p.setdefault("location_short", f"{p['city']}, {p['state_abbr']}")
    # <key>_rx: escaped lowercase form of every text value, for option-preference regexes.
    # An empty value gets a pattern that never matches, so an unanswered fact can't pick an option.
    for k, v in list(p.items()):
        if isinstance(v, str) and not k.endswith("_rx") and k + "_rx" not in p:
            p[k + "_rx"] = re.escape(v.lower()) if v else NEVER
    return p


NEVER = r"(?!x)x"


def load(path=None):
    path = path or PROFILE_PATH
    if not os.path.exists(path):
        sys.exit(f"jobmachine: no profile at {path}. Copy profile.example.json to profile.json and fill it in.")
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    p = {k: v for k, v in p.items() if not k.startswith("_")}
    missing = [k for k in REQUIRED if not p.get(k)]
    if missing:
        sys.exit(f"jobmachine: profile.json is missing {', '.join(missing)}")
    return _derive(p)


P = load()

_TOKEN = re.compile(r"<<(\w+)>>")


def fill(s):
    """Replace <<key>> tokens with profile values. Unknown keys raise, so a typo never ships a blank."""
    if not isinstance(s, str):
        return s
    return _TOKEN.sub(lambda m: str(P[m.group(1)]), s)


def get(key, default=None):
    v = P.get(key, default)
    return v if v not in (None, "") else default
