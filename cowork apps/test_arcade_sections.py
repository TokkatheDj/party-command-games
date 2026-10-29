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
        self.assertEqual(add_to_arcade.section_for("Action Games/x.html"), "action")
        self.assertEqual(add_to_arcade.section_for("party_apps/x.html"), "party")
        self.assertIsNone(add_to_arcade.section_for("vr_puzzle_apps/x.html"))

    def test_learning_kids_apps_go_to_learn(self):
        f = add_to_arcade.section_for
        self.assertEqual(f("kids_apps/2026-10-27-amigos-candy-math.html"), "learn")
        self.assertEqual(f("kids_apps/2026-10-20-rhyme-time-train.html"), "learn")
        self.assertEqual(f("kids_apps/2026-10-16-otto-sink-or-float-lab.html"), "learn")
        self.assertEqual(f("kids_apps/2026-10-27-benny-fix-it-garage.html"), "kids")
        self.assertEqual(f("party_apps/2026-10-28-trivia-vowel-play.html"), "party")   # only kids apps move

    def test_waiting_splits_placeable_from_unplaced(self):
        placeable, unplaced = add_to_arcade.waiting_ready(APPS)
        self.assertEqual(placeable, ["Action Games/a-reflex-game.html", "kids_apps/a-kids-game.html",
                                     "party_apps/a-party-game.html"])
        self.assertEqual(unplaced, ["vr_puzzle_apps/a-vr-room.html"])     # named, not added


class FamilyNames(unittest.TestCase):
    # 27 Oct 2026: a credit put a child's name on a public page. Made-up names here - the real
    # list lives outside this public repo.
    def setUp(self):
        self.names = os.path.join(tempfile.mkdtemp(), "names.txt")
        open(self.names, "w", encoding="utf-8").write("# a comment\nZebulon\n\nQuintessa\n")

    def test_finds_whole_names_in_any_case(self):
        self.assertEqual(add_to_arcade.private_names_in("Game idea by ZEBULON M.", self.names), ["Zebulon"])
        self.assertEqual(add_to_arcade.private_names_in("Zebulonia is a place", self.names), [])   # whole words only
        self.assertEqual(add_to_arcade.private_names_in("a comment", self.names), [])              # comments aren't names

    def test_no_list_says_so(self):
        self.assertIsNone(add_to_arcade.private_names_in("anything", self.names + ".missing"))


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

    def test_waits_for_a_locked_list(self):
        # 28 Oct 2026: Windows refuses os.replace on a file another program has open
        real, calls = os.replace, []
        def flaky(src, dst):
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError("[WinError 5] Access is denied")
            real(src, dst)
        with mock.patch.object(new_app_check.os, "replace", flaky), mock.patch.object(new_app_check.time, "sleep"):
            new_app_check.queue_arcade_step(APPS)
        self.assertEqual(len(calls), 3)
        self.assertIn("Reflex Game", self.step()["title"])

    def test_a_list_that_stays_locked_is_logged_not_fatal(self):
        def locked(src, dst):
            raise PermissionError("[WinError 5] Access is denied")
        with mock.patch.object(new_app_check.os, "replace", locked), mock.patch.object(new_app_check.time, "sleep"):
            new_app_check.queue_arcade_step(APPS)          # must not raise: the night's report goes on
        self.assertIsNone(self.step())                     # the list itself is unchanged
        self.assertTrue(any("stayed locked" in line for line in self.logged))
        self.assertTrue(os.path.exists(self.queue + ".tmp"))

    def test_leaves_a_hand_queued_arcade_step_alone(self):
        # 27 Oct 2026: a step queued by hand (id "arcade-add-amigos-candy-math") vanished at the
        # 21:30 run, because every waiting "arcade-add-" step was treated as last night's own.
        mine = {"id": "arcade-add-amigos-candy-math", "from": "claude", "status": "waiting"}
        old = {"id": "arcade-add-2026-10-26-2130", "from": "new_app_check.py", "status": "waiting"}
        json.dump({"steps": [mine, old]}, open(self.queue, "w", encoding="utf-8"))
        new_app_check.queue_arcade_step(APPS)
        ids = [s["id"] for s in json.load(open(self.queue, encoding="utf-8"))["steps"]]
        self.assertIn("arcade-add-amigos-candy-math", ids)               # kept
        self.assertNotIn("arcade-add-2026-10-26-2130", ids)              # its own old one replaced
        self.assertEqual(len(ids), 2)

    def test_only_unplaced_apps_means_no_step(self):
        new_app_check.queue_arcade_step({"vr_puzzle_apps/a-vr-room.html": APPS["vr_puzzle_apps/a-vr-room.html"]})
        self.assertIsNone(self.step())
        self.assertTrue(any("VR Room" in line for line in self.logged))


if __name__ == "__main__":
    unittest.main()
