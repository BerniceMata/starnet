#!/usr/bin/env python3
"""ashby_answers.py <ashby:slug:id> -> JSON plan for the Ashby form (via public non-user-graphql).
Reuses answers.py BANK/EEO logic. fields: path,title,type,required,answer,options"""
import json, os, re, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answers as A  # noqa: E402
from profile import P  # noqa: E402

Q = "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) { id title locationName isListed applicationForm { sections { title fieldEntries { ... on FormFieldEntry { id field isRequired descriptionHtml } } } } } }"


def fetch(slug, jid):
    body = json.dumps({"operationName": "ApiJobPosting", "variables": {"organizationHostedJobsPageName": slug, "jobPostingId": jid}, "query": Q}).encode()
    r = urllib.request.urlopen(urllib.request.Request("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting", data=body,
                                                      headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"}), timeout=30)
    return json.loads(r.read())["data"]["jobPosting"]


def answer_for(title, opts, loc):
    L = re.sub(r'^[^a-z0-9]+', '', title.lower()).strip()
    dfw = bool(A.HOME_METRO.search(loc or ""))
    if re.search(r"^(full )?name$|^legal name|^full legal name", L): return P["full_name"]
    if re.search(r"^first name", L): return P["first_name"]
    if re.search(r"^last name", L): return P["last_name"]
    if re.search(r"^(e-?mail|email address)", L): return P["email"]
    if re.search(r"^phone|phone number|mobile", L) and not opts: return P["phone"]
    if re.search(r"linkedin", L) and not opts and not re.search(r"do you have", L): return P["linkedin_url"]
    pa = A.private_answer(L, opts)
    if pa is not None and not opts: return pa
    if pa and opts:
        pk = A.pick(opts, re.escape(pa)) or (A.pick(opts, r"^no\b") if pa == "No" else None)
        if pk: return pk
    if re.search(r"dribbble|dribble|portfolio|website|other url|personal site", L) and not opts: return ""
    if opts and len(opts) == 1 and re.search(r"consent|acknowledg|privacy|i have read", (L + ' ' + opts[0]).lower()): return opts[0]
    if re.search(r"^location$|home location|current location|where are you (currently )?(located|based)|city.{0,10}state", L) and not opts: return P["location"]
    if re.search(r"years", L) and re.search(r"how many|number of|years of", L):
        if opts: return A.pick(opts, r"^1|1-2|0-2|1-3|less than 2|under 2|^0")
        if re.search(r"similar|this role|rev ?ops|revenue|sales|gtm|automation|\bai\b|llm|b2b|saas|crm", L) and not re.search(r"software engineering|engineering experience|salesforce|python|typescript|javascript", L): return P.get("years_similar") or None
        return None
    if re.search(r"hybrid|in[- ]office|on[- ]?site|commute", L):
        a = "Yes" if dfw else None
        return A.pick(opts, r"^yes") if (opts and a) else a
    for rx, a, pref in A.BANK:
        if a is None: continue
        if re.search(rx, L, re.I):
            if opts and len(opts) == 1 and re.search(r"consent|acknowledg|privacy|agree", L + opts[0], re.I): return opts[0]
            if a == "": return None  # profile has no answer: leave unknown (held if required)
            return A.pick(opts, pref) if opts else a
    for rx, pref in A.EEO:
        if opts and re.search(rx, L):
            return A.pick(opts, pref) or A.pick(opts, r"decline|prefer not|don't wish|do not wish|not to")
    return None


def plan(key):
    _, slug, jid = key.split(":", 2)
    jp = fetch(slug, jid)
    out = {"key": key, "url": f"https://jobs.ashbyhq.com/{slug}/{jid}/application", "title": jp["title"], "location": jp.get("locationName"),
           "fields": [], "unknown": [], "blockers": []}
    for s in jp["applicationForm"]["sections"]:
        for fe in s["fieldEntries"]:
            f = fe.get("field") or {}
            if f.get("isDeactivated"): continue
            path, title, typ, req = f.get("path"), (f.get("title") or "").strip(), f.get("type"), fe.get("isRequired")
            opts = [v.get("label") for v in (f.get("selectableValues") or [])]
            if typ == "File":
                if path == "_systemfield_resume" or re.search(r"resume|cv", title, re.I):
                    out["fields"].append({"path": path, "title": title, "type": typ, "required": req, "answer": "__RESUME__"})
                elif req:
                    (out["blockers"] if re.search(r"cover", title, re.I) else out["unknown"]).append(title)
                continue
            if typ == "Boolean": opts = ["Yes", "No"]
            if re.search(r"street|address line|zip|postal", title, re.I) and req:
                out["blockers"].append(f"needs-address: {title}"); continue
            ans = answer_for(title, opts, out["location"])
            if typ == "Number" and ans == A.SALARY_TEXT: ans = str(P.get("salary_number", ""))
            if typ == "LongText" and ans is None and req:
                out["unknown"].append({"path": path, "title": title, "type": typ, "desc": re.sub("<[^>]+>", " ", fe.get("descriptionHtml") or "")[:200]}); continue
            if ans is None:
                if req: out["unknown"].append({"path": path, "title": title, "type": typ, "options": opts[:60]})
                continue
            if ans == "" and req:
                out["unknown"].append({"path": path, "title": title, "type": typ, "options": opts[:60], "note": "required but no approved value"}); continue
            out["fields"].append({"path": path, "title": title, "type": typ, "required": req, "answer": ans, "options": opts[:60]})
    return out


if __name__ == "__main__":
    for k in sys.argv[1:]:
        try:
            print(json.dumps(plan(k), indent=1, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"key": k, "error": repr(e)}))
