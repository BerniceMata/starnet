#!/usr/bin/env python3
"""answers.py <key> : fetch a posting's form via the public API and map every question
to an answer from the packet's answer bank. Prints JSON plan for the Chrome worker:
{"key","url","fields":[{"label","type","required","answer","options"}],"unknown":[...],"blockers":[...]}
Never invents resume facts. Unknown required questions => listed, job should be skipped."""
import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile import P, fill  # noqa: E402

UA = "Mozilla/5.0"
def private_answer(L, opts=None):
    """Answers from the private profile. None = no rule; '' = leave blank (or unknown if required)."""
    if re.search(r"github", L):
        return P.get("github_username", "") if re.search(r"user ?name|handle", L) else P.get("github_url", "")
    if re.search(r"twitter|\bx\b handle|x\.com|\bx \(", L):
        return ""
    if re.search(r"(pe|vc|venture|private equity)[- ]?(or (pe|vc)[- ])?(backed|funded)|venture[- ]backed|private[- ]equity", L): return P.get("vc_pe_backed_employers", "")
    if re.search(r"vacation|holiday|time off|pto|leave", L) and re.search(r"booked|planned|upcoming|scheduled", L):
        if re.search(r"next month|coming month|next 30 days|next four weeks|next 4 weeks", L) and not re.search(r"months", L):
            return P.get("vacation_next_month", "")
        return ""
    return None


SALARY_TEXT = fill("<<salary_text>>")

# (label regex, answer, option-preference regex for selects)
BANK = [
    (r"do you live in,? and are you legally authori[sz]ed to work in the countr|are you legally authori[sz]ed to work in the countr(y|ies) listed", "Yes", r"^yes"),
    (r"(are you|currently).{0,60}authori[sz]ed.{0,160}without (requiring |needing )?(a |any )?(employer |visa |company )*(visa )?(sponsorship|support)", "Yes", r"^yes"),
    (r"require .{0,40}to maintain .{0,20}authori[sz]ation|require the support of .{0,30}to maintain", "No", r"^no\b"),
    (r"(unrestricted|current) (work )?authori[sz]ation to work|authori[sz]ation to work in the (us|u\.s\.|united states)", "Yes", r"^yes"),
    (r"where are you (currently )?(located|based)\??$|where would you like to work from", "<<location>>", r"remotely in the usa||other state||<<state_rx>>||<<city_rx>>||united states|^us\b"),
    (r"highest level of education|highest degree", "<<degree_level>>", r"bachelor||college degree"),
    (r"what degree (have you|did you) (earned|earn)|degree(s)? (have you )?earned", "<<degree_short>>", r"bachelor"),
    (r"major|field of study", "<<major>>", None),
    (r"finra|series (6|7|63|65|66)", "No", r"^no\b"),
    (r"(sales|business) development .{0,40}selling (ai|machine learning|data)", "No", r"^no\b"),
    (r"notice period|when would you be able to start", "<<availability>>", None),
    (r"gdpr|read and understood", "Acknowledge", r"read and understood|acknowledge|yes|confirm"),
    (r"^legal first name", "<<first_name>>", None),
    (r"^legal last name", "<<last_name>>", None),
    (r"^legal (full )?name|^legal full\s+name", "<<full_name>>", None),
    (r"^confirm (your )?email", "<<email>>", None),
    (r"which country are you (currently )?(based|located|living)|what country are you (currently )?(based|located)", "<<country>>", r"united states"),
    (r"^nationality$|what is your nationality", "<<nationality>>", r"<<nationality_rx>>"),
    (r"^contact number|^mobile number|^phone number", "<<phone>>", None),
    (r"require (a|any) (form of )?(visa|authorization)", "No", r"^no\b"),
    (r"authori[sz]ation to work for any employer", "Yes", r"^yes"),
    (r"current or (last|most recent) (company|employer)", "<<current_employer>>", None),
    (r"web3|crypto experience", "None", None),
    (r"located (with)?in the united states|based in the united states", "Yes", r"^yes"),
    (r"preferred communication method", "Email", r"^email"),
    (r"years of rev ?ops experience|years of revenue operations", "<<years_similar>>", None),
    (r"compensation requirements|salary requirements", SALARY_TEXT, None),
    (r"years (of )?experience do you have in this role or similar|years experience do you have in this role", "<<years_similar>>", None),
    (r"come to know about|how did you come to know", "<<how_heard>>", None),
    (r"last working day", "Not applicable; I am currently employed.", None),
    (r"total (work )?experience in (a )?similar", "<<years_similar_text>>", r"^1|1-2|0-2|less than 2"),
    (r"please select if you are a|select (the option|which) .{0,30}(citizen|u\.s\. person)", "<<citizenship_option>>", r"<<citizenship_option_rx>>"),
    (r"sponsor", "<<needs_sponsorship>>", r"^<<needs_sponsorship_rx>>\b"),
    (r"relocation (assistance|package|support)|require relocation", "No", r"^no\b"),
    (r"(experience|years) (with|using|in) (datarails|anaplan|adaptive|netsuite|sap|workday|marketo|salesforce|pardot|eloqua|tableau|looker|snowflake|dbt|sql)|fp&a|forex|crypto|i-gaming|pharmaceutical companies", "No", r"^no\b|^0|none|less than"),
    (r"^first name$|preferred first name|what is your preferred first name|^name \(the name you go by\)$|^preferred name", "<<first_name>>", None),
    (r"^last name$|preferred last name", "<<last_name>>", None),
    (r"^email", "<<email>>", None),
    (r"^phone", "<<phone>>", None),
    (r"do you have a linkedin", "Yes", r"^yes"),
    (r"please specify city and state|if .other.{0,20}specify", "<<location_short>>", None),
    (r"linkedin", "<<linkedin_url>>", None),
    (r"pronouns", "<<pronouns>>", r"<<pronouns_rx>>"),
    (r"(legally )?authori[sz]ed to work|eligible to work|right to work|work authori[sz]ation|work status|permanent work authorization|verification of legal right", "<<work_authorized>>", r"^<<work_authorized_rx>>|authorized to work for any employer|citizen"),
    (r"us citizen|u\.s\. citizen", "<<us_citizen>>", r"^<<us_citizen_rx>>"),
    (r"18 (years|or older)|over 18|at least 18", "<<over_18>>", r"^<<over_18_rx>>"),
    (r"relocat", "<<willing_to_relocate>>", r"^<<willing_to_relocate_rx>>"),
    (r"willing to travel|travel to", "<<willing_to_travel>>", r"^<<willing_to_travel_rx>>"),
    (r"background check|drug (screen|test)", "<<background_check_ok>>", r"^<<background_check_ok_rx>>"),
    (r"(previously|ever) (been )?(employed|worked)|worked (here|for|at) .{0,40}before|former employee|interviewed (here|with)|currently employed by|employed (at|with|by) .{0,30}(in the past|previously|for any length)|have you ever worked for", "No", r"^no\b|have not|never"),
    (r"how did you (initially |first )?(hear|learn|find|come across)|where (did|have) you (hear|learn|find)|^source$|referral source|how .{0,20}hear about", "<<how_heard>>", r"career|company (web)?site|website||other job board|job board||^other$||^linkedin"),
    (r"\breferr|know anyone (who|that) (currently )?works|relatives currently employed|family members", "No", r"^no\b|n/?a"),
    (r"familiarity with (artificial intelligence|ai)|rate your .{0,30}(ai|artificial intelligence)", "<<ai_familiarity>>", r"^<<ai_familiarity_rx>>\b"),
    (r"where are you based out of", "Other US city", r"other us city|<<city_rx>>|<<state_rx>>|united states"),
    (r"non-?compete|restrictive covenant", "No", r"^no\b"),
    (r"security clearance|clearance", "<<security_clearance>>", r"^<<security_clearance_rx>>\b"),
    (r"export control|deemed export", "No", r"^no\b"),
    (r"time ?zone", "<<timezone>>", r"<<timezone_rx>>"),
    (r"based in the (us|united states)|currently (reside|live|located) in the (us|united states)|reside in the (us|united states)", "Yes", r"^yes"),
    (r"which (u\.?s\.? )?state|state (do you|you) (currently )?(reside|live)|what state", "<<state>>", r"^<<state_rx>>$"),
    (r"^state$", "<<state>>", r"^<<state_rx>>$"),
    (r"^city$|what city", "<<city>>", None),
    (r"current(ly)? (location|based)|where (are you|do you) (currently )?(located|based|live)|location \(city, state\)|where are you based", "<<location>>", r"<<state_rx>>|<<city_rx>>|united states"),
    (r"country (of residence|where you (currently )?reside)|select the country", "<<country>>", r"united states"),
    (r"(most recent|current) (employer|company)|who is your (most recent|current)", "<<current_employer>>", None),
    (r"(current|most recent) (job )?title", "<<current_title>>", None),
    (r"salary|compensation expectation|expectations for total compensation|total compensation|desired (salary|pay|compensation)|pay expectation", SALARY_TEXT, r"70|75|80"),
    (r"start date|when can you (start|join)|available to (start|join)|by when can you join|earliest start", "<<availability>>", r"immediate|2 weeks|two weeks"),
    (r"(sms|text message|whatsapp|talent community|job alerts|marketing communications)", "No", r"^no\b|opt out|do not"),
    (r"privacy|acknowledge|consent|agree|i have read|recording|ai (policy|in (the )?interview)|terms", "Acknowledge", r"acknowledge|agree|yes|i consent|confirm|accept"),
    (r"bachelor'?s degree|4-year degree|undergraduate degree|highest level of education", "<<degree_level>>", r"bachelor|yes"),
    (r"computer science degree|degree in computer science", "No", r"^no\b"),
    (r"english", "Native / fluent", r"native||c2||fluent||excellent||^yes"),
    (r"salesforce", "No", r"^no\b|0|none"),
    (r"years of (experience|b2b|saas)|how many years", None, None),  # handled specially below
    (r"remote", "Yes", r"^yes"),
    (r"hybrid|in[- ]office|on[- ]site", None, None),  # depends on DFW; handled specially
]
_EEO_DECLINE = r"decline|prefer not|don't wish|do not wish|choose not|not to answer"
# EEO answers are voluntary and personal: option regexes come from profile.json "eeo"; default is to decline.
EEO = [(rx, (P.get("eeo") or {}).get(k) or _EEO_DECLINE) for k, rx in [
    ("gender", r"gender"), ("hispanic", r"hispanic|latino"), ("race", r"race|ethnicit"),
    ("veteran", r"veteran"), ("disability", r"disabilit")]]

# Fill the <<key>> tokens from the profile. An answer the profile leaves empty becomes "" = hold the form.
BANK = [(rx, fill(a) if a is not None else None, fill(pref) if pref else pref) for rx, a, pref in BANK]
HOME_METRO = re.compile(P["home_metro_regex"], re.I)


def fetch(slug, jid):
    r = urllib.request.urlopen(urllib.request.Request(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}?questions=true", headers={"User-Agent": UA}), timeout=30)
    return json.loads(r.read())


def pick(options, pref):
    if not options:
        return None
    if pref:
        for alt in pref.split("||"):
            for o in options:
                if re.search(alt, o, re.I):
                    return o
    return None


def plan(key):
    _, slug, jid = key.split(":")
    d = fetch(slug, jid)
    loc = (d.get("location") or {}).get("name", "")
    dfw = bool(HOME_METRO.search(loc))  # role is in the candidate's home metro
    out = {"key": key, "url": d.get("absolute_url"), "title": d.get("title"), "location": loc, "fields": [], "unknown": [], "blockers": []}
    for q in d.get("questions", []):
        label = re.sub(r"\s+", " ", q["label"]).strip()
        req = q["required"]
        f0 = q["fields"][0]
        typ = f0["type"]
        opts = [v["label"] for f in q["fields"] for v in f.get("values", [])]
        L = label.lower()
        ans = None
        if typ == "input_file":
            if re.search(r"resume|cv", L):
                ans = "__RESUME__"
            elif re.search(r"cover letter", L):
                if req:
                    out["blockers"].append("required cover letter")
                continue
            elif req:
                out["unknown"].append(label)
                continue
            else:
                continue
        pa = private_answer(L, opts)
        if pa is not None and not opts:
            if pa == "":
                if req: out["unknown"].append({"label": label, "type": typ, "options": opts[:12]})
                continue
            out["fields"].append({"label": label, "type": typ, "required": req, "answer": pa, "options": []})
            continue
        if pa and opts:
            pk = pick(opts, re.escape(pa)) or (pick(opts, r"^no\b") if pa == "No" else None)
            if pk:
                out["fields"].append({"label": label, "type": typ, "required": req, "answer": pk, "options": opts[:12]}); continue
        if re.search(r"street address|^address$|mailing address|home address|zip|postal code", L) and req:
            out["blockers"].append(f"needs-address: {label}")
            continue
        if re.search(r"years", L) and re.search(r"how many|number of|years of", L) and not re.search(r"datarails|fp&a|anaplan|marketo|salesforce", L):
            if re.search(r"salesforce|marketo|cybersecurity|fintech|payments|forex|crypto|security", L):
                ans = "0"
            elif re.search(r"b2b saas|saas", L):
                ans = P.get("years_similar", "1")
            elif re.search(r"(llm|ai|automation)", L):
                ans = P.get("years_similar", "1")
                if opts:
                    ans = pick(opts, r"less than 1|<\s?1|0-1|under 1|^1\b|1 year|1-2|1–2")
            elif re.search(r"(sales|outbound|sdr|bdr|business development)", L):
                ans = P.get("years_similar", "1")
            else:
                ans = "1-3 years" if opts else None
            if opts:
                ans = pick(opts, r"^1|1-2|0-2|1-3|less than 2|under 2|^0") or None
        if ans is None and re.search(r"hybrid|in[- ]office|on[- ]?site|commute", L):
            ans = "Yes" if dfw else None
            if opts and ans:
                ans = pick(opts, r"^yes")
        if ans is None:
            for rx, a, pref in BANK:
                if a is None:
                    continue
                if re.search(rx, L, re.I):
                    if a == "":
                        break  # profile has no answer for this: leave it unknown (held if required)
                    if opts:
                        ans = pick(opts, pref)
                    else:
                        ans = a
                    break
        if ans is None and (typ.startswith("multi_value") or opts):
            for rx, pref in EEO:
                if re.search(rx, L):
                    ans = pick(opts, pref) or pick(opts, r"decline|prefer not|don't wish|do not wish")
                    break
        if ans is None:
            if req:
                out["unknown"].append({"label": label, "type": typ, "options": opts[:12]})
            continue
        out["fields"].append({"label": label, "type": typ, "required": req, "answer": ans, "options": opts[:12]})
    # demographic/compliance blocks (Greenhouse 'compliance' + 'demographic_questions') are optional: EEO answers applied in-browser
    return out


if __name__ == "__main__":
    for k in sys.argv[1:]:
        try:
            print(json.dumps(plan(k), indent=1))
        except Exception as e:
            print(json.dumps({"key": k, "error": str(e)}))
