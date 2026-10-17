"""The nightly "put these on the Arcade" SHIP IT step must only name apps it can place.

16 Oct 2026: an Action Games app passed the nightly check, so the step ran
`add_to_arcade.py --waiting`, which stopped on "which section?" before adding
anything - and so did the step's own guard. Run: python -m unittest test_arcade_sections
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import add_to_arcade
import new_app_check

GOOD = {"ok": True, "a11y": [], "waiting": True, "public": True}
APPS = {
    "kids_apps/a-kids-game.html": dict(GOOD, title="Kids Game"),
    "party_apps/a-party-game.html": dict(GOOD, title="Party Game"),
    "Action Games/a-reflex-game.html": dict(GOOD, title="Reflex Game"),
    "vr_puzzle_apps/a-vr-room.html": dict(GOOD, title="VR Room"),           # no Arcade section
    "kids_apps/low-contrast.html": dict(GOOD, title="Low Contrast", a11y=["color-contrast x3"]),
}


class Sections(unittest.TestCase):
    def test_action_games_is_placed(self):
        self.assertEqual(add_to_arcade.section_for("Action Games/x.html"), "kids")
        self.assertEqual(add_to_arcade.section_for("party_apps/x.html"), "party")
        self.assertIsNone(add_to_arcade.section_for("vr_puzzle_apps/x.html"))

    def test_waiting_splits_placeable_from_unplaced(self):
        placeable, unplaced = add_to_arcade.waiting_ready(APPS)
        self.assertEqual(placeable, ["Action Games/a-reflex-game.html", "kids_apps/a-kids-game.html",
                                     "party_apps/a-party-game.html"])
        self.assertEqual(unplaced, ["vr_puzzle_apps/a-vr-room.html"])     # named, not added


class NightlyStep(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.queue = os.path.join(d, "your-turn.json")
        json.dump({"steps": []}, open(self.queue, "w", encoding="utf-8"))
        pointer = os.path.join(d, "ship-queue.txt")
        open(pointer, "w", encoding="utf-8").write(self.queue)
        self.logged = []
        for name, value in (("SHIP_QUEUE", pointer), ("log", self.logged.append)):
            p = mock.patch.object(new_app_check, name, value); p.start(); self.addCleanup(p.stop)

    def step(self):
        steps = json.load(open(self.queue, encoding="utf-8"))["steps"]
        return steps[0] if steps else None

    def test_step_names_only_apps_it_can_place(self):
        new_app_check.queue_arcade_step(APPS)
        s = self.step()
        self.assertIn("Reflex Game", s["title"])
        self.assertNotIn("VR Room", s["title"])
        self.assertNotIn("Low Contrast", s["title"])
        self.assertIn("VR Room", s["why"])                               # but it says so
        self.assertEqual(len(s["verify"]), 3)
        self.assertTrue(any("VR Room" in line for line in self.logged))

    def test_only_unplaced_apps_means_no_step(self):
        new_app_check.queue_arcade_step({"vr_puzzle_apps/a-vr-room.html": APPS["vr_puzzle_apps/a-vr-room.html"]})
        self.assertIsNone(self.step())
        self.assertTrue(any("VR Room" in line for line in self.logged))


if __name__ == "__main__":
    unittest.main()
