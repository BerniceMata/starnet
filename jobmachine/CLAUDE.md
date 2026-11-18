# jobmachine: rules for the Claude Code session that runs this folder

Claude Code reads this file automatically when opened in this folder. It applies to any candidate running the machine. The candidate's own facts live in `profile.json`; their own rules live in the startup prompt they paste. This file is about how the machine runs.

## 1. Where this must run

This folder runs on the candidate's own computer, in Claude Code with a terminal. Not in a chat-only session. Not in a cloud workspace with a network allowlist.

Reason: `run_sweep.py` reads three public job feeds directly. Cloud chat workspaces often block them. The candidate's own computer does not.

**First command of every session, before anything else:**

```bash
for u in "https://boards-api.greenhouse.io/v1/boards/stripe/jobs" "https://api.lever.co/v0/postings/lever?mode=json" "https://jobs.ashbyhq.com/api/non-user-graphql"; do printf "%s -> " "$u"; curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 "$u"; done
```

All three must print `200`. If any prints `000` or an error, stop and tell the candidate: "This session cannot reach the job feeds. Open Claude Code in a terminal on your own computer, in this folder, and run me there." Do not try to work around a blocked feed by scraping through Chrome. That is what gets the browser rate-limited and triggers Greenhouse security codes.

## 2. Division of labor

| Step | Who does it | Tool |
|---|---|---|
| Find postings | script | `run_sweep.py` (public APIs, zero Claude tokens) |
| Gate by title, location, pay, years | script | `jobq.py` regex, driven by `profile.json` |
| Plan answers for one form | script | `answers.py` / `ashby_answers.py` / `lever_answers.py` |
| Fill the form | Claude | Claude in Chrome, one tab, one form at a time |
| Decide to submit | candidate | says "submit" or "hold" |
| Record it | script | `jobq.py mark <key> submitted` |

Never use Claude reasoning to screen postings. Never spin up parallel agents to read job descriptions. The scripts do that for free. Claude's tokens are spent only on the form in front of it.

## 3. Truth rules

- `profile.json` and the resume in `data/` are the only sources for any form answer. If a required question is not answerable from them, hold the job and show the candidate the question verbatim.
- The resume in `data/` is the candidate's confirmed resume. Do not re-ask whether its bullets are true. If a bullet looks like it was drafted by a previous Claude session, ask once, get a yes or a correction, and never ask again.
- Never invent a tool, a year count, a certification, a clearance, or a metric.
- Empty values in `profile.json` are deliberate. They mean "hold forms that need this." Do not fill them in.

## 4. Browser rules

- One form at a time in the candidate's normal, signed-in Chrome profile. No incognito, no fresh profile, no parallel tabs submitting.
- Upload the resume first, then run the fill script twice, then read the completed form back to the candidate before submit.
- Greenhouse emailed security code: stop, tell the candidate, they type it. Never try to read their email for it.
- CAPTCHA or "verify you are human": stop and tell the candidate. Never solve it.
- Do not scrape, search, or browse job boards through Chrome. Chrome is for filling and submitting only.
- Pace: 10 to 20 submissions per day from one browser is normal. Do not try to do 60 in an hour.

## 5. Volume

The goal is applications submitted, not postings analyzed. The gate in `profile.json` is deliberately wide: right title family, nothing disqualifying. Judgment happens when the candidate reads the filled form, not at screening. Do not tighten the bar on your own, and do not reject a gate-passed posting because it "doesn't feel like a 90% fit." If the gate passed it and the answer plan has no unknowns, fill it and let the candidate decide.

If the candidate's pass rate seems low, the fix is editing `families` or `banned_regex` in `profile.json`, not a stricter screen.

## 6. Session loop

```bash
# 1. feeds reachable? (section 1)
python3 run_sweep.py --budget 100        # run 3 or 4 times
python3 jobq.py stats
python3 jobq.py list gate_passed 20
python3 jobq.py reserve mac 5            # or: reserve windows 5
# for each reserved key:
python3 answers.py <key>                 # gh: keys; ashby_answers.py / lever_answers.py for the others
# unknown empty -> fill in Chrome, read back, wait for "submit"
python3 jobq.py mark <key> submitted
```

Report at the end of every session: submitted, held (with the question that caused each hold), skipped, and the next 5 in the queue.

## 7. Never

- Never commit `profile.json`, `data/`, or the resume. They are git-ignored for a reason.
- Never push to this repo unless the candidate says so.
- Never email anyone, post anywhere, or contact a recruiter from this folder. This folder submits application forms, nothing else.
