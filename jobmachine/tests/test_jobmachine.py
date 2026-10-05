"""Offline tests for the job machine. Run from the repo root:

    python3 -m unittest discover -s jobmachine/tests

They use profile.example.json and a temp data dir, never the real profile, and make no network calls.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="jobmachine-test-")
os.environ["JOBMACHINE_PROFILE"] = os.path.join(ROOT, "profile.example.json")
os.environ["JOBMACHINE_DATA"] = TMP
os.environ.pop("JOBQ_DB", None)
sys.path.insert(0, ROOT)

import answers  # noqa: E402
import jobq  # noqa: E402
import profile  # noqa: E402

def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


BODY = "You will build automations and integrations for customers using APIs and workflow tools. " * 3


class ProfileTests(unittest.TestCase):
    def test_tokens_fill_from_profile(self):
        self.assertEqual(profile.fill("<<first_name>> <<last_name>>"), "Ada Example")
        self.assertEqual(profile.P["location_short"], "Austin, TX")

    def test_unknown_token_raises(self):
        with self.assertRaises(KeyError):
            profile.fill("<<no_such_key>>")

    def test_empty_fact_never_matches_an_option(self):
        # us_citizen is blank in the example: its option regex must match nothing.
        self.assertIsNone(answers.pick(["Yes", "No"], profile.P["us_citizen_rx"]))

    def test_every_template_token_resolves(self):
        import re
        for fn in ("answers.py", "ashby_answers.py", "lever_answers.py", "jobq.py"):
            src = _read(os.path.join(ROOT, fn))
            for tok in set(re.findall(r"<<(\w+)>>", src)) - {"key"}:
                self.assertIn(tok, profile.P, f"{fn} uses <<{tok}>> but the profile has no such key")


class AnswerBankTests(unittest.TestCase):
    def answer(self, label, opts=None):
        for rx, a, pref in answers.BANK:
            if a is None:
                continue
            if __import__("re").search(rx, label.lower(), __import__("re").I):
                if a == "":
                    return None
                return answers.pick(opts, pref) if opts else a
        return None

    def test_contact_answers_come_from_profile(self):
        self.assertEqual(self.answer("Email"), "ada@example.com")
        self.assertEqual(self.answer("LinkedIn Profile"), "https://linkedin.com/in/example")

    def test_blank_profile_fact_leaves_question_unknown(self):
        self.assertIsNone(self.answer("Are you a US citizen?", ["Yes", "No"]))
        self.assertEqual(answers.private_answer("github profile"), "")  # blank github -> hold if required

    def test_eeo_defaults_to_decline(self):
        opts = ["Male", "Female", "Decline to self-identify"]
        gender_pref = dict((rx, pref) for rx, pref in answers.EEO)["gender"]
        self.assertEqual(answers.pick(opts, gender_pref), "Decline to self-identify")


class GateTests(unittest.TestCase):
    def test_remote_us_target_role_passes(self):
        st, fam, *_ = jobq.gate("Forward Deployed Engineer", "Remote - US", BODY, "acme")
        self.assertEqual((st, fam), ("gate_passed", "ai_fde_se"))

    def test_senior_title_fails(self):
        self.assertEqual(jobq.gate("Senior Solutions Engineer", "Remote", BODY, "acme")[0], "gate_failed")

    def test_non_us_fails(self):
        self.assertEqual(jobq.gate("Solutions Engineer", "London, UK", BODY, "acme")[0], "gate_failed")

    def test_five_years_required_fails(self):
        body = BODY + " Requirements: 5+ years of experience in solutions engineering."
        self.assertEqual(jobq.gate("Solutions Engineer", "Remote", body, "acme")[0], "gate_failed")

    def test_home_metro_onsite_passes_other_metro_fails(self):
        self.assertEqual(jobq.gate("Revenue Operations Analyst", "Austin, TX", BODY, "acme")[0], "gate_passed")
        self.assertEqual(jobq.gate("Revenue Operations Analyst", "Chicago, IL", BODY, "acme")[0], "gate_failed")


class AshbyParseTests(unittest.TestCase):
    def test_hybrid_posting_flagged_remote_is_not_treated_as_remote(self):
        import ats_sweep
        board = {"jobs": [
            {"id": "a", "title": "Revenue Operations Analyst", "location": "Boulder Office",
             "isRemote": True, "workplaceType": "Hybrid", "descriptionPlain": BODY},
            {"id": "b", "title": "Revenue Operations Analyst", "location": "United States",
             "isRemote": True, "workplaceType": "Remote", "descriptionPlain": BODY},
        ]}
        real_get = ats_sweep.get
        ats_sweep.get = lambda url: (200, board)
        try:
            _, _, jobs = ats_sweep.ashby("acme")
        finally:
            ats_sweep.get = real_get
        locs = {j["id"]: j["loc"] for j in jobs}
        self.assertEqual(locs["a"], "Boulder Office")
        self.assertIn("Remote", locs["b"])
        self.assertEqual(jobq.gate("Revenue Operations Analyst", locs["a"], BODY, "acme")[0], "gate_failed")


class LedgerImportTests(unittest.TestCase):
    def test_import_ledger_reads_urls_and_sets_cooldown(self):
        md = os.path.join(TMP, "log.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("| # | Date | Company | Role | URL |\n|---|---|---|---|---|\n"
                    "| 1 | 2026-10-03 | Acme | GTM Engineer | https://job-boards.greenhouse.io/acme/jobs/123 |\n"
                    "| 2 | 2026-10-04 | Beta | FDE | https://jobs.ashbyhq.com/beta/0b1c2d3e-0000-4000-8000-000000000000 |\n")
        env = dict(os.environ)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "jobq.py"), "import-ledger", md],
                             capture_output=True, text=True, env=env)
        self.assertIn("imported: 2", out.stdout, out.stderr)
        c = jobq.conn()
        keys = {r["key"] for r in c.execute("SELECT key FROM ledger")}
        self.assertIn("gh:acme:123", keys)
        until = c.execute("SELECT until FROM cooldown WHERE slug='acme'").fetchone()["until"]
        c.close()
        self.assertEqual(until, "2026-10-10")


class PrivacyTests(unittest.TestCase):
    def test_private_files_are_ignored(self):
        ignore = _read(os.path.join(ROOT, ".gitignore"))
        for pat in ("profile.json", "data/", "*.db"):
            self.assertIn(pat, ignore)

    def test_example_profile_is_placeholder_only(self):
        ex = json.loads(_read(os.path.join(ROOT, "profile.example.json")))
        self.assertTrue(ex["email"].endswith("@example.com"))
        self.assertEqual(ex["phone"], "555-555-0100")


if __name__ == "__main__":
    unittest.main()
