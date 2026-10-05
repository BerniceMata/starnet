#!/usr/bin/env python3
"""jobq - the job machine's shared queue (Greenhouse, Ashby and Lever).

One SQLite DB = one source of truth for: boards, postings, gate results,
browser reservations, applied ledger, company cooldowns, query log, metrics.

Status lifecycle of a posting:
  discovered -> evaluated -> gate_failed | gate_passed | needs_judgment
  gate_passed -> reserved_by_mac | reserved_by_windows   (atomic, BEGIN IMMEDIATE)
  reserved_* -> submitted | skipped | failed
A browser may open a posting ONLY after `reserve` hands it out.

Commands:
  init                         create tables, seed ledger from data/applied_seed.json
  add-boards <file> [source]  register board slugs (one per line; # comments ok)
  import-ledger <file.md>      seed the applied ledger + cooldowns from a markdown list of application URLs
  add-candidates <json>        worker output: [{"slug":..,"job_id":..,"lane":..,"source":..}] or [{"slug":..}]
  sweep [--stale-hours N]      pull every unswept/stale board via public API, run deterministic gates
  reserve <mac|windows> <n>    atomically claim n gate_passed postings (priority order), print JSON
  mark <key> <submitted|skipped|failed> [note]
  judge <key> <pass|fail> [note]   resolve needs_judgment (fallback lane)
  query-log <lane> <query>     record a discovery query; exit 1 if already run in last 24h
  stats                        metrics funnel
  list <status> [n]            show postings by status
"""
import json, os, re, sqlite3, sys, html, time, ssl, urllib.request, urllib.error
import concurrent.futures as cf
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile import P, DATA  # noqa: E402

DB = os.environ.get("JOBQ_DB") or os.path.join(DATA, "jobs.db")
HTTP_TIMEOUT = 30  # seconds per board request; run_sweep.py lowers it to stay inside a routine budget
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

# ------------------------------------------------------------------ gates
FAMILIES = [  # (priority, family, title regex) - lower number = higher priority
    (1, "gtm_eng", r"\b(gtm|go[- ]to[- ]market) (engineer|systems|automation)|revenue systems|growth engineer|revenue engineer"),
    (3, "ai_fde_se", r"forward[- ]deployed|solutions? (engineer|architect)|applied ai|\bai (engineer|automation|solutions|operations)|agent engineer|automation engineer|deployment engineer|delivery engineer"),
    (4, "ops", r"revenue operations|\brevops\b|sales operations|sales ops|marketing operations|marketing ops|business operations|deal desk|\bcrm\b|gtm operations|growth operations|sales enablement|revenue analyst|gtm analyst"),
    (5, "lifecycle", r"deliverability|lifecycle|marketing automation|email (operations|marketing|infrastructure)|campaign operations"),
    (6, "health_ops", r"patient coordinator|care coordinator|clinical coordinator|program coordinator|genetic counseling assistant|patient (access|success)"),
    (7, "tech_sales", r"sales development|business development rep|\bsdr\b|\bbdr\b|associate account executive|account executive|implementation (engineer|specialist|consultant)|solutions consultant|associate solutions architect|onboarding specialist"),
]
HEALTH = re.compile(r"health|clinic|medical|patient|care\b|pharma|genomic|diagnost|hospital|provider|payer|ehr|biotech", re.I)
BANNED = re.compile(r"\b(senior|sr\.?|staff|principal|director|head|manager|lead|leader|vp|vice president|chief|intern|internship|phd|research(er)?|co-?op|technician|qa|quality assurance|backend|back-end|front ?end|full[- ]?stack|software engineer|data scientist|scientist|devops|sre|site reliability|security engineer|ml engineer|machine learning engineer|expression of interest|future (sales )?openings?|all future|talent (pool|community)|contract(or)?|temp|temporary|part[- ]time|1099|prn|seasonal|freelance|m/w/d|bilingual|spanish|portuguese|german|french|japanese|korean|mandarin)\b", re.I)
LANG_REQ = re.compile(r"(fluen(t|cy)|native|proficien(t|cy)) in (spanish|portuguese|german|french|japanese|korean|mandarin|italian|dutch)|must speak (spanish|portuguese|german|french)", re.I)
CITY_IN_TITLE = re.compile(r"\(([A-Z][a-zA-Z .]+),\s*([A-Z]{2})\)")
HOME_METRO = re.compile(P["home_metro_regex"], re.I)  # the candidate's home metro (on-site/hybrid allowed here)
HOME_STATE = re.compile(r"\b(%s|%s)\b" % (re.escape(P["state"]), re.escape(P["state_abbr"])), re.I)
HOME_METRO_FALSE = re.compile(P["home_metro_exclude_regex"], re.I) if P.get("home_metro_exclude_regex") else None
NONUS = re.compile(r"\b(indonesia|jakarta|taiwan|taipei|thailand|bangkok|vietnam|macedonia|ukraine|latin america|latam|eu|europe|emea|apac|nigeria|kenya|south africa|egypt|uae|dubai|saudi|qatar|pakistan|chile|peru|uruguay|romania|serbia|bulgaria|czech|hungary|greece|turkey|new zealand|china|shanghai|beijing|canada|uk|united kingdom|london|emea|apac|india|germany|europe|mexico|brazil|latam|australia|ireland|poland|spain|france|netherlands|philippines|singapore|japan|toronto|vancouver|montreal|portugal|argentina|colombia|israel|berlin|dublin|amsterdam|paris|bangalore|bengaluru|tokyo|sydney|seoul|ontario|british columbia|hong kong|malaysia|switzerland|sweden|italy|denmark|belgium|slovakia|costa rica|cri)\b", re.I)
STATE_ONLY_REMOTE = re.compile(r"remote[,\s-]*(?:\(|-)?\s*(california|colorado|new york|washington|oregon|florida|georgia|illinois|massachusetts|arizona|utah|ohio|wisconsin|virginia|pennsylvania|new jersey|north carolina|tennessee|ca|co|ny|wa|fl|ga|il|ma|az|ut|oh|wi|va|pa|nj|nc|tn)\b|(california|colorado|new york|washington|oregon|florida|georgia|illinois|massachusetts|arizona|utah|ohio|wisconsin|virginia|pennsylvania|new jersey|north carolina|tennessee)[- ]remote", re.I)
HARD_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*\d{0,2}\+?\s*years?[^.]{0,90}?(experience|in |of |as |closing|selling|quota|software)", re.I)
MONEY = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+(?:\.\d+)?|\d{2,3}(?:\.\d)?\s?[kK])")
HARD_SKIP_BODY = re.compile(r"commission[- ]only|door[- ]to[- ]door|bachelor'?s degree in computer science (required|is required)|must (be|have) .{0,30}(licensed|rn\b|registered nurse)|active (secret|ts/sci) clearance", re.I)
TECH_SIGNAL = re.compile(r"\b(api|technical|automation|developer|engineer|integrat|workflow|ai\b|llm|saas|platform|data|crm|hubspot|zapier|python|sql)\b", re.I)
COLD_CALL_MILL = re.compile(r"(\d{2,3})\+?\s*(cold )?(calls|dials) (per|a|each) day|high[- ]volume cold call", re.I)


def family_of(title):
    for pr, fam, rx in FAMILIES:
        if re.search(rx, title, re.I):
            return pr, fam
    return None, None


def money_vals(text):
    out = []
    for m in MONEY.findall(text):
        s = m.replace(",", "").replace(" ", "")
        try:
            v = float(s[:-1]) * 1000 if s[-1] in "kK" else float(s)
        except ValueError:
            continue
        if 20000 <= v <= 700000:
            out.append(v)
    return out


def location_gate(loc, title=""):
    l = loc or ""
    if HOME_METRO_FALSE and HOME_METRO_FALSE.search(l):
        return False, "not home metro (same-name city)"
    m = CITY_IN_TITLE.search(title or "")
    if m and not (HOME_METRO.search(m.group(1)) and m.group(2).upper() == P["state_abbr"].upper()):
        return False, f"field role in {m.group(1)}, {m.group(2)}"
    if HOME_METRO.search(l):
        return True, "home metro"
    if NONUS.search(l) and not re.search(r"united states|\bus\b|usa", l, re.I):
        return False, "non-US"
    if re.search(r"remote|anywhere|distributed", l, re.I):
        if STATE_ONLY_REMOTE.search(l) and not (HOME_STATE.search(l) or re.search(r"remote[ ,-]*(us|usa|united states)", l, re.I)):
            return False, "remote restricted to another state"
        if NONUS.search(l) and not re.search(r"united states|\bus\b|usa", l, re.I):
            return False, "remote non-US"
        return True, "remote-US"
    if re.fullmatch(r"\s*(united states|usa|us|u\.s\.)\s*", l, re.I):
        return True, "US unspecified"
    return False, "on-site/hybrid outside home metro"


FALLBACK_COMP = int(P.get("fallback_comp_floor", 90000))  # stated pay needed before a sales-fallback role is considered


def gate(title, loc, body, slug):
    """Deterministic gate. Returns (status, family, priority, reason, comp)."""
    pr, fam = family_of(title)
    if not fam:
        return "gate_failed", None, None, "not a target family", ""
    if BANNED.search(title):
        return "gate_failed", fam, pr, "title seniority/banned word", ""
    ok, why = location_gate(loc, title)
    if not ok:
        return "gate_failed", fam, pr, "location: " + why, ""
    if LANG_REQ.search(body):
        return "gate_failed", fam, pr, "non-English language required", ""
    yrs = [int(m.group(1)) for m in HARD_YEARS.finditer(body) if int(m.group(1)) < 25]
    yrs += [int(x) for x in re.findall(r"(\d{1,2})\+\s*(?:years|yrs)", body, re.I) if int(x) < 25]
    if yrs and min(yrs) >= 4:
        return "gate_failed", fam, pr, f"years {min(yrs)}+", ""
    mv = money_vals(body)
    comp = f"{int(min(mv))}-{int(max(mv))}" if mv else ""
    floor = int(P.get("health_ops_comp_floor", 55000)) if fam == "health_ops" else int(P.get("comp_floor_base", 70000))
    if mv and max(mv) < floor:
        return "gate_failed", fam, pr, "comp below floor", comp
    if HARD_SKIP_BODY.search(body):
        return "gate_failed", fam, pr, "hard-skip body term", comp
    if re.search(r"salesforce (admin|administrator|certified|certification) (required|is required)", body, re.I):
        return "gate_failed", fam, pr, "Salesforce certification required", comp
    # health-tech promotion: ops/gtm roles at health companies -> priority 2
    if fam in ("ops", "gtm_eng") and HEALTH.search(body[:3000] + " " + slug):
        pr = 2 if fam == "ops" else 1
    if fam == "tech_sales":
        # fallback lane: deterministic pre-screen, then Opus judgment
        if yrs and min(yrs) >= 3 and re.search(r"quota|closing|closed|full[- ]cycle", body, re.I):
            return "gate_failed", fam, pr, "3+ yrs quota/closing required", comp
        if COLD_CALL_MILL.search(body):
            return "gate_failed", fam, pr, "high-volume cold-calling role", comp
        if not mv or max(mv) < FALLBACK_COMP:
            return "gate_failed", fam, pr, f"fallback comp not strong (needs >= {FALLBACK_COMP} stated)", comp
        if len(TECH_SIGNAL.findall(body)) < 4:
            return "gate_failed", fam, pr, "no technical/complex-product signal", comp
        return "needs_judgment", fam, pr, "fallback lane: Opus review", comp
    if fam in ("ai_fde_se",) and re.search(r"(\d)\+? years? (of )?(professional )?software engineering", body, re.I):
        m = re.search(r"(\d)\+? years? (of )?(professional )?software engineering", body, re.I)
        if int(m.group(1)) >= 3:
            return "needs_judgment", fam, pr, f"{m.group(1)}+ yrs SWE asked", comp
    return "gate_passed", fam, pr, why, comp


# ------------------------------------------------------------------ db
SCHEMA = """
CREATE TABLE IF NOT EXISTS boards(slug TEXT PRIMARY KEY, source TEXT, added_at TEXT, last_swept TEXT, live INTEGER, n_jobs INTEGER);
CREATE TABLE IF NOT EXISTS postings(
  key TEXT PRIMARY KEY, slug TEXT, job_id TEXT, company TEXT, title TEXT, location TEXT, url TEXT,
  comp TEXT, family TEXT, priority INTEGER, lane TEXT, source TEXT, updated_at TEXT,
  status TEXT, reason TEXT, reserved_by TEXT, reserved_at TEXT, discovered_at TEXT, evaluated_at TEXT, finished_at TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_status ON postings(status, priority);
CREATE TABLE IF NOT EXISTS ledger(url TEXT PRIMARY KEY, key TEXT, company TEXT, slug TEXT, role TEXT, submitted_at TEXT, worker TEXT);
CREATE TABLE IF NOT EXISTS cooldown(slug TEXT PRIMARY KEY, until TEXT);
CREATE TABLE IF NOT EXISTS queries(lane TEXT, query TEXT, run_at TEXT, PRIMARY KEY(lane, query));
CREATE TABLE IF NOT EXISTS events(t TEXT, kind TEXT, key TEXT, detail TEXT);
"""


def conn():
    c = sqlite3.connect(DB, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ssl.create_default_context()) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return -1, None


def cmd_init(args):
    c = conn(); c.executescript(SCHEMA)
    seed = os.path.join(DATA, "applied_seed.json")
    if os.path.exists(seed):
        for r in json.load(open(seed)):
            c.execute("INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?,?,?)",
                      (r["url"], r["key"], r["company"], r["slug"], r["role"], r["submitted_at"], r.get("worker", "mac")))
            c.execute("INSERT OR REPLACE INTO cooldown VALUES(?,?)", (r["slug"], r["cooldown_until"]))
    print("db ready:", DB)


def cmd_add_boards(args):
    c = conn(); n = 0
    src = args[1] if len(args) > 1 else "manual"
    for line in open(args[0]).read().splitlines():
        s = line.split("#", 1)[0].strip().lower()
        if s and c.execute("INSERT OR IGNORE INTO boards(slug,source,added_at) VALUES(?,?,?)", (s, src, NOW())).rowcount:
            n += 1
    print("new boards:", n)


def cmd_add_candidates(args):
    c = conn(); nb = nj = 0
    for f in args:
        try:
            data = json.load(open(f))
        except Exception as e:
            print("bad file", f, e); continue
        for r in data:
            s = (r.get("slug") or "").strip().lower()
            if not s:
                continue
            if c.execute("INSERT OR IGNORE INTO boards(slug,source,added_at) VALUES(?,?,?)", (s, r.get("lane", "worker"), NOW())).rowcount:
                nb += 1
            if r.get("job_id"):
                key = f"gh:{s}:{r['job_id']}"
                if c.execute("INSERT OR IGNORE INTO postings(key,slug,job_id,lane,source,status,discovered_at) VALUES(?,?,?,?,?,?,?)",
                             (key, s, str(r["job_id"]), r.get("lane"), r.get("source"), "discovered", NOW())).rowcount:
                    nj += 1
    print(f"new boards {nb}, new postings {nj}")


def _sweep_board(slug):
    code, data = http_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return slug, code, data


def sweep_context(c):
    applied = {r["url"] for r in c.execute("SELECT url FROM ledger")}
    return {"applied_ids": {u.rstrip("/").split("/")[-1] for u in applied},
            "cooldown": {r["slug"]: r["until"] for r in c.execute("SELECT * FROM cooldown")},
            "donot": bool(c.execute("SELECT name FROM sqlite_master WHERE name='donot'").fetchone())}


def ingest_greenhouse(c, slug, code, data, ctx, stats):
    """Record one Greenhouse board's fetch result and gate every new posting. Never re-touches evaluated rows."""
    stats["boards"] += 1
    if code != 200 or data is None:
        # Only a 404/410 means the board is gone. Timeouts, 429s and 5xx are transient: keep it live.
        if code in (404, 410):
            c.execute("UPDATE boards SET live=0,last_swept=? WHERE slug=?", (NOW(), slug))
        else:
            c.execute("UPDATE boards SET last_swept=? WHERE slug=?", (NOW(), slug))
        return
    jobs = data.get("jobs", [])
    c.execute("UPDATE boards SET live=1,last_swept=?,n_jobs=? WHERE slug=?", (NOW(), len(jobs), slug))
    c.execute("BEGIN IMMEDIATE")
    for j in jobs:
        jid = str(j.get("id")); key = f"gh:{slug}:{jid}"
        title = (j.get("title") or "").strip(); loc = (j.get("location") or {}).get("name", "")
        url = j.get("absolute_url") or f"https://job-boards.greenhouse.io/{slug}/jobs/{jid}"
        company = j.get("company_name") or slug
        row = c.execute("SELECT status FROM postings WHERE key=?", (key,)).fetchone()
        if row and row["status"] not in ("discovered",):
            continue  # already evaluated; never re-touch reserved/submitted rows
        stats["discovered"] += 0 if row else 1
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(j.get("content") or ""))))
        if jid in ctx["applied_ids"]:
            st, fam, pr, why, comp = "submitted", None, None, "already in ledger", ""
        else:
            st, fam, pr, why, comp = gate(title, loc, body, slug)
            dn = c.execute("SELECT reason FROM donot WHERE ? LIKE pattern OR ? LIKE pattern", (f"{slug}:{title.lower()}", f"{slug}:{jid}")).fetchone() if ctx["donot"] else None
            if dn:
                st, why = "gate_failed", dn[0]
            cd = ctx["cooldown"].get(slug)
            if st in ("gate_passed", "needs_judgment") and cd and cd > NOW()[:10]:
                st, why = "gate_failed", f"company cooldown until {cd}"
        stats["evaluated"] += 1
        stats["passed"] += st == "gate_passed"
        stats["judgment"] += st == "needs_judgment"
        c.execute("""INSERT INTO postings(key,slug,job_id,company,title,location,url,comp,family,priority,lane,source,updated_at,status,reason,discovered_at,evaluated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(key) DO UPDATE SET company=excluded.company,title=excluded.title,location=excluded.location,url=excluded.url,
                     comp=excluded.comp,family=excluded.family,priority=excluded.priority,updated_at=excluded.updated_at,status=excluded.status,
                     reason=excluded.reason,evaluated_at=excluded.evaluated_at""",
                  (key, slug, jid, company, title, loc, url, comp, fam, pr, fam, "board_sweep", j.get("updated_at", ""), st, why, NOW(), NOW()))
    c.execute("COMMIT")


def cmd_sweep(args):
    stale = 20
    if "--stale-hours" in args:
        stale = int(args[args.index("--stale-hours") + 1])
    c = conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale)).isoformat()
    slugs = [r["slug"] for r in c.execute("SELECT slug FROM boards WHERE source NOT IN ('ashby','lever') AND slug NOT LIKE '%:%' AND (live IS NULL OR live=1) AND (last_swept IS NULL OR last_swept<?)", (cutoff,))]
    print("boards to sweep:", len(slugs), file=sys.stderr)
    ctx = sweep_context(c)
    stats = dict(boards=0, discovered=0, evaluated=0, passed=0, judgment=0)
    with cf.ThreadPoolExecutor(16) as ex:
        for slug, code, data in ex.map(_sweep_board, slugs):
            ingest_greenhouse(c, slug, code, data, ctx, stats)
    print(json.dumps({"boards_swept": len(slugs), "new_postings_discovered": stats["discovered"], "postings_evaluated": stats["evaluated"]}))


def cmd_import_ledger(args):
    """Seed the applied ledger (and 7-day cooldowns) from a markdown table that lists application URLs,
    e.g. the applied log kept outside the repo. Prevents re-applying after a fresh install."""
    c = conn(); c.executescript(SCHEMA); n = 0
    pat = re.compile(r"https://(?:job-boards\.greenhouse\.io|job-boards\.eu\.greenhouse\.io|boards\.greenhouse\.io)/([^/\s|]+)/jobs/(\d+)"
                     r"|https://jobs\.ashbyhq\.com/([^/\s|]+)/([0-9a-f-]{36})"
                     r"|https://jobs\.lever\.co/([^/\s|]+)/([0-9a-f-]{36})")
    for line in open(args[0], encoding="utf-8"):
        m = pat.search(line)
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if not m:
            g = re.search(r"(https://\S+?gh_jid=(\d+))", line)  # Greenhouse embedded on a company careers site
            if not g or len(cells) < 5:
                continue
            m = None
            src, slug, jid, url = "gh", re.sub(r"[^a-z0-9]", "", cells[2].lower()), g.group(2), g.group(1)
        if m and m.group(1):
            src, slug, jid, url = "gh", m.group(1), m.group(2), m.group(0)
        elif m and m.group(3):
            src, slug, jid, url = "ashby", m.group(3), m.group(4), m.group(0)
        elif m:
            src, slug, jid, url = "lever", m.group(5), m.group(6), m.group(0)
        date = next((x for x in cells if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)), NOW()[:10])
        company = cells[2] if len(cells) > 4 else slug
        role = cells[3] if len(cells) > 4 else ""
        if c.execute("INSERT OR IGNORE INTO ledger VALUES(?,?,?,?,?,?,?)",
                     (url, f"{src}:{slug}:{jid}", company, slug, role, date, "import")).rowcount:
            n += 1
        until = (datetime.fromisoformat(date) + timedelta(days=7)).date().isoformat()
        c.execute("INSERT INTO cooldown VALUES(?,?) ON CONFLICT(slug) DO UPDATE SET until=max(until, excluded.until)", (slug, until))
    print("ledger rows imported:", n)


def cmd_reserve(args):
    worker, n = args[0], int(args[1])
    assert worker in ("mac", "windows"), "worker must be mac or windows"
    c = conn()
    c.execute("BEGIN IMMEDIATE")  # serialises reservers: no two workers can claim the same row
    rows = c.execute("""SELECT * FROM postings WHERE status='gate_passed'
                        AND slug NOT IN (SELECT slug FROM cooldown WHERE until>?)
                        AND url NOT IN (SELECT url FROM ledger)
                        ORDER BY (key LIKE 'gh:%') DESC, priority, fit DESC, updated_at DESC""", (NOW()[:10],)).fetchall()
    taken, seen_co = [], set(r["slug"] for r in c.execute(
        "SELECT slug FROM postings WHERE status LIKE 'reserved_by_%'"))
    for r in rows:
        if r["slug"] in seen_co:
            continue  # one application per company: never hold two from the same company
        seen_co.add(r["slug"])
        c.execute("UPDATE postings SET status=?,reserved_by=?,reserved_at=? WHERE key=? AND status='gate_passed'",
                  (f"reserved_by_{worker}", worker, NOW(), r["key"]))
        taken.append(dict(r))
        if len(taken) >= n:
            break
    c.execute("COMMIT")
    for t in taken:
        c.execute("INSERT INTO events VALUES(?,?,?,?)", (NOW(), "reserve", t["key"], worker))
    print(json.dumps([{k: t[k] for k in ("key", "company", "title", "location", "url", "comp", "family", "priority")} for t in taken], indent=1))


def cmd_mark(args):
    key, st = args[0], args[1]
    note = " ".join(args[2:])
    assert st in ("submitted", "skipped", "failed", "gate_passed")
    c = conn(); c.execute("BEGIN IMMEDIATE")
    r = c.execute("SELECT * FROM postings WHERE key=?", (key,)).fetchone()
    if not r:
        c.execute("ROLLBACK"); print("no such key"); sys.exit(1)
    if st == "submitted":
        if c.execute("SELECT 1 FROM ledger WHERE url=?", (r["url"],)).fetchone():
            c.execute("ROLLBACK"); print("DUPLICATE: already in ledger"); sys.exit(2)
        c.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?)", (r["url"], key, r["company"], r["slug"], r["title"], NOW(), r["reserved_by"] or "mac"))
        until = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        c.execute("INSERT OR REPLACE INTO cooldown VALUES(?,?)", (r["slug"], until))
        # release any other reserved/passed rows at the same company
        c.execute("UPDATE postings SET status='gate_failed',reason=? WHERE slug=? AND key!=? AND status IN ('gate_passed','needs_judgment')",
                  (f"company cooldown until {until}", r["slug"], key))
    c.execute("UPDATE postings SET status=?,finished_at=?,note=? WHERE key=?", (st, NOW(), note, key))
    c.execute("COMMIT")
    c.execute("INSERT INTO events VALUES(?,?,?,?)", (NOW(), st, key, note))
    print("ok", key, st)


def cmd_judge(args):
    key, verdict = args[0], args[1]
    c = conn()
    st = "gate_passed" if verdict == "pass" else "gate_failed"
    c.execute("UPDATE postings SET status=?,reason=? WHERE key=? AND status='needs_judgment'", (st, "judged: " + " ".join(args[2:]), key))
    print("ok", key, st)


def cmd_query_log(args):
    lane, q = args[0], " ".join(args[1:])
    c = conn()
    r = c.execute("SELECT run_at FROM queries WHERE lane=? AND query=?", (lane, q)).fetchone()
    if r and r["run_at"] > (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat():
        print("SKIP already run", r["run_at"]); sys.exit(1)
    c.execute("INSERT OR REPLACE INTO queries VALUES(?,?,?)", (lane, q, NOW()))
    print("ok")


def cmd_stats(args):
    c = conn()
    q = lambda s, *a: c.execute(s, a).fetchone()[0]
    out = {
        "boards_known": q("SELECT count(*) FROM boards"),
        "boards_live": q("SELECT count(*) FROM boards WHERE live=1"),
        "postings_discovered": q("SELECT count(*) FROM postings"),
        "postings_evaluated": q("SELECT count(*) FROM postings WHERE evaluated_at IS NOT NULL"),
        "gate_passed_total": q("SELECT count(*) FROM postings WHERE status IN ('gate_passed','reserved_by_mac','reserved_by_windows','submitted','skipped','failed') AND reason!='already in ledger'"),
        "awaiting_judgment": q("SELECT count(*) FROM postings WHERE status='needs_judgment'"),
        "queue_ready": q("SELECT count(*) FROM postings WHERE status='gate_passed'"),
        "reserved_mac": q("SELECT count(*) FROM postings WHERE status='reserved_by_mac'"),
        "reserved_windows": q("SELECT count(*) FROM postings WHERE status='reserved_by_windows'"),
        "forms_opened": q("SELECT count(*) FROM postings WHERE status IN ('submitted','skipped','failed') AND reserved_by IS NOT NULL"),
        "confirmed_submitted_ledger": q("SELECT count(*) FROM ledger"),
        "skipped": q("SELECT count(*) FROM postings WHERE status='skipped'"),
        "failed": q("SELECT count(*) FROM postings WHERE status='failed'"),
    }
    fam = c.execute("SELECT family, count(*) n FROM postings WHERE status='gate_passed' GROUP BY family ORDER BY n DESC").fetchall()
    out["queue_by_family"] = {r["family"]: r["n"] for r in fam}
    rs = c.execute("SELECT reason, count(*) n FROM postings WHERE status='gate_failed' AND family IS NOT NULL GROUP BY reason ORDER BY n DESC LIMIT 8").fetchall()
    out["top_fail_reasons_in_family"] = {r["reason"][:50]: r["n"] for r in rs}
    print(json.dumps(out, indent=1))


def cmd_list(args):
    st = args[0]; n = int(args[1]) if len(args) > 1 else 50
    c = conn()
    for r in c.execute("SELECT * FROM postings WHERE status=? ORDER BY priority, updated_at DESC LIMIT ?", (st, n)):
        print(f"P{r['priority']} | {r['key']} | {r['company']} | {r['title']} | {r['location'][:40]} | {r['comp']} | {r['reason']}")


CMDS = {"init": cmd_init, "add-boards": cmd_add_boards, "add-candidates": cmd_add_candidates, "sweep": cmd_sweep,
        "reserve": cmd_reserve, "mark": cmd_mark, "judge": cmd_judge, "query-log": cmd_query_log, "stats": cmd_stats, "list": cmd_list,
        "import-ledger": cmd_import_ledger}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(1)
    CMDS[sys.argv[1]](sys.argv[2:])
