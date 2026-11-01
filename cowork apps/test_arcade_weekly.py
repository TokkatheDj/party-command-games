"""The weekly Arcade check (arcade_weekly.py): its phone fit step (28 Oct 2026) and worksheet steps (29 Oct).
Run: python -m unittest test_arcade_weekly"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import arcade_weekly as aw

FITS = {"results": [{"what": "Kids Game (kids-a)", "how": "Arcade tile", "ok": True, "problems": []},
                    {"what": "kids_apps/a.html", "how": "direct link", "ok": True, "problems": []}]}
CUT = {"results": [{"what": "Feed the Monster (kids-feed)", "how": "Arcade tile", "ok": False,
                    "problems": ['iPhone 14, after "Play": button "x" 83px below the screen']},
                   {"what": "kids_apps/a.html", "how": "direct link", "ok": True, "problems": []}]}

SUBJECTS_PASS = {"ok": True, "topics": 25, "problems": 250, "failures": [], "dialogs": [], "errors": []}


def ran(out, code=0):
    return SimpleNamespace(stdout=out if isinstance(out, str) else json.dumps(out), stderr="", returncode=code)


class PhoneFit(unittest.TestCase):
    def setUp(self):
        self.logged = []
        p = mock.patch.object(aw, "log", self.logged.append); p.start(); self.addCleanup(p.stop)

    def test_all_fit_reports_nothing(self):
        with mock.patch.object(aw.subprocess, "run", return_value=ran(FITS)):
            self.assertEqual(aw.phone_fit("root"), [])
        self.assertIn("all fit", self.logged[-1])

    def test_a_cut_off_game_is_named_with_how_it_was_opened(self):
        with mock.patch.object(aw.subprocess, "run", return_value=ran(CUT)):
            bad = aw.phone_fit("root")
        self.assertEqual([b["name"] for b in bad], ["Phone fit: Feed the Monster (kids-feed) (Arcade tile)"])
        self.assertIn("83px below", bad[0]["problems"][0])

    def test_a_check_that_crashes_says_so(self):
        with mock.patch.object(aw.subprocess, "run", return_value=ran("Error: boom", 1)):
            bad = aw.phone_fit("root")
        self.assertEqual(bad[0]["problems"], ["the check itself failed"])
        self.assertTrue(any("phone fit check failed" in line for line in self.logged))


class WorksheetChecks(unittest.TestCase):
    """The Subject Worksheets and worksheet accessibility steps (added 29 Oct 2026)."""
    def setUp(self):
        self.logged = []
        p = mock.patch.object(aw, "log", self.logged.append); p.start(); self.addCleanup(p.stop)

    def test_subjects_all_pass_reports_nothing(self):
        with mock.patch.object(aw.subprocess, "run", return_value=ran("checking...\n" + json.dumps(SUBJECTS_PASS))):
            self.assertEqual(aw.subjects_check(), [])
        self.assertIn("all pass", self.logged[-1])

    def test_subjects_failures_and_dialogs_are_named(self):
        res = dict(SUBJECTS_PASS, ok=False, failures=["History q3 marked wrong"], dialogs=["alert on Spanish"])
        with mock.patch.object(aw.subprocess, "run", return_value=ran(res)):
            bad = aw.subjects_check()
        self.assertEqual(bad[0]["problems"], ["History q3 marked wrong", "dialog: alert on Spanish"])

    def test_a11y_page_with_issues_is_named(self):
        pages = {"pages": [{"url": "https://x/a/b/worksheets.html", "ok": False, "views": 4,
                            "issues": ["color-contrast on .hint"], "errors": []}]}
        with mock.patch.object(aw.subprocess, "run", return_value=ran(pages)):
            bad = aw.worksheet_a11y()
        self.assertEqual(bad[0]["name"], "Worksheets accessibility: worksheets.html")

    def test_a11y_check_that_crashes_says_so(self):
        with mock.patch.object(aw.subprocess, "run", return_value=ran("Error: boom", 1)):
            self.assertEqual(aw.worksheet_a11y()[0]["problems"], ["the check itself failed"])


class WeeklyRun(unittest.TestCase):
    """A full run sends the phone fit problems to the status page with the broken tiles."""

    def test_full_run_reports_phone_fit_to_the_status_page(self):
        d = tempfile.mkdtemp()
        report_to = os.path.join(d, "report-to.txt")
        with open(report_to, "w", encoding="utf-8") as f:
            f.write("http://127.0.0.1:9/door/apps\n")
        tiles = {"tiles": [{"id": "kids-a", "name": "Kids Game", "ok": True, "problems": []}]}

        def run(args, **kw):
            script = os.path.basename(args[1])
            return ran({"arcade_play_check.js": tiles, "worksheet_blanks_check.js": {"pages": []},
                        "subject_worksheets_check.js": SUBJECTS_PASS, "worksheet_a11y_check.js": {"pages": []},
                        "phone_fit_check.js": CUT}[script])

        sent = []
        def urlopen(req, timeout=0):
            sent.append((req.full_url, json.loads(req.data)))
            return SimpleNamespace(read=lambda: b"")

        with mock.patch.object(aw.subprocess, "run", run), mock.patch.object(aw.urllib.request, "urlopen", urlopen), \
             mock.patch.object(aw, "OUT", os.path.join(d, "out.json")), mock.patch.object(aw, "REPORT_TO", report_to), \
             mock.patch.object(aw, "log", lambda m: None), mock.patch.object(aw.sys, "argv", ["arcade_weekly.py"]):
            self.assertEqual(aw.main(), 0)
        url, body = sent[0]
        self.assertTrue(url.endswith("/door/arcade"))
        self.assertEqual(body["tiles"], 1)
        self.assertEqual([b["name"] for b in body["broken"]], ["Phone fit: Feed the Monster (kids-feed) (Arcade tile)"])


if __name__ == "__main__":
    unittest.main()
