"""The family-names guard in add_to_arcade.py must run on BOTH machines (22 Nov 2026).

It read only C:\\Users\\Lance\\Amigo\\private-names.txt, a desktop path, so on the Surface (user
tokka, where the factory runs) it printed "note: ... not checked" and published anyway.
These tests use made-up names and throwaway lists; no real family name is in this file.
Run: python -m unittest test_private_names
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import add_to_arcade as A

HERE = os.path.dirname(os.path.abspath(__file__))


class PrivateNames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.list = os.path.join(self.tmp, "private-names.txt")
        with open(self.list, "w", encoding="utf-8") as f:
            f.write("# family names\nZorblat\n\nQuixa Vell\n")

    def test_listed_name_found_whole_word_any_case(self):
        self.assertEqual(A.private_names_in("<h1>Made by ZORBLAT</h1>", self.list), ["Zorblat"])
        self.assertEqual(A.private_names_in("thanks quixa vell!", self.list), ["Quixa Vell"])

    def test_no_false_hit_inside_a_longer_word(self):
        self.assertEqual(A.private_names_in("the zorblatter machine", self.list), [])

    def test_no_list_anywhere_means_not_checked(self):
        with mock.patch.object(A, "PRIVATE_NAMES_PLACES", ["", os.path.join(self.tmp, "nope.txt")]):
            self.assertIsNone(A.private_names_file())
            self.assertIsNone(A.private_names_in("Zorblat"))

    def test_list_with_only_comments_counts_as_no_list(self):
        with open(self.list, "w", encoding="utf-8") as f:
            f.write("# one family name per line\n\n")
        self.assertIsNone(A.private_names_in("anything", self.list))

    def test_this_users_amigo_folder_is_found(self):
        # the Surface case: ~\\Amigo\\private-names.txt, with the desktop path absent
        home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(home, "Amigo"))
        mine = os.path.join(home, "Amigo", "private-names.txt")
        with open(mine, "w", encoding="utf-8") as f:
            f.write("Zorblat\n")
        places = ["", mine, os.path.join(self.tmp, "desktop-only.txt")]
        with mock.patch.object(A, "PRIVATE_NAMES_PLACES", places):
            self.assertEqual(A.private_names_file(), mine)
            self.assertEqual(A.private_names_in("hi Zorblat"), ["Zorblat"])

    def test_default_places_include_this_users_amigo_folder(self):
        want = os.path.join(os.path.expanduser("~"), "Amigo", "private-names.txt")
        self.assertIn(want, A.PRIVATE_NAMES_PLACES)

    def test_tool_refuses_a_real_app_with_a_listed_word(self):
        # end to end, --dry: a word that IS in a tracked app ("Magnet") stands in for a family name
        with open(self.list, "w", encoding="utf-8") as f:
            f.write("Magnet\n")
        env = dict(os.environ, AMIGO_PRIVATE_NAMES=self.list, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "add_to_arcade.py", "--dry", "kids_apps/2026-11-20-maggie-magnet-hunt.html"],
                           cwd=HERE, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("family name(s)", r.stdout + r.stderr)
        self.assertNotIn("Magnet\n", r.stdout + r.stderr)      # names are never echoed, only the count


if __name__ == "__main__":
    unittest.main()
