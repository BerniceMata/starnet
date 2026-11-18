# Job Machine handoff for a cyber / GRC candidate

This is the same machine that produced 275 confirmed applications for Mitchell in 4 days. It works because of three things your first run did not have:

1. **A seed list of ~8,000 live company boards** (`seeds/`). You do not search Google. You do not guess company names. The boards are already here.
2. **A regex gate, not an LLM gate** (`jobq.py`). Screening a posting costs zero Claude tokens, so it can check a quarter million postings without hitting a usage limit.
3. **Screening never touches your Chrome.** It reads the public Greenhouse, Ashby and Lever APIs from a terminal. Chrome is used for exactly one thing: filling and submitting a form you are watching.

Everything about you lives in one file, `profile.json`. You never edit Python.

---

## What you need on your computer

- Python 3.9 or newer (`python3 --version`)
- Chrome with the Claude in Chrome extension, signed into the Google account you apply with
- A Claude Code session with a shell (not a chat-only session). The sweep runs as a script; a chat session with no terminal cannot run it.
- Your resume as a PDF

## Setup (10 minutes, once)

```bash
git clone https://github.com/BerniceMata/starnet.git
cd starnet
git checkout feat/job-machine
cd jobmachine
python3 -m pip install beautifulsoup4
cp profile.cyber.example.json profile.json
mkdir -p data
cp /path/to/your/resume.pdf data/resume.pdf
```

Now open `profile.json` and fill every empty value with your real answer. Rules:

- Leave a value empty if you are not sure. The machine will HOLD any form that needs it rather than guess.
- `home_metro_regex` is set to `(?!x)x` which means **remote only**. Leave it unless you also want on-site roles in your city.
- `comp_floor_base` is 125000. Any posting that states a max under that is skipped.
- `max_years_required` is 20. Postings asking for more years than that are skipped. (Mitchell's is 3. Yours is 20 because you have the years.)
- `families` is your title gate. Three lanes are preloaded: GRC, cyber risk, secops. Add or remove a regex if a title you want keeps getting "not a target family."
- `banned_regex` kills interns, dev roles, VP/Chief/CISO, and non-English roles. Senior and Manager are NOT banned for you.
- `eeo` is optional. Leave it empty and the machine selects "decline to answer" on every form.

Then:

```bash
python3 jobq.py init
python3 jobq.py add-boards seeds/greenhouse.txt greenhouse
python3 jobq.py add-boards seeds/ashby.txt ashby
python3 jobq.py add-boards seeds/lever.txt lever
python3 -m unittest discover -s tests      # must say OK
```

If you already applied somewhere, put those URLs in a text file and run `python3 jobq.py import-ledger that_file.md` so you never double-apply.

## Daily run (what Claude does, with you watching)

Paste the prompt at the bottom of this file as the first message of a fresh Claude Code session opened in the `jobmachine` folder. Then the loop is:

```bash
python3 run_sweep.py --budget 100      # pulls new postings from ~700 boards per run; run it 3 or 4 times to cover the list
python3 jobq.py stats                  # how many passed the gate
python3 jobq.py list gate_passed 20    # the top postings that passed
python3 jobq.py reserve mac 5          # claim the next 5 for this machine (use 'windows' on a PC)
```

For each posting Claude will:

1. Run `python3 answers.py <key>` (or `ashby_answers.py` / `lever_answers.py`). This maps every form question to an answer from your `profile.json`. Anything it cannot answer from your profile shows up under `unknown`.
2. If `unknown` is empty: open the form in your Chrome, upload `data/resume.pdf`, run the fill script twice, read the form back to you.
3. You say "submit" or "hold." Claude never submits on its own.
4. `python3 jobq.py mark <key> submitted` writes the ledger and starts a 7-day cooldown on that company.

## The two walls your first run hit, and what to do

**Greenhouse emailed security code.** Greenhouse asks for an 8-character code by email when a session looks untrusted. Two causes in your log: the browser had just been rate-limited (406) from scraping, and it was the first application from that session. Fixes:
- Never scrape from Chrome again. The sweep script does that now.
- Apply from your normal, long-lived Chrome profile, signed in, with history.
- When the code email arrives, you type it. That takes 10 seconds and it is your rule to keep it that way.
- Spread submissions out. 10 to 20 a day from one browser is normal. 60 in an hour is a bot signature.

**Claude usage limit.** You burned it on 4 parallel screening agents reading postings with the LLM. The sweep script does the same job for free. Claude's reasoning is only spent on the answer plan for a posting that already passed the gate.

## The fit bar

Your first run required "meets every hard requirement, 90%+ fit." That rejected 261 of 273. Mitchell's bar is "right title family, nothing disqualifying," and the hold logic catches the ones that need a human. Keep your bar wide at the gate. The form itself, and you reading it before submit, is where judgment goes. At 4% pass rate you reach 2,000 applications never. At the wide bar you reach 10 to 30 submissions a day.

## What stays private

`profile.json`, `data/`, your resume, and your ledger are git-ignored. Do not commit them. Do not paste them into a chat log you share.

---

## Startup prompt (paste as the first message in Claude Code, opened in the `jobmachine` folder)

```
You are my job application machine. I give you permission to apply to jobs in my name using Claude in Chrome on this computer, one form at a time, while I watch.

Read HANDOFF_CYBER.md and README.md in this folder first. My profile is profile.json. It is the ONLY source of answers for any form. Never invent an answer. If a required question is not answerable from profile.json, hold the job and tell me what it asked.

Each session:
1. Run python3 run_sweep.py --budget 100 three times, then python3 jobq.py stats.
2. Run python3 jobq.py reserve mac 5 (or 'windows' on a PC) to claim the next 5. For each one: run the matching answers script. If unknown is empty, open the form in my Chrome, upload data/resume.pdf, run the fill script twice, and read the completed form back to me.
3. Wait for me to say submit. Then click submit, confirm the thank-you page, and run python3 jobq.py mark <key> submitted.
4. If Greenhouse asks for an emailed security code, stop and tell me. I enter it.
5. Do not solve CAPTCHAs. Do not scrape job boards through Chrome. Do not run parallel browser sessions. Do not apply to a company twice in 7 days.

Remote only. $125K base minimum. No roles requiring an active clearance. Hold anything with a required essay, cover letter, or personal-anecdote question and show me the question so I can answer it.
```
