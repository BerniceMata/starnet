import os, sys, csv, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobq


class MergedLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        w = csv.DictWriter(self.tmp, fieldnames=["company", "role", "ats", "job_url_or_id", "applied_date", "status", "source"])
        w.writeheader()
        w.writerow(dict(company="Luma Health", role="Sales Development Representative", ats="greenhouse", job_url_or_id="8827865002", applied_date="2026-01-01", status="applied", source="t"))
        w.writerow(dict(company="Opus AI", role="SDR", ats="indeed", job_url_or_id="", applied_date=jobq.datetime.now(jobq.timezone.utc).date().isoformat(), status="applied", source="t"))
        self.tmp.close()
        jobq.MERGED_LEDGER, jobq._MERGED = self.tmp.name, None

    def tearDown(self):
        os.unlink(self.tmp.name); jobq._MERGED = None

    def test_job_id(self):
        self.assertIn("job id", jobq.merged_dupe("Luma", "lumahealth", "Anything", "8827865002", "u"))

    def test_company_role(self):
        self.assertIn("company+role", jobq.merged_dupe("Luma Health, Inc.", "lumahealth", "Sales Development Representative", "1", "u"))

    def test_seven_day_company(self):
        self.assertIn("7-day", jobq.merged_dupe("Opus AI", "opus", "Data Analyst", "2", "u"))

    def test_clean(self):
        self.assertIsNone(jobq.merged_dupe("Acme", "acme", "Data Analyst", "3", "u"))


class Gate(unittest.TestCase):
    def test_never_own_employer(self):
        self.assertEqual(jobq.gate("Data Analyst", "Remote", "remote role", "hostragroup")[3], "never apply: own employer")

    def test_allowed_manager(self):
        self.assertNotEqual(jobq.gate("Customer Success Manager", "Remote", "x", "acme")[3], "title seniority/banned word")

    def test_track_of(self):
        self.assertEqual(jobq.track_of("ai_fde_se"), "B")
        self.assertEqual(jobq.track_of("data_analyst"), "A")

    def test_new_families(self):
        self.assertEqual(jobq.family_of("Healthcare Data Analyst")[1], "data_analyst")
        self.assertEqual(jobq.family_of("Prior Authorization Specialist")[1], "hc_admin")


if __name__ == "__main__":
    unittest.main()
