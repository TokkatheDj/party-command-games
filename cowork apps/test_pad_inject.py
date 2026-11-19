"""Tests for game controllers in the AppVerse (pad_inject.py + the /pad.js route), 18 Nov 2026.

    python -m unittest test_pad_inject

The handler test runs serve_apps.AppHandler on a spare port. It never calls serve_apps.main(),
so nothing saved is touched and nothing is written to the access log.
"""
import http.server
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import pad_inject

HERE = Path(__file__).parent
TAG = pad_inject.TAG


class InjectTest(unittest.TestCase):
    def test_goes_before_the_last_body(self):
        out = pad_inject.inject(b"<html><body><p>hi</p></body></html>")
        self.assertEqual(out, b"<html><body><p>hi</p>" + TAG + b"</body></html>")

    def test_uppercase_body(self):
        self.assertIn(TAG + b"</BODY>", pad_inject.inject(b"<HTML><BODY>x</BODY></HTML>"))

    def test_page_with_pad_js_is_left_alone(self):
        page = b'<html><body><script src="pad.js" data-mode="menu"></script></body></html>'
        self.assertEqual(pad_inject.inject(page), page)

    def test_no_body_tag_appends(self):
        self.assertEqual(pad_inject.inject(b"<p>x</p>"), b"<p>x</p>" + TAG)

    def test_body_inside_a_script_string_is_not_used(self):
        # a loader that builds a page: its "</body>" is text in a script with no real </body> after
        page = b"<html><body><script>const at = html.lastIndexOf('</body>');"
        out = pad_inject.inject(page)
        self.assertEqual(out, page + TAG)
        self.assertNotIn(TAG + b"');", out)

    def test_real_body_after_a_script_mentioning_body(self):
        page = b"<body><script>x('</body>')</script><p>end</p></body>"
        self.assertEqual(pad_inject.inject(page), b"<body><script>x('</body>')</script><p>end</p>" + TAG + b"</body>")


class HandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import serve_apps

        class H(serve_apps.AppHandler):
            def log_message(self, *a):
                pass

        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, "", b""

    def test_pad_js_is_served(self):
        status, ctype, body = self.get("/pad.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertEqual(body, (HERE / "pad.js").read_bytes())

    def test_an_app_gets_the_tag_once(self):
        rel = "kids_apps/2026-09-21-big-fish-little-fish.html"
        status, ctype, body = self.get("/" + rel.replace(" ", "%20"))
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertEqual(body.count(TAG), 1)
        self.assertIn(TAG + b"</body>", body)
        self.assertEqual(body.replace(TAG, b""), (HERE / rel).read_bytes())   # nothing else changed

    def test_games_arcade_page_is_left_alone(self):
        status, _, body = self.get("/all-games-hub.html")
        self.assertEqual(status, 200)
        self.assertNotIn(TAG, body)
        self.assertEqual(body, (HERE / "all-games-hub.html").read_bytes())

    def test_private_files_stay_private(self):
        for p in ("/serve_apps.py", "/pad_inject.py", "/node_modules/playwright/index.js", "/.app_data.json", "/other.js"):
            self.assertEqual(self.get(p)[0], 404, p)

    def test_missing_app_is_404(self):
        self.assertEqual(self.get("/kids_apps/no-such-game.html")[0], 404)


if __name__ == "__main__":
    unittest.main()
