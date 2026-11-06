"""Tests for mp_relay.py, the two-device game relay. Runs only the relay on a spare port,
never the AppVerse server itself (whose start-up touches saved data).
    python test_mp_relay.py
"""
import http.server
import json
import socketserver
import threading
import time
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, unquote

import mp_relay


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        q = {k: v[0] for k, v in parse_qs(self.path.partition("?")[2]).items()}
        if not mp_relay.handle(self, "GET", path, q, {}):
            self.send_error(404)

    def do_POST(self):
        path = unquote(self.path.split("?")[0])
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if not mp_relay.handle(self, "POST", path, {}, body):
            self.send_error(404)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True


class Relay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server(("127.0.0.1", 0), H)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        mp_relay._rooms.clear()

    def call(self, method, name, body=None):
        req = urllib.request.Request(self.base + "/api/mp/" + name, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def read_stream(self, query, want, secs=3):
        """Open an SSE stream and collect `want` data messages (or give up after secs)."""
        got = []
        with urllib.request.urlopen(self.base + "/api/mp/stream?" + query, timeout=secs + 2) as r:
            self.assertEqual(r.headers["Content-Type"], "text/event-stream")
            end = time.time() + secs
            while len(got) < want and time.time() < end:
                line = r.readline().decode()
                if line.startswith("data: "):
                    got.append(json.loads(line[6:]))
        return got

    def test_open_list_join_and_messages_both_ways(self):
        s, host = self.call("POST", "open", {"name": "Level 3 Cadet", "rank": "cadet"})
        self.assertEqual(s, 200)
        room, token = host["room"], host["token"]
        self.assertRegex(room, r"^\d{4}$")
        s, lst = self.call("GET", "rooms")
        self.assertEqual(lst["rooms"], [{"room": room, "name": "Level 3 Cadet", "rank": "cadet", "guests": 0, "full": False}])
        s, g = self.call("POST", "join", {"room": room})
        self.assertEqual(s, 200)
        gid = g["guest"]
        # guest -> host
        self.assertEqual(self.call("POST", "send", {"room": room, "from": gid, "to": "host", "msg": {"t": "in", "mx": 0.5, "my": -1}})[0], 200)
        got = self.read_stream("room=%s&as=host&token=%s" % (room, token), 2)
        self.assertEqual(got, [{"t": "joined", "guest": gid}, {"t": "from", "guest": gid, "msg": {"t": "in", "mx": 0.5, "my": -1}}])
        # host -> guests, delivered while the guest's stream is already open
        out = []
        th = threading.Thread(target=lambda: out.extend(self.read_stream("room=%s&as=%s" % (room, gid), 1)))
        th.start()
        time.sleep(0.3)
        self.assertEqual(self.call("POST", "send", {"room": room, "from": "host", "token": token, "to": "guests", "msg": {"t": "st", "sh": 3}})[0], 200)
        th.join(5)
        self.assertEqual(out, [{"t": "st", "sh": 3}])
        self.assertEqual(self.call("GET", "rooms")[1]["rooms"][0]["guests"], 1)

    def test_only_the_host_can_speak_as_host(self):
        room = self.call("POST", "open", {})[1]["room"]
        self.assertEqual(self.call("POST", "send", {"room": room, "from": "host", "token": "nope", "to": "guests", "msg": 1})[0], 403)
        self.assertEqual(self.call("POST", "send", {"room": room, "from": "gstranger", "to": "host", "msg": 1})[0], 403)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/api/mp/stream?room=%s&as=host&token=nope" % room, timeout=3)

    def test_unknown_room_and_big_messages(self):
        self.assertEqual(self.call("POST", "join", {"room": "9999"})[0], 404)
        h = self.call("POST", "open", {})[1]
        self.assertEqual(self.call("POST", "send", {"room": h["room"], "from": "host", "token": h["token"], "to": "guests", "msg": "x" * 5000})[0], 413)

    def test_room_full_after_max_guests(self):
        room = self.call("POST", "open", {})[1]["room"]
        for _ in range(mp_relay.MAX_GUESTS):
            self.assertEqual(self.call("POST", "join", {"room": room})[0], 200)
        self.assertEqual(self.call("POST", "join", {"room": room})[0], 409)
        self.assertTrue(self.call("GET", "rooms")[1]["rooms"][0]["full"])

    def test_closing_tells_the_guest(self):
        h = self.call("POST", "open", {})[1]
        gid = self.call("POST", "join", {"room": h["room"]})[1]["guest"]
        self.call("POST", "close", {"room": h["room"], "token": h["token"]})
        self.assertEqual(self.read_stream("room=%s&as=%s" % (h["room"], gid), 1), [{"t": "ended"}])

    def test_a_closed_game_leaves_the_list_at_once_even_with_the_host_stream_open(self):
        # found by test24: the host's still-open stream kept refreshing a closed room
        h = self.call("POST", "open", {})[1]
        th = threading.Thread(target=lambda: self.read_stream("room=%s&as=host&token=%s" % (h["room"], h["token"]), 99, secs=2))
        th.start()
        time.sleep(0.3)
        self.call("POST", "close", {"room": h["room"], "token": h["token"]})
        self.assertEqual(self.call("GET", "rooms")[1]["rooms"], [])
        self.assertEqual(self.call("POST", "join", {"room": h["room"]})[0], 404)
        self.assertEqual(self.call("POST", "send", {"room": h["room"], "from": "host", "token": h["token"], "to": "guests", "msg": 1})[0], 404)
        th.join(5)

    def test_bye_gives_the_seat_back(self):
        h = self.call("POST", "open", {})[1]
        gid = self.call("POST", "join", {"room": h["room"]})[1]["guest"]
        self.assertEqual(self.call("GET", "rooms")[1]["rooms"][0]["guests"], 1)
        self.call("POST", "send", {"room": h["room"], "from": gid, "to": "host", "msg": {"t": "bye"}})
        self.assertEqual(self.call("GET", "rooms")[1]["rooms"][0]["guests"], 0)
        self.assertEqual(self.call("POST", "send", {"room": h["room"], "from": gid, "to": "host", "msg": {"t": "in"}})[0], 403)

    def test_a_silent_host_room_expires(self):
        old = mp_relay.ROOM_IDLE
        mp_relay.ROOM_IDLE = 0.2
        try:
            self.call("POST", "open", {})
            time.sleep(0.3)
            self.assertEqual(self.call("GET", "rooms")[1]["rooms"], [])
        finally:
            mp_relay.ROOM_IDLE = old

    def test_a_stream_ends_by_itself(self):
        old = mp_relay.STREAM_SECS
        mp_relay.STREAM_SECS = 0.5
        try:
            h = self.call("POST", "open", {})[1]
            t0 = time.time()
            with urllib.request.urlopen(self.base + "/api/mp/stream?room=%s&as=host&token=%s" % (h["room"], h["token"]), timeout=5) as r:
                r.read()
            self.assertLess(time.time() - t0, 3)
        finally:
            mp_relay.STREAM_SECS = old

    def test_too_many_rooms(self):
        for _ in range(mp_relay.MAX_ROOMS):
            self.assertEqual(self.call("POST", "open", {})[0], 200)
        self.assertEqual(self.call("POST", "open", {})[0], 429)


class ThroughAppVerse(unittest.TestCase):
    """The same routes through AppVerse's own request handler (serve_apps.AppHandler).
    Only the handler class is used: serve_apps' start-up (which touches saved data) never runs.
    Added 6 Nov after the relay passed the tests above but crashed inside AppVerse's do_GET."""

    @classmethod
    def setUpClass(cls):
        import serve_apps
        cls.srv = Server(("127.0.0.1", 0), serve_apps.AppHandler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        mp_relay._rooms.clear()

    call = Relay.call
    read_stream = Relay.read_stream

    def test_open_list_join_send_stream_close(self):
        self.assertEqual(self.call("GET", "rooms"), (200, {"rooms": []}))
        s, h = self.call("POST", "open", {"name": "Level 1 Story"})
        self.assertEqual(s, 200)
        s, g = self.call("POST", "join", {"room": h["room"]})
        self.assertEqual(s, 200)
        self.assertEqual(self.call("POST", "send", {"room": h["room"], "from": g["guest"], "to": "host", "msg": {"t": "in", "mx": 1, "my": 0}})[0], 200)
        got = self.read_stream("room=%s&as=host&token=%s" % (h["room"], h["token"]), 2)
        self.assertEqual([m["t"] for m in got], ["joined", "from"])
        self.assertEqual(self.call("POST", "close", {"room": h["room"], "token": h["token"]})[0], 200)
        self.assertEqual(self.call("GET", "rooms"), (200, {"rooms": []}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
