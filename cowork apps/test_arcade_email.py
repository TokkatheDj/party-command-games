"""On the Surface (no SHIP IT list) the nightly check emails Lance once a day about games ready for the
Arcade; on the desktop (SHIP IT list present) it still queues the step and sends nothing (22 Nov 2026).
No real email is sent: send() is captured. Run: python -m unittest test_arcade_email
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import new_app_check as N

READY = {"ok": True, "a11y": [], "waiting": True, "public": True}
KNOWN = {
    "kids_apps/2026-11-22-pepper-fire-pup-station.html": dict(READY, title="Pepper's Fire Pup Station"),
    "party_apps/2026-11-22-trivia-clue-ladder-duel.html": dict(READY, title="Clue Ladder Duel"),
    "kids_apps/2026-11-22-broken.html": dict(READY, ok=False, title="Broken One"),
    "vr_puzzle_apps/2026-11-22-vr-room.html": dict(READY, title="VR Room"),        # no Arcade section
}


class ArcadeEmail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = os.path.join(self.tmp, "arcade-email-sent.txt")
        self.sent = []
        self.p = mock.patch.object(N, "log", lambda m: None); self.p.start()

    def tearDown(self):
        self.p.stop()

    def mail(self, known=KNOWN, today="2026-11-22", index=None):
        if index is None:
            index = os.path.join(self.tmp, "index.html")
            open(index, "w", encoding="utf-8").write("const SECTIONS = [];")      # empty catalog
        return N.email_arcade_ready(known, state=self.state, send=self.sent.append, today=today, index=index)

    def test_games_already_on_the_arcade_are_left_out(self):
        # 22 Nov: a run off a day-old list emailed games published that morning
        index = os.path.join(self.tmp, "listed.html")
        open(index, "w", encoding="utf-8").write(
            "{ id: 'kids-pepper', src: 'kids_apps/2026-11-22-pepper-fire-pup-station.html' }")
        self.assertEqual(self.mail(index=index), "sent")
        body = self.sent[0].get_content()
        self.assertNotIn("Pepper's Fire Pup Station", body)
        self.assertIn("Clue Ladder Duel", body)
        self.assertIn("1 new game ready", self.sent[0]["Subject"])

    def test_ready_games_get_one_email(self):
        self.assertEqual(self.mail(), "sent")
        self.assertEqual(len(self.sent), 1)
        m = self.sent[0]; body = m.get_content()
        self.assertIn("2 new games ready", m["Subject"])
        self.assertIn("Pepper's Fire Pup Station", body)
        self.assertIn("Clue Ladder Duel", body)
        self.assertNotIn("Broken One", body)                  # failed the nightly check
        self.assertIn("VR Room", body)                        # mentioned only as "no Arcade section"
        self.assertIn("add_to_arcade.py --waiting", body)

    def test_second_run_same_day_is_silent_next_day_sends(self):
        self.assertEqual(self.mail(), "sent")
        self.assertEqual(self.mail(), "already")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.mail(today="2026-11-23"), "sent")
        self.assertEqual(len(self.sent), 2)

    def test_nothing_ready_sends_nothing(self):
        only_bad = {k: v for k, v in KNOWN.items() if not v["ok"] or k.startswith("vr_")}
        self.assertEqual(self.mail(only_bad), "none")
        self.assertEqual(self.sent, [])
        self.assertFalse(os.path.exists(self.state))

    def test_no_ship_list_means_email(self):
        with mock.patch.object(N, "SHIP_QUEUE", os.path.join(self.tmp, "missing.txt")), \
             mock.patch.object(N, "email_arcade_ready") as em:
            N.queue_arcade_step(KNOWN)
        em.assert_called_once()

    def test_desktop_with_ship_list_queues_step_and_sends_no_email(self):
        qfile = os.path.join(self.tmp, "your-turn.json")
        json.dump({"steps": []}, open(qfile, "w", encoding="utf-8"))
        ptr = os.path.join(self.tmp, "ship-queue.txt")
        open(ptr, "w", encoding="utf-8").write(qfile)
        with mock.patch.object(N, "SHIP_QUEUE", ptr), \
             mock.patch.object(N, "email_arcade_ready", side_effect=AssertionError("emailed on the desktop")):
            N.queue_arcade_step(KNOWN)
        steps = json.load(open(qfile, encoding="utf-8"))["steps"]
        self.assertEqual(len(steps), 1)
        self.assertIn("Pepper's Fire Pup Station", steps[0]["title"])
        self.assertNotIn("Broken One", steps[0]["title"])


if __name__ == "__main__":
    unittest.main()
