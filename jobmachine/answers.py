#!/usr/bin/env python3
"""answers.py <key> : fetch a posting's form via the public API and map every question
to an answer from the packet's answer bank. Prints JSON plan for the Chrome worker:
{"key","url","fields":[{"label","type","required","answer","options"}],"unknown":[...],"blockers":[...]}
Never invents resume facts. Unknown required questions => listed, job should be skipped."""
import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile import P, fill  # noqa: E402

UA = "Mozilla/5.0"
from jobq import money_vals, family_of, track_of  # noqa: E402
CTX = {"body": "", "fam": None}  # set per posting by plan()

# Completed years by area, from the dated work history (Windows pack 02). Mitchell 2026-11-10: AI since 2021.
YEARS = [
    (r"manag|direct reports|people leader|supervis", 0),
    (r"marketo|pardot|eloqua|netsuite|workday|looker", 0),
    (r"salesforce|sales navigator", 0.5),  # Mitchell 2026-11-10: used, under 1 year -> picks "less than 1" ranges
    (r"tableau|power ?bi|power automate|power apps|power platform|microsoft 365|sharepoint", 1),
    (r"health|medical|patient|clinical|ehr|emr|epic|provider", 4),
    (r"\bai\b|artificial intelligence|llm|automation|python|sql|data analy|analytics|prompt|machine learning", 5),
    (r"software (engineering|development)|professional (software|engineering)|production code", 1),
    (r"quota|closing|full[- ]cycle sales|b2b sales|closing deals", 3),
    (r"crm|rev ?ops|revenue operations|sales operations|operations|hubspot|gohighlevel|airtable", 0),
    (r"sales|business development|\bsdr\b|\bbdr\b|outbound|prospecting|closing", 3),
    (r"total|professional|work experience|relevant experience|overall", 5),
]


def years_for(L):
    for rx, n in YEARS:
        if re.search(rx, L, re.I):
            return n
    return None


def pick_years(opts, n):
    """Pick the dropdown option whose range contains n."""
    for o in opts:
        t = o.lower()
        nums = [int(x) for x in re.findall(r"\d+", t)]
        if not nums:
            if n == 0 and re.search(r"none|no experience|less than|under|^0", t):
                return o
            if 0 < n < 1 and re.search(r"less than|under|some|beginner", t):
                return o
            continue
        lo = nums[0]
        hi = nums[1] if len(nums) > 1 else (99 if re.search(r"\+|more|over|or more|above", t) else lo)
        if re.search(r"less than|under|<", t):
            lo, hi = 0, nums[0] - 0.01
        if lo <= n <= hi:
            return o
    return None


def salary_answer(L):
    if re.search(r"\bote\b|on[- ]target|commission|current (salary|compensation|pay|base)|hourly|per hour|monthly", L):
        return ""  # hold: pack says OTE/commission/hourly/current pay wording needs Mitchell
    floor = int((P.get("track_floors") or {}).get(track_of(CTX["fam"]) if CTX["fam"] else "B", 100000))
    mv = money_vals(CTX["body"])
    if not mv:  # no posted range: ask for a market band instead of the bare floor
        lo = int(P.get("salary_no_range_low", max(floor, 60000)))
        return f"${lo:,} to ${int(lo * 1.25 // 1000 * 1000):,}, flexible for the right role"
    n = max(floor, int(round((min(mv) + max(mv)) / 2, -3)))
    return f"${n:,}"


def why_answer():
    """Short, truthful 'why this role/company' answer built from confirmed facts. Never claims company-specific knowledge."""
    co, title, fam = CTX.get("company") or "your team", CTX.get("title") or "this role", CTX.get("fam") or ""
    health = re.search(r"health|clinic|patient|care|medical|therap|pharm", (co + " " + title + " " + CTX.get("body", "")[:3000]).lower())
    core = ("At HostraGroup I managed 500+ leads through the pipeline in GoHighLevel and Airtable and built the structured follow-up "
            "system behind it, and at Accomplishr I build AI tools like Cami that the team uses every day.")
    if fam in ("ai_fde_se", "entry_swe", "ai_trainer", "gtm_eng"):
        hook = f"The {title} role at {co} is the work I already do: taking a real business problem and shipping an AI or automation system that people actually use."
    elif fam in ("data_analyst", "heads_down"):
        hook = f"The {title} role at {co} is the kind of heads-down systems and data work I do best: turning messy operations into clean, reliable processes and reporting."
    else:
        hook = f"The {title} role at {co} fits how I work: owning a process end to end and making sure nothing falls through the cracks."
    tail = (" I also spent four years supporting clinical teams as a medical assistant and hold a Healthcare Studies degree, so healthcare workflows are familiar ground."
            if health else " I learn new tools and domains fast and I care about the outcome, not just the task list.")
    return hook + " " + core + tail


def private_answer(L, opts=None):
    """Answers from the private profile. None = no rule; '' = leave blank (or unknown if required)."""
    if re.search(r"why (are you|do you want|would you like|you are)|what (excites|interests|draws) you|why .{0,30}(interested|excited)|why (this|our) (role|company|team)|why .{0,20}(join|work (at|for|with))|interest(ed)? in (this|the) (role|position|company)", L) and not opts:
        return why_answer()
    if re.fullmatch(r"\s*(your )?(full|legal) name\s*\??", L) or L.strip() in ("name", "your name"):
        return P.get("full_name", P["first_name"] + " " + P["last_name"])
    if re.search(r"(contractual obligations|non-?compete|restrictive covenant).{0,200}(impact|impede|interfere|prevent|restrict)", L):
        return pick(opts, r"^no\b") if opts else "No"
    if re.search(r"salary|compensation expectation|expected (annual )?(base )?(salary|compensation|pay)|desired (salary|pay|compensation)|pay expectation|expectations for total compensation", L) and not opts:
        return salary_answer(L)
    if re.search(r"(record|notetaker|transcri).{0,60}interview|interview.{0,60}(record|notetaker|transcri)", L) and P.get("ai_interview_recording_ok"):
        return pick(opts, r"consent|^yes|agree|accept") if opts else "Yes"
    if re.search(r"privacy (act )?notice|privacy policy|applicant privacy|ccpa", L) and opts:
        return pick(opts, r"acknowledge|^yes|agree|accept|read|understand")
    if re.search(r"ai policy|policy for (ai|hiring)", L) and P.get("employer_ai_policy_ok"):
        return pick(opts, r"^yes|agree|accept|acknowledge") if opts else "Yes"
    if re.search(r"tobacco|smok|nicotine", L) and P.get("smoke_free"):
        return pick(opts, r"non-?smoker|^yes|agree") if opts else "Yes"
    if re.search(r"deemed export|export licen[cs]e|ear[- ]controlled|itar", L) and opts:
        return pick(opts, r"^yes")  # US citizen: meets export-control requirements
    if re.search(r"confirm (your )?understanding|i understand that|acknowledge that this role requires", L) and opts:
        return pick(opts, r"^yes|agree|understand|acknowledge|confirm")
    if re.search(r"^(legal address - )?state(/province)?\s*\??$|^state of residence", L):
        return pick(opts, r"^tx$|^texas") if opts else P.get("state", "Texas")
    if re.search(r"^legal address - city", L):
        return P.get("address_city", P.get("city", "Dallas"))
    if re.search(r"(street )?address (line )?2|address 2|apt|suite|unit number", L) and not opts:
        return ""
    if re.search(r"^legal address - country|^country of residence", L):
        return pick(opts, r"^united states$|^united states of america|^usa?$") if opts else "United States"
    if re.search(r"over the age of 18|at least 18|18 years of age", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"high school diploma|\bged\b", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"desired hourly|hourly (pay|rate)|expected hourly", L) and not opts:
        return P.get("hourly_text", "")
    if re.search(r"work eligibility status|citizenship status|work authorization status", L) and opts:
        return pick(opts, r"u\.?s\.? citizen|citizen")
    if re.search(r"(current|active) (level of )?security clearance|clearance level", L) and opts:
        return pick(opts, r"^none|no clearance|^n/?a|^no\b")
    if re.search(r"hereby certify|i (verify|certify|attest) that|true,? (complete|accurate) and correct|information .{0,40}is true", L):
        return pick(opts, r"acknowledge|agree|^yes|certify|true") if opts else "Yes"
    if re.search(r"employment is at will|at-will", L) and opts:
        return pick(opts, r"^yes|agree|understand|acknowledge")
    if re.search(r"performed from within the united states|lived in the united states for at least", L):
        return pick(opts, r"agree|^yes") if opts else "Yes"
    if re.search(r"attendance requirements|able to meet the (schedule|attendance)", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"(rn|lpn|registered nurse|nursing) (license|certification)|do you have an? (rn|lpn)", L) and opts:
        return pick(opts, r"^no\b")
    if re.search(r"share your resume.{0,60}(clients|prospective)", L) and opts:
        return pick(opts, r"^yes")
    if re.search(r"(apis?|rest|webhooks?)\b.{0,40}(experience|familiar)|experience .{0,40}(rest|webhooks|apis)\b", L) and opts:
        return pick(opts, r"^yes")
    if re.search(r"(currently|ever been|previously been) (employed|work(ed)?) (by|at|for)|do you currently work at|currently an? (employee|contractor)", L) and opts:
        return pick(opts, r"^no\b|not applicable|^n/?a|never")
    if re.search(r"(family|relative)s?.{0,60}(work(ing)?|employed) (for|at|by)", L) and opts:
        return pick(opts, r"^no\b|not applicable|^n/?a")
    if re.search(r"when can you begin|begin (full-time )?work|available to begin", L) and not opts:
        return "Immediately"
    if re.search(r"\brefer(red|ral)?\b", L) and re.search(r"name|who|indicate|relationship", L) and not opts:
        return "N/A"
    if re.fullmatch(r"\s*(current )?location\s*\??", L) or re.search(r"^(city|current city), state\s*\??$", L):
        return P.get("location_short", "Dallas, TX")
    if re.fullmatch(r"\s*(current )?city\s*\??", L):
        return P.get("address_city", P.get("city", "Dallas"))  # matches the street address and ZIP
    if re.search(r"comfortable with the location requirement|able to meet the location requirement", L):
        return "Yes"
    if re.search(r"legally (eligible|authorized|able) (for|to) (employment|work)", L):
        return "Yes"
    if re.search(r"workflow automation (platform|tool)|integration platforms?|ipaas|automation tools? (have you|do you)", L):
        return "Yes" if opts else "Yes. Make, n8n and Zapier, plus GoHighLevel workflows and Airtable automations."
    if re.search(r"when (could|can|would) you start|start date|earliest (start|available)", L) and not opts:
        return "Immediately"
    if re.search(r"what hours are you available|hours (of )?availability", L) and not opts:
        return "Full-time, and flexible across US time zones"
    if re.search(r"(other|outside|secondary) employment|currently employed elsewhere|other (jobs|work commitments)", L) and not re.search(r"sponsor|visa|immigration|h-?1b|authoriz", L):
        return ""  # Mitchell 2026-11-11: don't volunteer other jobs; never answer falsely -> hold for him
    if re.search(r"convicted|pleaded guilty|criminal (offense|record|conviction)|felony|misdemeanor", L):
        if re.search(r"explain|describe|if (yes|you have)", L) and not opts:
            return "N/A"
        return pick(opts, r"^no\b|^n/?a") if opts else "No"  # Mitchell 2026-11-11: never convicted
    if re.search(r"commit (to )?(this role )?full[- ]time|exclusive(ly)? employ|devote full|screen monitoring|keystroke|activity monitoring", L):
        return "Yes"
    if re.search(r"(able|willing) to travel up to \d+ ?%", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"(what|how much).{0,30}(percent|%).{0,20}travel|travel.{0,30}(percent|%)", L) and not opts:
        return P.get("max_travel", "")
    if re.search(r"driver'?s licen[sc]e", L):
        return P.get("drivers_license", "")
    if re.search(r"reliable (transportation|vehicle)|own (a )?(car|vehicle)|access to a (car|vehicle)", L):
        return P.get("own_car", "")
    if re.search(r"countr(y|ies).{0,40}(reside|live|located|based|anticipate working)|^country$|countries you anticipate", L):
        return pick(opts, r"^united states|^usa?$|^us\b") if opts else "United States"
    if re.search(r"(current|previous|most recent) (job )?title", L):
        return P.get("current_title", "")
    if re.search(r"export control|authori[sz]ation status|u\.?s\.? persons?", L) and opts and any(re.search(r"u\.?s\.? citizen", o, re.I) for o in opts):
        return pick(opts, r"^u\.?s\.? citizen|^citizen|u\.?s\.? citizen")
    if re.search(r"sanctions|export control", L) and opts:
        return pick(opts, r"none of the above|not applicable|^none|^no\b") or ""
    if re.search(r"if you selected a response to the prior question other than", L):
        return pick(opts, r"none|not applicable|n/?a") if opts else "N/A"
    if re.search(r"work authori[sz]ation status|citizenship status|immigration status", L):
        return pick(opts, r"citizen|authorized to work|no sponsorship") if opts else "US citizen, authorized to work in the US without sponsorship"
    if re.search(r"(describe|explain).{0,60}(revenue cycle|medical (billing|coding)|insurance billing|claims|prior auth)", L) and not opts:
        return ("No dedicated revenue cycle or coding role yet. Four years as a medical assistant across internal medicine, pulmonology, "
                "orthopedics and sports medicine handling patient intake, documentation and care coordination in Epic and eClinicalWorks, "
                "plus a B.S. in Healthcare Studies. I also built Before You Pay, a medical bill rights checker built on CMS data covering "
                "itemized bills, financial assistance and surprise-bill protections.")
    if re.search(r"^i certify|certify that the information|attest that", L):
        return pick(opts, r"^yes|i certify|agree|acknowledge|confirm") if opts else "Yes"
    if re.search(r"authori[sz]ed to (reside|live) and work|in the (us|u\.s\.|united states) right now", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"what city (&|and) state|city and state do you (live|reside)|^city,? state", L):
        return f"{P.get('address_city', '')}, {P.get('state_abbr', 'TX')}"
    if re.search(r"open to travel|willing to travel|able to travel", L) and not re.search(r"percent|%|how much", L):
        return pick(opts, r"^yes") if opts else "Yes"
    if re.search(r"^what is your preferred name|^preferred name", L):
        return P.get("first_name", "")
    if re.search(r"(do you have|list).{0,20}certifications", L):
        return pick(opts, r"none|^no\b|not applicable") if opts else "No"
    if re.search(r"(where|how) have you (experimented|used|applied) (with )?(ai|it|llms?|generative ai)|(experience|experimented) (with|using) (ai|generative ai|llms?) (in|for) your (own )?work|how do you use ai", L) and not opts:
        return ("I use AI every day to do the work, not just to talk about it. At HostraGroup I built an operations bot that sweeps 8 data "
                "sources every hour and sorts each issue into one of 6 verdicts, graded against a 67-case eval suite so I know when it is wrong. "
                "At Accomplishr I built Cami, a Slack assistant on Claude that answers staff questions from a knowledge page and escalates what "
                "it can't answer. Where it falls short is anything without a clear source of truth: it guesses confidently, so I put evals and a "
                "human check on anything that touches a customer or a number. In a role like this, the biggest impact is on the repetitive "
                "reporting and data-cleanup work, so people spend their time on the decisions instead of the spreadsheets.")
    if re.search(r"agentic ai (experience|tools)|agentic (ai )?(tools|workflows).{0,40}(built|implemented)", L) and not opts:
        return ("Three I built and run: Milo, a multi-agent system where one Chief routes work to 18 specialist bots across four rooms "
                "(Python, Claude, pytest, 62 skills); Cami, a Slack assistant on Claude for Accomplishr that answers staff questions from a "
                "knowledge page, runs a second search when needed and escalates what it can't answer, with an evaluation harness; and an "
                "operations bot at HostraGroup with an hourly sweep across 8 data sources and a 6-verdict classifier graded by a 67-case eval "
                "suite. I can demo Milo's routing and Cami's eval harness live.")
    if re.search(r"client-facing experience|translate business requirements into technical", L) and not opts:
        return ("Yes. At HostraGroup I run discovery calls with homeowners and turn what they need into the onboarding pipeline and "
                "automations behind it (500+ leads, 45+ signed agreements). At Accomplishr I build AI tools like Cami from what staff and "
                "experts ask for, and train teammates on AI tools in group sessions and one-on-one.")
    if re.search(r"proficien|skill level|rate your|level of (experience|expertise|comfort)|how (comfortable|experienced)", L):
        pf = P.get("proficiency") or {}
        if pf.get("none") and re.search(pf["none"], L):
            if not opts:
                return "None"
            o = pick(opts, r"^none|no experience|not familiar|^0|never")
            return o or ""
        if pf.get("intermediate") and re.search(pf["intermediate"], L):
            if not opts:
                return "Intermediate"
            return pick(opts, r"intermediate|proficient|moderate|^3\b|comfortable") or ""
        if pf.get("beginner") and re.search(pf["beginner"], L):
            if not opts:
                return "Beginner"
            return pick(opts, r"beginner|basic|novice|familiar|^2\b|some") or ""
    if re.search(r"\bgpa\b|grade point", L):
        return P.get("gpa", "")
    if P.get("portfolio_url") and re.search(r"portfolio|personal (web)?site|^website|website url|other website|blog", L) and not re.search(r"user ?name|handle", L):
        return P["portfolio_url"]
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
    (r"(eligible|authori[sz]ed|right) to work[^?]{0,80}without[^?]{0,30}sponsorship|(currently )?have (work|employment) authori[sz]ation", "<<work_authorized>>", r"^<<work_authorized_rx>>"),
    (r"sponsor", "<<needs_sponsorship>>", r"^<<needs_sponsorship_rx>>\b"),
    (r"relocation (assistance|package|support)|require relocation", "No", r"^no\b"),
    (r"(experience|years) (with|using|in) (datarails|anaplan|adaptive|netsuite|sap|workday|marketo|pardot|eloqua|looker|snowflake|dbt)|fp&a|forex|crypto|i-gaming|pharmaceutical companies", "No", r"^no\b|^0|none|less than"),
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
    (r"(currently|presently)? ?(based|reside|residing|located|living|live) in (the )?(country|us\b|u\.s|united states)[^?]{0,60}(or|and).{0,40}relocat", "Yes", r"^yes"),
    (r"relocat", "<<willing_to_relocate>>", r"^<<willing_to_relocate_rx>>(?!,? ?but)(?!.*willing)"),
    (r"willing to travel|travel to", "<<willing_to_travel>>", r"^<<willing_to_travel_rx>>"),
    (r"background check|drug (screen|test)", "<<background_check_ok>>", r"^<<background_check_ok_rx>>"),
    (r"(previously|ever) (been )?(employed|worked)|worked (here|for|at) .{0,40}before|former employee|interviewed (here|with)|currently employed by|employed (at|with|by) .{0,30}(in the past|previously|for any length)|have you ever worked for", "No", r"^no\b|have not|never"),
    (r"how did you (initially |first )?(hear|learn|find|come across)|where (did|have) you (hear|learn|find)|^source$|referral source|how .{0,20}hear about", "<<how_heard>>", r"^(other )?job board|online job|job (search|posting) (site|board)||company (web)?site|careers? (site|page)|website||^other$||^linkedin"),
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
    (r"privacy|acknowledge|consent|\bagree\b|i have read|recording|ai (policy|in (the )?interview)|\bterms\b", "Acknowledge", r"acknowledge|agree|yes|i consent|confirm|accept"),
    (r"bachelor'?s degree|4-year degree|undergraduate degree|highest level of education", "<<degree_level>>", r"bachelor|yes"),
    (r"computer science degree|degree in computer science", "No", r"^no\b"),
    (r"english", "Native / fluent", r"native||c2||fluent||excellent||^yes"),
    (r"salesforce|sales navigator|power ?bi|tableau|power automate|power apps|microsoft 365", "Yes", r"^yes"),
    (r"(open|willing|interested|consider|available|okay|ok)\b.{0,40}(contract|1099|part[- ]time|temporary|freelance)|(contract|1099|temporary|freelance) (role|position|basis|work|engagement)", "<<contract_ok>>", r"^yes"),
    (r"(work|available|comfortable|willing).{0,60}(time ?zones?|eastern hours|pacific hours|\b(est|pst|et|pt)\b hours|overlap with)", "<<other_timezones_ok>>", r"^yes"),
    (r"night|weekend|evening|overnight|shift", "<<nights_weekends_ok>>", r"^yes"),
    (r"years of (experience|b2b|saas)|how many years", None, None),  # handled specially below
    (r"remote", "Yes", r"^yes"),
    (r"hybrid|in[- ]office|on[- ]site", None, None),  # depends on DFW; handled specially
]
_EEO_DECLINE = r"decline|prefer not|don't wish|do not wish|choose not|not to answer"
# EEO answers are voluntary and personal: option regexes come from profile.json "eeo"; default is to decline.
EEO = [(rx, (P.get("eeo") or {}).get(k) or _EEO_DECLINE) for k, rx in [
    ("gender", r"gender"), ("hispanic", r"hispanic|latino"), ("race", r"race|ethnicit"),
    ("veteran", r"veteran"), ("disability", r"disabilit"),
    ("orientation", r"sexual orientation|lgbtq|lgbt")]]

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
    import html as _h
    CTX["body"] = re.sub(r"<[^>]+>", " ", _h.unescape(d.get("content", "")))
    CTX["fam"] = family_of(d.get("title", ""))[1]
    CTX["title"] = d.get("title", ""); CTX["company"] = (d.get("company_name") or slug.replace("-", " ").title())
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
            pk = (pick(opts, "^" + re.escape(pa) + "$") or pick(opts, r"\b" + re.escape(pa) + r"\b")
                  or (pick(opts, r"^no\b") if pa == "No" else None))  # exact first: "US" must not match "Australia"
            if pk:
                out["fields"].append({"label": label, "type": typ, "required": req, "answer": pk, "options": opts[:12]}); continue
        if P.get("address_line") and not opts and re.search(r"street address|^address( line 1)?$|mailing address|home address|zip|postal code|^city$", L):
            full = f'{P["address_line"]}, {P["address_city"]}, {P.get("state_abbr", "TX")} {P["address_zip"]}'
            a = full if re.search(r"full address|street,? city|address.{0,20}city.{0,20}(state|zip)", L) else P["address_zip"] if re.search(r"zip|postal", L) else (P["address_city"] if L == "city" else (full if L in ("address", "home address", "mailing address") else P["address_line"]))
            out["fields"].append({"label": label, "type": typ, "required": req, "answer": a, "options": []}); continue
        if re.search(r"street address|^address$|mailing address|home address|zip|postal code", L) and req:
            out["blockers"].append(f"needs-address: {label}")
            continue
        if re.search(r"years", L) and re.search(r"how many|number of|years of|years'? experience", L) and not re.search(r"describe|explain|tell us", L):
            n = years_for(L)
            if n is not None:
                ans = (pick_years(opts, n) if opts else ("Less than 1 year" if 0 < n < 1 else str(n)))
        if ans is None and re.search(r"hybrid|in[- ]office|on[- ]?site|commute", L):
            ans = "Yes" if dfw else "No"  # Mitchell 2026-11-10: hybrid/on-site is fine inside DFW
            if opts and ans:
                ans = pick(opts, r"^yes\b" if dfw else r"^no\b")
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
        if typ == "textarea" and str(ans).strip().lower() in ("yes", "no") and not re.search(r"^(are|do|did|have|has|is|will|would|can|could)\b", L):
            if req:
                out["unknown"].append({"label": label, "type": typ, "options": []})
            continue  # an essay question never gets a bare Yes/No
        out["fields"].append({"label": label, "type": typ, "required": req, "answer": ans, "options": opts[:12]})
    # demographic/compliance blocks (Greenhouse 'compliance' + 'demographic_questions') are optional: EEO answers applied in-browser
    return out


if __name__ == "__main__":
    for k in sys.argv[1:]:
        try:
            print(json.dumps(plan(k), indent=1))
        except Exception as e:
            print(json.dumps({"key": k, "error": str(e)}))
