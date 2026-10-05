#!/usr/bin/env python3
"""ats_sweep.py <ashby|lever> <slugfile> : sweep Ashby / Lever boards into the SAME jobs.db queue,
using the SAME deterministic gate as jobq.py. Keys: ashby:<slug>:<id> / lever:<slug>:<id>.
Safe to run in the background alongside Chrome workers (WAL + short transactions)."""
import json, re, sys, html, time, urllib.request, urllib.error, concurrent.futures as cf
import os  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobq
from jobq import conn, gate, NOW

UA = "Mozilla/5.0"
HTTP_TIMEOUT = 30  # seconds per board request; run_sweep.py lowers it to stay inside a routine budget


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=HTTP_TIMEOUT) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return -1, None


def ashby(slug):
    code, d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    out = []
    if code != 200 or not d:
        return slug, code, out
    for j in d.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        loc = "; ".join(l for l in locs if l)
        if j.get("isRemote") and not re.search(r"remote", loc, re.I):
            loc += "; Remote"
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        body = (j.get("descriptionPlain") or "") + " " + comp
        if (j.get("employmentType") or "").lower() in ("parttime", "contract", "intern", "temporary"):
            body += " part-time contract"
        out.append(dict(id=j["id"], title=j.get("title", "").strip(), loc=loc, body=body,
                        url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j['id']}",
                        company=slug, updated=j.get("publishedAt", "")))
    return slug, code, out


def lever(slug):
    code, d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    out = []
    if code != 200 or not isinstance(d, list):
        return slug, code, out
    for j in d:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location") or ""]
        loc = "; ".join(locs)
        if (j.get("workplaceType") or "") == "remote" and not re.search(r"remote", loc, re.I):
            loc += "; Remote"
        if (j.get("country") or "").upper() not in ("", "US") and not re.search(r"united states|\bus\b|usa", loc, re.I):
            loc += f"; {j.get('country')}"
        lists = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(x.get("content", ""))) for x in j.get("lists") or [])
        sr = j.get("salaryRange") or {}
        comp = f" ${sr.get('min')} - ${sr.get('max')}" if sr.get("min") else ""
        body = (j.get("descriptionPlain") or "") + " " + lists + " " + (j.get("additionalPlain") or "") + comp
        if re.search(r"intern|part|contract|temp", (cat.get("commitment") or ""), re.I):
            body += " part-time contract"
        out.append(dict(id=j["id"], title=(j.get("text") or "").strip(), loc=loc, body=body,
                        url=j.get("hostedUrl"), company=slug, updated=str(j.get("createdAt", ""))))
    return slug, code, out


def ingest(c, ats, slug, code, jobs, applied, cooldown, stats):
    """Record one board's fetch result and gate every new posting. Never re-touches evaluated rows."""
    c.execute("INSERT OR IGNORE INTO boards(slug,source,added_at) VALUES(?,?,?)", (f"{ats}:{slug}", ats, NOW()))
    stats["boards"] += 1
    if code != 200:
        # Only a 404/410 means the board is gone. Timeouts, 429s and 5xx are transient: keep it live.
        if code in (404, 410):
            c.execute("UPDATE boards SET live=0,last_swept=? WHERE slug=?", (NOW(), f"{ats}:{slug}"))
        else:
            c.execute("UPDATE boards SET last_swept=? WHERE slug=?", (NOW(), f"{ats}:{slug}"))
        return
    c.execute("UPDATE boards SET live=1,last_swept=?,n_jobs=? WHERE slug=?", (NOW(), len(jobs), f"{ats}:{slug}"))
    stats["live"] += 1
    c.execute("BEGIN IMMEDIATE")
    for j in jobs:
        key = f"{ats}:{slug}:{j['id']}"
        row = c.execute("SELECT status FROM postings WHERE key=?", (key,)).fetchone()
        if row and row["status"] != "discovered":
            continue
        body = re.sub(r"\s+", " ", j["body"])
        if j["url"] in applied:
            st, fam, pr, why, comp = "submitted", None, None, "already in ledger", ""
        else:
            st, fam, pr, why, comp = gate(j["title"], j["loc"], body, slug)
            if st in ("gate_passed", "needs_judgment") and cooldown.get(slug, "") > NOW()[:10]:
                st, why = "gate_failed", "company cooldown"
        stats["discovered"] += 0 if row else 1
        stats["passed"] += st == "gate_passed"
        stats["judgment"] += st == "needs_judgment"
        c.execute("""INSERT OR REPLACE INTO postings(key,slug,job_id,company,title,location,url,comp,family,priority,lane,source,updated_at,status,reason,discovered_at,evaluated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (key, slug, j["id"], j["company"], j["title"], j["loc"], j["url"], comp, fam, pr, fam, f"{ats}_sweep", j["updated"], st, why, NOW(), NOW()))
    c.execute("COMMIT")


def ledger_context(c):
    applied = {r["url"] for r in c.execute("SELECT url FROM ledger")}
    cooldown = {r["slug"]: r["until"] for r in c.execute("SELECT * FROM cooldown")}
    return applied, cooldown


def main():
    ats, slugfile = sys.argv[1], sys.argv[2]
    fn = ashby if ats == "ashby" else lever
    slugs = [s.strip().lower() for s in open(slugfile).read().replace(",", " ").split() if s.strip()]
    c = conn()
    applied, cooldown = ledger_context(c)
    stats = dict(boards=0, live=0, discovered=0, passed=0, judgment=0)
    with cf.ThreadPoolExecutor(12) as ex:
        for slug, code, jobs in ex.map(fn, slugs):
            ingest(c, ats, slug, code, jobs, applied, cooldown, stats)
            if stats["boards"] % 250 == 0:
                print(json.dumps(stats), flush=True)
    print("DONE", json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()
