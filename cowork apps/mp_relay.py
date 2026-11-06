"""A tiny relay so two devices on the home Wi-Fi can play one game together.

Used by Squad Leader: Frontier's "play on two devices": the host tablet runs the game,
a second device joins as P2 and sends its thumb; the host sends status back.

Everything is in memory and short-lived: no file is written, nothing is logged, and a room
disappears 30 seconds after its host stops talking. Messages travel as JSON:
  GET  /api/mp/rooms                      -> open rooms, for the guest's "join" buttons
  POST /api/mp/open   {name, rank}        -> {room, token}       (the host)
  POST /api/mp/join   {room}              -> {guest}             (a second device)
  POST /api/mp/send   {room, from, token?, to, msg}              ("host" -> "guests" or a guest id; guest -> "host")
  POST /api/mp/close  {room, token}
  GET  /api/mp/stream?room=..&as=host|<guest id>   Server-Sent Events, one "data:" line per message.
A stream ends by itself after STREAM_SECS so no server thread lives forever; the browser's
EventSource reconnects on its own (we ask it to wait RETRY_MS).
"""
import json
import secrets
import threading
import time
from collections import deque

ROOM_IDLE = 30          # seconds without the host before a room goes away
GUEST_IDLE = 20         # seconds without a guest before it is dropped
STREAM_SECS = 40        # one SSE connection's lifetime
PING_SECS = 10
RETRY_MS = 800
MAX_ROOMS = 8
MAX_GUESTS = 3          # the game uses one today; the room can hold more later
QUEUE_MAX = 64          # per listener; old messages drop first
MAX_MSG = 4096          # bytes of one message's JSON

_lock = threading.Condition()
_rooms = {}             # code -> room dict


def _now():
    return time.monotonic()


def _sweep():
    t = _now()
    for code in list(_rooms):
        r = _rooms[code]
        if t - r["host_seen"] > ROOM_IDLE or (r["closed"] and t - r["closed"] > 3):
            del _rooms[code]
            continue
        for gid in list(r["guests"]):
            if t - r["guests"][gid] > GUEST_IDLE:
                del r["guests"][gid]
                r["queues"].pop(gid, None)
                _push(r, "host", {"t": "left", "guest": gid})


def _push(room, who, msg):
    q = room["queues"].get(who)
    if q is not None:
        q.append(msg)
        _lock.notify_all()


def _new_code():
    for _ in range(50):
        code = "%04d" % secrets.randbelow(10000)
        if code not in _rooms:
            return code
    raise RuntimeError("no free room code")


def open_room(payload):
    with _lock:
        _sweep()
        if len(_rooms) >= MAX_ROOMS:
            return 429, {"error": "too many games open"}
        code = _new_code()
        token = secrets.token_hex(8)
        _rooms[code] = {
            "code": code, "token": token, "host_seen": _now(), "made": time.time(),
            "name": str(payload.get("name") or "Game")[:40], "rank": str(payload.get("rank") or "")[:12],
            "guests": {}, "queues": {"host": deque(maxlen=QUEUE_MAX)}, "closed": 0,
        }
        return 200, {"room": code, "token": token}


def list_rooms():
    with _lock:
        _sweep()
        return 200, {"rooms": [{"room": r["code"], "name": r["name"], "rank": r["rank"],
                                "guests": len(r["guests"]), "full": len(r["guests"]) >= MAX_GUESTS}
                               for r in _rooms.values() if not r["closed"]]}


def join(payload):
    with _lock:
        _sweep()
        r = _rooms.get(str(payload.get("room", "")))
        if not r or r["closed"]:
            return 404, {"error": "that game has ended"}
        if len(r["guests"]) >= MAX_GUESTS:
            return 409, {"error": "that game is full"}
        gid = "g" + secrets.token_hex(4)
        r["guests"][gid] = _now()
        r["queues"][gid] = deque(maxlen=QUEUE_MAX)
        _push(r, "host", {"t": "joined", "guest": gid})
        return 200, {"guest": gid}


def send(payload):
    raw = json.dumps(payload.get("msg"), separators=(",", ":"))
    if len(raw) > MAX_MSG:
        return 413, {"error": "message too big"}
    msg = json.loads(raw)
    with _lock:
        r = _rooms.get(str(payload.get("room", "")))
        if not r:
            return 404, {"error": "that game has ended"}
        frm, to = str(payload.get("from", "")), str(payload.get("to", ""))
        if r["closed"]:
            return 404, {"error": "that game has ended"}
        if frm == "host":
            if payload.get("token") != r["token"]:
                return 403, {"error": "not the host"}
            r["host_seen"] = _now()
            targets = list(r["guests"]) if to == "guests" else [to] if to in r["guests"] else []
            for gid in targets:
                _push(r, gid, msg)
        elif frm in r["guests"]:
            r["guests"][frm] = _now()
            if to != "host":
                return 400, {"error": "guests talk to the host"}
            _push(r, "host", {"t": "from", "guest": frm, "msg": msg})
            if isinstance(msg, dict) and msg.get("t") == "bye":
                del r["guests"][frm]
                r["queues"].pop(frm, None)
        else:
            return 403, {"error": "not in this game"}
        return 200, {"ok": True}


def close(payload):
    with _lock:
        r = _rooms.get(str(payload.get("room", "")))
        if r and payload.get("token") == r["token"]:
            for gid in r["guests"]:
                _push(r, gid, {"t": "ended"})
            # hidden at once; kept 3 s so the guests' streams can deliver "ended"
            r["closed"] = _now()
        return 200, {"ok": True}


def stream(handler, query):
    """Serve one SSE connection. `handler` is a BaseHTTPRequestHandler; query a dict."""
    code, who = str(query.get("room", "")), str(query.get("as", ""))
    with _lock:
        r = _rooms.get(code)
        ok = r is not None and (who in r["guests"] or (who == "host" and query.get("token") == r["token"]))
    if not ok:
        handler.send_response(404)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(b'{"error":"that game has ended"}')
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    handler.end_headers()
    end = _now() + STREAM_SECS
    last_write = _now()
    try:
        handler.wfile.write(("retry: %d\n\n" % RETRY_MS).encode())
        handler.wfile.flush()
        while _now() < end:
            with _lock:
                r = _rooms.get(code)
                if r is None or (who != "host" and who not in r["guests"]) or (r["closed"] and who == "host"):
                    out = [{"t": "ended"}]
                    end = 0
                else:
                    q = r["queues"].get(who)
                    if not q:
                        _lock.wait(timeout=min(PING_SECS, max(0.05, end - _now())))
                    out = []
                    while q:
                        out.append(q.popleft())
                    if who == "host":
                        r["host_seen"] = _now()
                    else:
                        r["guests"][who] = _now()
            if out:
                handler.wfile.write("".join("data: %s\n\n" % json.dumps(m, separators=(",", ":")) for m in out).encode())
                handler.wfile.flush()
                last_write = _now()
            elif _now() - last_write >= PING_SECS:
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
                last_write = _now()
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass  # the device went away; its room or seat will time out


def handle(handler, method, path, query, payload):
    """Route one /api/mp/ request. Returns True if it was ours."""
    if not path.startswith("/api/mp/"):
        return False
    name = path[len("/api/mp/"):]
    if method == "GET" and name == "stream":
        stream(handler, query)
        return True
    routes = {("GET", "rooms"): lambda: list_rooms(),
              ("POST", "open"): lambda: open_room(payload),
              ("POST", "join"): lambda: join(payload),
              ("POST", "send"): lambda: send(payload),
              ("POST", "close"): lambda: close(payload)}
    fn = routes.get((method, name))
    status, body = fn() if fn else (404, {"error": "unknown"})
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
    return True
