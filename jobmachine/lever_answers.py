#!/usr/bin/env python3
"""lever_answers.py <lever:slug:id> -> JSON plan for the Lever apply form (parsed from public apply page HTML).
fields: name (input name attr), title, type (text|textarea|radio|checkbox|select|file), required, answer, options.
Reuses ashby_answers.answer_for (which wraps answers.py BANK)."""
import json, os, re, sys, urllib.request
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ashby_answers import answer_for  # noqa: E402
import answers as A  # noqa: E402
from profile import P  # noqa: E402

STD = {"name": P["full_name"], "email": P["email"], "phone": P["phone"],
       "org": P["current_employer"], "location": P["location_short"], "urls[LinkedIn]": P["linkedin_url"]}


def plan(key):
    _, slug, jid = key.split(":", 2)
    url = f"https://jobs.lever.co/{slug}/{jid}/apply"
    s = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode()
    soup = BeautifulSoup(s, "html.parser")
    form = soup.find("form", id="application-form") or soup
    out = {"url": url, "fields": [], "unknown": [], "blockers": [], "captcha": bool(form.find(attrs={"name": "h-captcha-response"}))}
    for li in form.select("li.application-question, .application-additional"):
        lab = li.select_one(".application-label .text") or li.select_one(".application-label")
        title = re.sub(r"\s+", " ", (lab.get_text(" ") if lab else "")).replace("✱", "").strip()
        req = bool(li.select_one(".required")) or bool(li.find(attrs={"required": True}))
        inputs = [i for i in li.find_all(["input", "textarea", "select"]) if i.get("type") != "hidden" and i.get("name")]
        if not inputs: continue
        nm = inputs[0]["name"]
        if nm.startswith("eeo[") or nm in ("resumeStorageId", "h-captcha-response"): continue
        tag = inputs[0].name
        typ = "select" if tag == "select" else "textarea" if tag == "textarea" else inputs[0].get("type", "text")
        if typ == "file":
            if nm == "resume": out["fields"].append({"name": nm, "title": title or "Resume", "type": "file", "required": req, "answer": "__RESUME__"})
            elif req: out["blockers"].append(f"file: {title}")
            continue
        opts = [o.get_text(strip=True) for o in inputs[0].find_all("option") if o.get("value")] if typ == "select" else \
               [i.get("value") for i in inputs if i.get("type") in ("radio", "checkbox")]
        if nm in STD:
            out["fields"].append({"name": nm, "title": title, "type": typ, "required": req, "answer": STD[nm], "options": []}); continue
        if not title: continue
        if re.search(r"street|address line|zip|postal", title, re.I) and req:
            out["blockers"].append(f"needs-address: {title}"); continue
        if re.search(r"cover letter", title, re.I) and req:
            out["blockers"].append(f"cover: {title}"); continue
        ans = answer_for(title, opts, P["location_short"])
        if ans is None or (ans == "" and req):
            if req: out["unknown"].append({"name": nm, "title": title, "type": typ, "options": opts[:60]})
            continue
        if ans == "": continue
        out["fields"].append({"name": nm, "title": title, "type": typ, "required": req, "answer": ans, "options": opts[:60]})
    return out


if __name__ == "__main__":
    for k in sys.argv[1:]:
        try: print(json.dumps(plan(k), ensure_ascii=False))
        except Exception as e: print(json.dumps({"key": k, "error": repr(e)}))
