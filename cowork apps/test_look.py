"""The nightly check's look check (new_app_check.look / look_summary), 30 Oct 2026.
After the IDENTITY block every new app names a style card and a sound kit; this is what
notices when one style takes over again. Run: python -m unittest test_look"""
import os
import tempfile
import unittest
from unittest import mock

import new_app_check as nac


def app(style=None, sound=None, font="Fredoka"):
    tag = "[style: %s / sound: %s]" % (style, sound) if style else ""
    return ("<!-- CONCEPT: a game about things. %s -->\n<style>:root{--font:'%s', sans-serif}"
            "body{font-family:var(--font)}</style>" % (tag, font))


class Look(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = mock.patch.object(nac, "HERE", self.dir); p.start(); self.addCleanup(p.stop)

    def write(self, rel, text):
        os.makedirs(os.path.dirname(os.path.join(self.dir, rel)), exist_ok=True)
        open(os.path.join(self.dir, rel), "w", encoding="utf-8").write(text)

    def test_reads_the_tag_and_follows_a_font_variable(self):
        self.write("kids_apps/2026-10-30-a.html", app("Paper Cutout", "Marimba", "Fredoka"))
        self.assertEqual(nac.look("kids_apps/2026-10-30-a.html"),
                         {"style": "Paper Cutout", "sound": "Marimba", "font": "Fredoka"})

    def test_an_untagged_app_still_reports_its_font(self):
        self.write("kids_apps/2026-10-30-b.html", "<style>body{font-family:'Segoe UI',sans-serif}</style>")
        self.assertEqual(nac.look("kids_apps/2026-10-30-b.html"), {"style": None, "sound": None, "font": "Segoe UI"})


def known(*apps):
    return {"x/2026-10-%s-%d.html" % (day, i): dict(title="App %d" % i, style=st, sound=so, font=f)
            for i, (day, st, so, f) in enumerate(apps)}


class Summary(unittest.TestCase):
    def test_three_of_four_sharing_a_style_warns(self):
        s = nac.look_summary(known(("30", "Clay", "Marimba", "Nunito"), ("30", "Clay", "Chiptune", "Nunito"),
                                   ("31", "Clay", "Music Box", "Fredoka"), ("31", "Storybook", "Toy Piano", "Merriweather")))
        self.assertIn("Look: 3 of 4 new apps share the style Clay", s["warnings"])
        self.assertEqual(s["styles"], {"Clay": 3, "Storybook": 1})

    def test_a_varied_night_is_quiet(self):
        s = nac.look_summary(known(("30", "Clay", "Marimba", "Nunito"), ("30", "Chalkboard", "Chiptune", "Patrick Hand"),
                                   ("31", "Neon Arcade", "Music Box", "VT323"), ("31", "Storybook", "Toy Piano", "Merriweather")))
        self.assertEqual(s["warnings"], [])

    def test_two_of_two_is_too_few_to_call(self):
        s = nac.look_summary(known(("30", "Clay", "Marimba", "Nunito"), ("30", "Clay", "Marimba", "Nunito")))
        self.assertEqual(s["warnings"], [])

    def test_untagged_new_apps_are_named(self):
        s = nac.look_summary(known(("30", None, None, "Segoe UI"), ("30", "Clay", "Marimba", "Nunito")))
        self.assertEqual(s["untagged"], 1)
        self.assertTrue(any("no style tag: App 0" in w for w in s["warnings"]))

    def test_apps_from_before_the_block_are_left_out(self):
        s = nac.look_summary(known(("28", None, None, "Segoe UI"), ("29", None, None, "Segoe UI"), ("27", None, None, "Segoe UI")))
        self.assertEqual((s["apps"], s["warnings"]), (0, []))

    def test_a_shared_font_warns_even_with_varied_tags(self):
        s = nac.look_summary(known(("30", "Clay", "Marimba", "Segoe UI"), ("30", "Chalkboard", "Chiptune", "Segoe UI"),
                                   ("31", "Neon Arcade", "Music Box", "Segoe UI"), ("31", "Storybook", "Toy Piano", "Merriweather")))
        self.assertIn("Look: 3 of 4 new apps share the font Segoe UI", s["warnings"])


if __name__ == "__main__":
    unittest.main()
