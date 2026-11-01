"""AppVerse's list header must count what the list shows (1 Nov 2026).
The number beside a list's name ("Kid 35") counted every app on the list that wasn't
hidden - including one whose file is gone, which gets no card. A deleted or renamed game
would have made the header say one more than the boys could see. Run:
python -m unittest test_playlist_count"""
import re
import unittest
from unittest import mock

import serve_apps


def card(app, *a, **k):
    return '<div class="app-item" data-path="%s"></div>' % app["path"]


class PlaylistCount(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(serve_apps, "_make_card", card); p.start(); self.addCleanup(p.stop)

    def render(self, apps, have, removed=()):
        html = serve_apps.build_playlist_html(
            "abc", {"name": "Kid", "emoji": "x", "apps": apps},
            {a: {"path": a} for a in have}, {"removed": list(removed)})
        return int(re.search(r'class="count">(\d+)<', html).group(1)), html.count('class="app-item"')

    def test_header_matches_the_cards(self):
        self.assertEqual(self.render(["a.html", "b.html"], ["a.html", "b.html"]), (2, 2))

    def test_a_hidden_app_is_in_neither(self):
        self.assertEqual(self.render(["a.html", "b.html"], ["a.html", "b.html"], removed=["b.html"]), (1, 1))

    def test_an_app_whose_file_is_gone_is_not_counted(self):
        self.assertEqual(self.render(["a.html", "gone.html"], ["a.html"]), (1, 1))

    def test_an_empty_list_says_zero(self):
        count, cards = self.render(["gone.html"], [])
        self.assertEqual((count, cards), (0, 0))


if __name__ == "__main__":
    unittest.main()
