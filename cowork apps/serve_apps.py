#!/usr/bin/env python3
"""
Local app server for cowork apps.
Serves all HTML files with a mobile-friendly index page.
Access from any device on the same WiFi network.
"""
import http.server
import html
import json
import struct
import zlib
import re
import socket
import socketserver
import subprocess
import smtplib
import threading
import time
import uuid
import os
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import unquote

APPS_DIR = Path(__file__).parent
PORT = 8080
DATA_FILE = APPS_DIR / ".app_data.json"
CUSTOM_APPS_DIR = APPS_DIR / "custom_apps"
EMAIL_CONFIG_FILE = APPS_DIR / "email_config.json"
MAX_CONCURRENT_GENERATIONS = 2
GENERATION_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_GENERATIONS)
GENERATION_TIMEOUT_SEC = 360
# Guards every read-modify-write cycle against .app_data.json: do_POST holds this
# for its whole request (load -> mutate -> save), and update_app_request() holds it
# too, so a background generation thread's status write can never be silently
# clobbered by (or clobber) a concurrent HTTP request's stale data snapshot.
DATA_LOCK = threading.Lock()

CATEGORY_ICONS = {
    # Original 8 categories
    "Adult Puzzle Apps": "\U0001f9e9",
    "Art Apps": "\U0001f58c️",
    "Classroom Tools": "\U0001f3eb",
    "Data Visualization Apps": "\U0001f4c8",
    "Educational Apps": "\U0001f393",
    "Health Productivity Apps": "\U0001fa7a",
    "Kids Apps": "\U0001f9f8",
    "Music Apps": "\U0001f3b9",
    "Reviews": "⭐",
    # Expanded categories (added 2026-06-27)
    "Action Games": "\U0001f94a",
    "Card Games Apps": "\U0001f0cf",
    "Content Creation Apps": "✍️",
    "Custom Apps": "\U0001f6e0️",
    "Dj Music Apps": "\U0001f3a7",
    "Fashion Apps": "\U0001f457",
    "Music Game Apps": "\U0001f3b6",
    "Party Apps": "\U0001f389",
    "Shooting Games Apps": "\U0001f3af",
    "Sports Games Apps": "⚽",
    "Table Games Apps": "\U0001f3b2",
    "Therapy Apps": "\U0001f9d8",
}

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def clean_name(stem):
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    return name.replace("-", " ").replace("_", " ").title()

def discover_apps():
    apps = {}
    ignore = {"serve_apps.py", "test_apps.js", "Start-AppServer.ps1", "Run-Tests.ps1"}
    ignore_dirs = {"node_modules", "test_reports", ".playwright-mcp", ".claude", "Reviews"}
    for html_file in sorted(APPS_DIR.rglob("*.html")):
        parent_names = {p.name for p in html_file.parents}
        if parent_names & ignore_dirs or html_file.name in ignore:
            continue
        rel = html_file.relative_to(APPS_DIR)
        parts = rel.parts
        if len(parts) == 1:
            category = "Other"
        else:
            category = parts[0].replace("_", " ").title()
        name = clean_name(html_file.stem)
        path_str = str(rel).replace("\\", "/")
        mtime = html_file.stat().st_mtime
        apps.setdefault(category, []).append({
            "name": name,
            "path": path_str,
            "mtime": mtime,
        })
    for cat in apps:
        apps[cat].sort(key=lambda x: x["mtime"], reverse=True)
    return dict(sorted(apps.items()))


def md_to_html(text):
    """Convert a subset of Markdown to HTML for review files."""
    lines = text.split("\n")
    result = []
    i = 0
    in_list = False

    def inline(s):
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"_(.+?)_", r"<em>\1</em>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if stripped.startswith("### "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h3>{inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h2>{inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<h1>{inline(stripped[2:])}</h1>")
        elif stripped.strip() == "---":
            if in_list: result.append("</ul>"); in_list = False
            result.append("<hr>")
        elif stripped.startswith("|"):
            if in_list: result.append("</ul>"); in_list = False
            table_lines = []
            while i < len(lines) and lines[i].rstrip().startswith("|"):
                table_lines.append(lines[i].rstrip())
                i += 1
            i -= 1
            result.append('<div class="table-wrap"><table class="review-table">')
            header_done = False
            for row in table_lines:
                cells = [c.strip() for c in row.strip("|").split("|")]
                if all(re.match(r"^[-: ]+$", c) for c in cells if c):
                    header_done = True
                    continue
                tag = "th" if not header_done else "td"
                row_html = "<tr>"
                for cell in cells:
                    cls = ""
                    if tag == "td":
                        if "✅" in cell: cls = ' class="rating-pass"'
                        elif "⚠️" in cell: cls = ' class="rating-warn"'
                        elif "❌" in cell or "BROKEN" in cell: cls = ' class="rating-fail"'
                    row_html += f"<{tag}{cls}>{inline(cell)}</{tag}>"
                row_html += "</tr>"
                result.append(row_html)
                header_done = True
            result.append("</table></div>")
        elif stripped.startswith("- "):
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append(f"<li>{inline(stripped[2:])}</li>")
        elif not stripped.strip():
            if in_list: result.append("</ul>"); in_list = False
            result.append("")
        else:
            if in_list: result.append("</ul>"); in_list = False
            result.append(f"<p>{inline(stripped)}</p>")
        i += 1

    if in_list:
        result.append("</ul>")
    return "\n".join(result)


def discover_reviews():
    reviews_dir = APPS_DIR / "Reviews"
    reviews = []
    if not reviews_dir.exists():
        return reviews
    for md_file in sorted(reviews_dir.glob("*.md"), reverse=True):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        reviews.append({"filename": md_file.name, "html": md_to_html(text)})
    return reviews


def load_data():
    defaults = {"favorites": [], "ratings": {}, "removed": [], "opened": [], "notes": [], "playlists": {}, "app_requests": [], "builders": {}}
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            for k, v in defaults.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return defaults


def save_data(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def now_iso():
    """UTC timestamp in the same format used for every created/started/finished
    field across notes, playlists, and app_requests."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def slugify_idea(text):
    slug = re.sub(r'[^a-z0-9]+', '-', (text or "").lower()).strip('-')
    return slug[:40].strip('-') or "my-app"


def slug_from_filename(target_filename):
    """Derive the localStorage-namespace slug from the actual computed target
    filename (stripping the YYYY-MM-DD- prefix and .html suffix) instead of
    recomputing it independently from criteria -- that way the namespace
    always matches the real filename, including any -2/-3 disambiguator
    compute_target_filename() appended on a same-day slug collision."""
    stem = target_filename[:-5] if target_filename.endswith(".html") else target_filename
    return re.sub(r'^\d{4}-\d{2}-\d{2}-', '', stem)


def compute_target_filename(criteria, data):
    slug = slugify_idea(criteria.get("idea") or criteria.get("theme") or criteria.get("app_type"))
    today = time.strftime("%Y-%m-%d")
    existing = {p.name for p in CUSTOM_APPS_DIR.glob("*.html")} if CUSTOM_APPS_DIR.exists() else set()
    existing |= {req.get("target_filename") for req in data.get("app_requests", []) if req.get("target_filename")}
    base = f"{today}-{slug}"
    candidate = f"{base}.html"
    n = 2
    while candidate in existing:
        candidate = f"{base}-{n}.html"
        n += 1
    return candidate


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def strip_private_fields(request_record):
    """Drop fields from an app_request record that shouldn't leave the server:
    log_tail (debug-only subprocess output) and requester_email (only needed
    server-side to send the build-finished notification, not for card display)."""
    return {k: v for k, v in request_record.items() if k not in ("log_tail", "requester_email")}


def remember_builder(data, name, email):
    """Track name -> most-recently-provided email so the name dropdown can
    offer returning guests their name (and re-use their email for build
    notifications) without asking them to retype it every time."""
    builders = data.setdefault("builders", {})
    if email:
        builders[name] = email
    elif name not in builders:
        builders[name] = ""


def list_builders(data):
    return sorted(
        ({"name": name, "email": email} for name, email in data.get("builders", {}).items() if name),
        key=lambda b: b["name"].lower(),
    )


def load_email_config():
    """Reads email_config.json (gitignored, not part of .app_data.json since it
    holds an SMTP credential, not app state). Returns None -- and callers must
    silently skip sending -- until the file exists with all three fields filled in."""
    if not EMAIL_CONFIG_FILE.exists():
        return None
    try:
        cfg = json.loads(EMAIL_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not (cfg.get("smtp_host") and cfg.get("smtp_user") and cfg.get("smtp_app_password")):
        return None
    return cfg


def get_base_url():
    return os.environ.get("PUBLIC_URL") or f"http://{get_local_ip()}:{PORT}"


def send_build_notification(requester_name, requester_email, target_path):
    """Best-effort 'your app is ready' email. Must never raise into the caller --
    a missing/unconfigured email_config.json or an SMTP hiccup should not affect
    the build itself, so every failure path here just logs and returns."""
    if not requester_email:
        return
    cfg = load_email_config()
    if not cfg:
        return
    link = f"{get_base_url()}/{target_path}"
    msg = EmailMessage()
    msg["Subject"] = f"Your app is ready, {requester_name}!"
    msg["From"] = f'{cfg.get("from_name", "Cowork Apps")} <{cfg["smtp_user"]}>'
    msg["To"] = requester_email
    msg.set_content(
        f"Hi {requester_name},\n\n"
        f"Your app is built and ready to play:\n{link}\n\n"
        "Have fun!\n"
    )
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 587), timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["smtp_user"], cfg["smtp_app_password"])
            smtp.send_message(msg)
        print(f"[builder] notification email sent to {requester_email}", flush=True)
    except Exception as e:
        print(f"[builder] notification email failed: {e}", flush=True)


def update_app_request(request_id, **fields):
    """Re-read data fresh before writing, mirroring daily_check.py's update_note()
    idiom, so a slow generation doesn't clobber concurrent HTTP-server writes.
    Holds DATA_LOCK for the whole read-modify-write cycle -- see DATA_LOCK's
    definition for why a re-read alone isn't a strong enough guarantee."""
    with DATA_LOCK:
        data = load_data()
        for req in data.get("app_requests", []):
            if req.get("id") == request_id:
                req.update(fields)
                break
        save_data(data)


def build_prompt(criteria, mode, target_filename, requester_name):
    target_full = CUSTOM_APPS_DIR / target_filename
    mechanics_line = f"Requested mechanics: {', '.join(criteria.get('mechanics', []))}\n" if criteria.get("mechanics") else ""
    age_line = f"Target age range: {criteria.get('age_range')}\n" if criteria.get("age_range") else ""
    tech_line = f"Specific technical requests: {criteria.get('tech_requests')}\n" if criteria.get("tech_requests") else ""
    inspired_line = f"Should feel similar in spirit to: {criteria.get('inspired_by')}\n" if criteria.get("inspired_by") else ""
    slug = slug_from_filename(target_filename)

    return (
        "You are generating exactly ONE new self-contained HTML app for a local family app "
        "library called 'Cowork Apps', built by a kid using a 'Build Your Own App' wizard.\n\n"
        f"App type: {criteria.get('app_type')}\n"
        f"Theme: {criteria.get('theme')}\n"
        f"Difficulty: {criteria.get('difficulty')}\n"
        f"Visual color vibe: {criteria.get('color_vibe')}\n"
        f"One-line idea: {criteria.get('idea')}\n"
        f"{mechanics_line}{age_line}{tech_line}{inspired_line}"
        f"Requested by: {requester_name}\n\n"
        "MANDATORY OUTPUT LOCATION -- this is the single most important rule:\n"
        f"Create exactly one file at this exact absolute path: {target_full}\n"
        "Do NOT create, edit, move, or delete any other file. Do not touch serve_apps.py, "
        "Start-AppServer.ps1, .app_data.json, package.json, or anything outside the "
        "custom_apps folder. Do not create README files, asset files, or a second HTML file.\n\n"
        "MANDATORY HTML APP CONVENTIONS (from this project's CLAUDE.md -- follow exactly):\n"
        "- First line of the file must be: <!-- CONCEPT: one-sentence description -->\n"
        "- Must include this exact viewport meta tag verbatim: "
        '<meta name="viewport" content="width=device-width, initial-scale=1.0, '
        'maximum-scale=1.0, user-scalable=no">\n'
        "- Single self-contained HTML file: all CSS and JS inline, no external dependencies, "
        "no CDN links, no external fonts or images.\n"
        "- Always include this universal reset: "
        "* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }\n"
        "- Always include this on html, body: margin: 0; padding: 0; "
        "touch-action: manipulation; user-select: none; -webkit-user-select: none;\n"
        "- Use CSS custom properties (:root { --var: value; }) for theme colors.\n"
        "- Vanilla JS only, in one <script> tag at the end of <body>.\n"
        "- Mobile-first: works at 375px wide with no horizontal scroll, all tap targets >= 44px, "
        "no hover-only interactions.\n"
        "- If you persist any state, use localStorage with keys namespaced as "
        f"'cowork-{slug}-{{key}}'.\n"
        "- Give the app a clear on-screen title and, if it's a game or puzzle, a way to restart/reset.\n"
        "- Match the visual vibe requested above (bright/playful, dark/muted, neon, pastel, etc.) "
        "using colors, not just a label in a comment.\n\n"
        "Build the complete, working app in one pass -- do not ask clarifying questions, do not "
        "produce placeholder or skeleton code."
    )


def build_fix_prompt(original, issue_description, target_filename):
    target_full = CUSTOM_APPS_DIR / target_filename
    criteria = (original or {}).get("criteria", {})
    return (
        "You are fixing a bug in an existing self-contained HTML app in a local family app "
        "library called 'Cowork Apps'. The app was originally generated by an earlier AI pass "
        "from a kid's 'Build Your Own App' wizard, and a family member just played it and hit "
        "a real problem.\n\n"
        f"File to fix (edit this exact file in place -- do not create a new file): {target_full}\n\n"
        f"Original app type: {criteria.get('app_type', 'unknown')}\n"
        f"Original theme: {criteria.get('theme', 'unknown')}\n"
        f"Original idea: {criteria.get('idea', 'unknown')}\n\n"
        f"Reported problem: {issue_description}\n\n"
        "Read the existing file, reproduce and diagnose the root cause of the reported problem "
        "by tracing through the actual logic (do not guess), and fix it with the smallest change "
        "that reliably solves it. Preserve everything else about the app -- its visual theme, "
        "existing features, filename, and overall structure -- unless the fix genuinely requires "
        "changing them. Do NOT create a new file, rename this file, or touch any other file. Keep "
        "the file fully self-contained (no external dependencies, no CDN links) and preserve the "
        "mandatory viewport meta tag and the CONCEPT comment already in the file."
    )


def generate_app_worker(request_id):
    data = load_data()
    req = next((r for r in data.get("app_requests", []) if r.get("id") == request_id), None)
    if req is None:
        return
    kind = req.get("kind", "build")
    target_filename = req.get("target_filename")
    requester_name = req.get("requester_name", "")

    with GENERATION_SEMAPHORE:
        started = now_iso()
        update_app_request(request_id, status="generating", started=started)
        print(f"[builder] {request_id} ({kind}) starting -> {target_filename}", flush=True)

        target_full_path = CUSTOM_APPS_DIR / target_filename
        CUSTOM_APPS_DIR.mkdir(exist_ok=True)

        if kind == "fix":
            original = next((r for r in data.get("app_requests", []) if r.get("id") == req.get("fix_of")), None)
            prompt = build_fix_prompt(original, req.get("issue_description", ""), target_filename)
            mtime_before = target_full_path.stat().st_mtime if target_full_path.exists() else 0
        else:
            criteria = req.get("criteria", {})
            mode = req.get("mode", "basic")
            prompt = build_prompt(criteria, mode, target_filename, requester_name)
            mtime_before = None

        log_tail = ""
        try:
            result = subprocess.run(
                ["claude", "--permission-mode", "dontAsk", "-p", prompt,
                 "--allowedTools", f"Write({CUSTOM_APPS_DIR}\\**),Edit({CUSTOM_APPS_DIR}\\**),Read,Glob,Grep",
                 "--max-turns", "30"],
                capture_output=True, text=True, timeout=GENERATION_TIMEOUT_SEC,
                encoding="utf-8", errors="replace", cwd=str(APPS_DIR),
            )
            log_tail = ((result.stdout or "") + (result.stderr or ""))[-2000:]
            finished = now_iso()

            if kind == "fix":
                # A fix edits an already-existing file, so "exists and non-empty" is
                # trivially true even if nothing happened -- require the mtime to have
                # actually advanced as the real signal that a change was made.
                touched = target_full_path.exists() and target_full_path.stat().st_mtime > mtime_before
                if touched:
                    print(f"[builder] {request_id} done (fix applied) -> {target_filename}", flush=True)
                    update_app_request(request_id, status="done", finished=finished, log_tail=log_tail)
                else:
                    err = f"Fix did not modify the file (exit code {result.returncode})."
                    print(f"[builder] {request_id} error: {err}", flush=True)
                    update_app_request(request_id, status="error", finished=finished, error_message=err, log_tail=log_tail)
                return

            actual_filename = target_filename
            if not (target_full_path.exists() and target_full_path.stat().st_size > 0):
                # Defensive fallback: look for the newest html file created since we started
                started_ts = time.mktime(time.strptime(started, "%Y-%m-%dT%H:%M:%S"))
                candidates = [
                    p for p in CUSTOM_APPS_DIR.glob("*.html")
                    if p.stat().st_mtime >= started_ts
                ]
                if candidates:
                    newest = max(candidates, key=lambda p: p.stat().st_mtime)
                    actual_filename = newest.name
                    target_full_path = newest
                else:
                    target_full_path = None

            if target_full_path and target_full_path.exists() and target_full_path.stat().st_size > 0:
                print(f"[builder] {request_id} done -> {actual_filename}", flush=True)
                update_app_request(
                    request_id, status="done", finished=finished, log_tail=log_tail,
                    target_filename=actual_filename,
                    target_path=f"custom_apps/{actual_filename}",
                )
                send_build_notification(requester_name, req.get("requester_email", ""), f"custom_apps/{actual_filename}")
            else:
                err = f"No file was created (exit code {result.returncode})."
                print(f"[builder] {request_id} error: {err}", flush=True)
                update_app_request(request_id, status="error", finished=finished, error_message=err, log_tail=log_tail)

        except subprocess.TimeoutExpired:
            finished = now_iso()
            print(f"[builder] {request_id} error: timed out after {GENERATION_TIMEOUT_SEC}s", flush=True)
            update_app_request(
                request_id, status="error", finished=finished,
                error_message=f"Timed out after {GENERATION_TIMEOUT_SEC} seconds.", log_tail=log_tail,
            )
        except FileNotFoundError:
            # Matches daily_check.py's ask_claude() -- same subprocess.run(["claude", ...])
            # shape, same failure mode if the CLI isn't resolvable on PATH.
            finished = now_iso()
            err = "claude CLI not found -- ensure Claude Code is installed and on PATH."
            print(f"[builder] {request_id} error: {err}", flush=True)
            update_app_request(request_id, status="error", finished=finished, error_message=err, log_tail=log_tail)
        except Exception as e:
            finished = now_iso()
            print(f"[builder] {request_id} error: {e}", flush=True)
            update_app_request(request_id, status="error", finished=finished, error_message=str(e), log_tail=log_tail)


def _star_html(path, current_rating):
    stars = ""
    for i in range(1, 6):
        filled = "filled" if i <= current_rating else ""
        stars += (
            f'<span class="star {filled}" data-path="{path}" '
            f'data-star="{i}">&#9733;</span>'
        )
    return f'<div class="star-row">{stars}</div>'


def _make_card(app, favorites, ratings, removed_set, opened, now, threshold_new, is_removed=False, playlists=None):
    path = app["path"]
    is_fav = path in favorites
    rating = ratings.get(path, 0)
    is_new = (now - app["mtime"]) < threshold_new
    is_unread = path not in opened

    heart = "&#9829;" if is_fav else "&#9825;"
    heart_cls = "fav-btn active" if is_fav else "fav-btn"
    fav_border = "favorite" if is_fav else ""

    badges = ""
    if is_new:
        badges += '<span class="badge badge-new">NEW</span>'
    if is_unread:
        badges += '<span class="badge badge-unread">UNREAD</span>'

    stars = _star_html(path, rating)
    safe_id = path.replace("/", "__").replace(".", "_")
    is_pinned = any(path in p.get("apps", []) for p in (playlists or {}).values())
    pin_cls = "pin-btn pinned" if is_pinned else "pin-btn"

    if is_removed:
        return (
            f'\n            <div class="app-card {fav_border}" data-path="{path}" id="card-{safe_id}">'
            f'\n              <button class="{heart_cls}" data-path="{path}" title="Favorite">{heart}</button>'
            f'\n              <div class="app-main">'
            f'\n                <span class="app-name">{app["name"]}</span>'
            f'\n                <div class="card-meta">{badges}{stars}</div>'
            f'\n              </div>'
            f'\n              <button class="restore-btn" data-path="{path}" title="Restore">Restore</button>'
            f'\n            </div>'
        )
    else:
        app_name_esc = app["name"].replace('"', '&quot;')
        return (
            f'\n            <div class="app-item" id="item-{safe_id}">'
            f'\n              <a href="/{path}" class="app-link" data-path="{path}">'
            f'\n                <div class="app-card {fav_border}" data-path="{path}" id="card-{safe_id}">'
            f'\n                  <button class="{heart_cls}" data-path="{path}" title="Favorite">{heart}</button>'
            f'\n                  <div class="app-main">'
            f'\n                    <span class="app-name">{app["name"]}</span>'
            f'\n                    <div class="card-meta">{badges}{stars}</div>'
            f'\n                  </div>'
            f'\n                  <button class="note-quick-btn" data-path="{path}" data-name="{app_name_esc}" data-id="{safe_id}" title="Quick note">&#128221;</button>'
            f'\n                  <button class="{pin_cls}" data-path="{path}" title="Add to playlist">&#128204;</button>'
            f'\n                  <button class="remove-btn" data-path="{path}" title="Remove">&#10005;</button>'
            f'\n                </div>'
            f'\n              </a>'
            f'\n              <div class="quick-note-form hidden" id="qnote-{safe_id}">'
            f'\n                <textarea class="quick-note-ta" placeholder="Note for AI checker..."></textarea>'
            f'\n                <div class="quick-note-actions">'
            f'\n                  <button class="quick-note-submit" data-path="{path}" data-name="{app_name_esc}">Add Note</button>'
            f'\n                  <button class="quick-note-cancel" data-id="{safe_id}">Cancel</button>'
            f'\n                </div>'
            f'\n              </div>'
            f'\n            </div>'
        )


def build_category_html(category, safe_cat, icon, items, data):
    """Generate inner HTML for a category view (lazy-loaded on demand)."""
    favorites = set(data.get("favorites", []))
    ratings = data.get("ratings", {})
    removed_set = set(data.get("removed", []))
    opened = set(data.get("opened", []))
    playlists = data.get("playlists", {})
    now = time.time()
    threshold_new = 48 * 3600

    fav_items = [a for a in items if a["path"] in favorites and a["path"] not in removed_set]
    reg_items = [a for a in items if a["path"] not in favorites and a["path"] not in removed_set]
    visible_count = len(fav_items) + len(reg_items)

    cards = ""
    for app in fav_items + reg_items:
        cards += _make_card(app, favorites, ratings, removed_set, opened, now, threshold_new, playlists=playlists)

    return (
        f'<div class="cat-nav">'
        f'<button class="back-btn">&#8592; Categories</button>'
        f'<span class="cat-nav-title">{icon} {category} <span class="count">{visible_count}</span></span>'
        f'</div>'
        f'<div class="cat-search-wrap">'
        f'<input class="cat-search" type="search" placeholder="Search {category}..." data-cat="{safe_cat}" autocomplete="off">'
        f'</div>'
        f'<div class="cat-app-list" id="catlist-{safe_cat}">'
        f'{cards}'
        f'</div>'
    )


def build_playlist_html(playlist_id, playlist, all_apps_map, data):
    """Generate inner HTML for a playlist view (lazy-loaded on demand)."""
    favorites = set(data.get("favorites", []))
    ratings = data.get("ratings", {})
    removed_set = set(data.get("removed", []))
    opened = set(data.get("opened", []))
    playlists = data.get("playlists", {})
    now = time.time()
    threshold_new = 48 * 3600

    pl_name = playlist.get("name", "Playlist")
    pl_emoji = playlist.get("emoji", "📋")
    pl_apps = [p for p in playlist.get("apps", []) if p not in removed_set]

    cards = ""
    for path in pl_apps:
        app = all_apps_map.get(path)
        if app:
            cards += _make_card(app, favorites, ratings, removed_set, opened, now, threshold_new, playlists=playlists)

    if not cards:
        cards = '<p style="color:var(--muted);padding:1.5rem;text-align:center;font-style:italic">No apps in this playlist yet — pin apps using the \U0001f4cc button on any app card.</p>'

    return (
        f'<div class="cat-nav">'
        f'<button class="back-btn pl-back-btn">&#8592; Playlists</button>'
        f'<span class="cat-nav-title">{html.escape(pl_emoji)} {html.escape(pl_name)} <span class="count">{len(pl_apps)}</span></span>'
        f'</div>'
        f'<div class="cat-app-list" id="pllist-{playlist_id}">'
        f'{cards}'
        f'</div>'
    )


def generate_index(apps, reviews, base_url):
    data = load_data()
    favorites = set(data.get("favorites", []))
    removed = set(data.get("removed", []))
    now = time.time()
    threshold_new = 48 * 3600

    app_count = sum(len(v) for v in apps.values())
    review_count = len(reviews)
    notes = sorted(data.get("notes", []), key=lambda n: n.get("created", ""), reverse=True)
    note_count = len(notes)
    pending_count = sum(1 for n in notes if not n.get("reviewed"))
    notes_tab_label = f"({pending_count} pending)" if pending_count else f"({note_count})"
    playlists = data.get("playlists", {})
    playlists_json = json.dumps(playlists).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    playlist_count = len(playlists)

    app_requests = data.get("app_requests", [])
    app_requests_public = [strip_private_fields(r) for r in app_requests]
    app_requests_json = json.dumps(app_requests_public).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    app_request_count = len(app_requests)

    builders_json = json.dumps(list_builders(data)).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    notes_items_html = ""
    for note in notes:
        created = note.get("created", "")[:16].replace("T", " ")
        status_cls = "reviewed" if note.get("reviewed") else "pending"
        status_txt = "AI Reviewed" if note.get("reviewed") else "Pending AI Review"
        _air = (note.get("ai_response") or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        ai_block = f'<div class="ai-response">{_air}</div>' if _air else ""
        nid = note.get("id", "")
        ntxt = note.get("text","").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        notes_items_html += f'<div class="note-card" id="note-{nid}"><div class="note-header"><span class="note-ts">{created}</span><span class="note-badge {status_cls}">{status_txt}</span><button class="note-delete" data-id="{nid}">&#x1F5D1;</button></div><div class="note-text">{ntxt}</div>{ai_block}</div>\n'
    if not notes_items_html:
        notes_items_html = '<p class="no-notes">No notes yet. Add one above for the daily AI check.</p>'

    # Compact app list for client-side search (name + path + category only)
    all_apps_list = []
    grid_tiles_html = ""
    removed_count = 0

    for category, items in apps.items():
        icon = CATEGORY_ICONS.get(category, "\U0001f4f1")
        safe_cat = re.sub(r'[^a-z0-9]+', '-', category.lower()).strip('-')
        cat_title = f"{icon} {category}"

        fav_items = [a for a in items if a["path"] in favorites and a["path"] not in removed]
        reg_items = [a for a in items if a["path"] not in favorites and a["path"] not in removed]
        rem_items = [a for a in items if a["path"] in removed]
        removed_count += len(rem_items)

        visible_count = len(fav_items) + len(reg_items)
        new_count = sum(1 for a in fav_items + reg_items if (now - a["mtime"]) < threshold_new)
        new_badge = f' &middot; <span class="cat-tile-new">{new_count} new</span>' if new_count else ''

        grid_tiles_html += (
            f'\n        <div class="cat-tile" data-cat="{safe_cat}">'
            f'\n          <span class="cat-tile-icon">{icon}</span>'
            f'\n          <span class="cat-tile-name">{category}</span>'
            f'\n          <span class="cat-tile-count">{visible_count} apps{new_badge}</span>'
            f'\n        </div>'
        )

        for app in fav_items + reg_items:
            all_apps_list.append({
                "name": app["name"],
                "path": app["path"],
                "safeCat": safe_cat,
                "catTitle": cat_title,
            })

    all_apps_json = json.dumps(all_apps_list)

    reviews_html = ""
    if reviews:
        for rev in reviews:
            date = rev["filename"].replace("review-", "").replace(".md", "")
            reviews_html += (
                f'<div class="review-card">'
                f'<div class="review-date">{date}</div>'
                f'{rev["html"]}</div>'
            )
    else:
        reviews_html = '<p class="no-reviews">No review files found in the Reviews folder.</p>'

    review_label = "Reviews" if review_count != 1 else "Review"

    removed_section = ""
    if removed_count > 0:
        removed_section = (
            f'\n  <div id="removed-section">'
            f'\n    <button class="show-removed-btn" id="show-removed-btn">Show removed ({removed_count})</button>'
            f'\n    <div id="removed-list" class="hidden"></div>'
            f'\n  </div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cowork Apps</title>
<meta name="description" content="A local launcher for {app_count} HTML apps — games, tools, education, music, and more.">
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#7c6ee6">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Cowork Apps">
<link rel="apple-touch-icon" href="/icon-192.png">
<style>
  :root {{
    --bg: #0f0f13;
    --surface: #1a1a24;
    --border: #2a2a3a;
    --accent: #7c6ee6;
    --accent2: #e66e7c;
    --text: #e8e8f0;
    --muted: #888899;
    --card-hover: #222232;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
  header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); padding: 2rem 1.5rem 0; border-bottom: 1px solid var(--border); text-align: center; }}
  header h1 {{ font-size: 1.8rem; font-weight: 700; background: linear-gradient(90deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 0.3rem; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.2rem; }}
  .tabs-nav {{ display: flex; border-top: 1px solid var(--border); }}
  .tab-btn {{ flex: 1; padding: 0.8rem; background: transparent; border: none; border-bottom: 3px solid transparent; color: var(--muted); font-size: 0.95rem; font-weight: 500; cursor: pointer; transition: color 0.15s, border-color 0.15s; }}
  .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-btn:hover {{ color: var(--text); }}
  .search-wrap {{ padding: 1rem 1.5rem; max-width: 700px; margin: 0 auto; }}
  #search {{ width: 100%; padding: 0.75rem 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-size: 1rem; outline: none; transition: border-color 0.2s; }}
  #search:focus {{ border-color: var(--accent); }}
  #search::placeholder {{ color: var(--muted); }}
  .count {{ background: var(--border); color: var(--muted); border-radius: 99px; padding: 0.1em 0.5em; font-size: 0.75em; font-weight: 500; text-transform: none; letter-spacing: 0; }}
  .app-list {{ display: flex; flex-direction: column; gap: 0.4rem; }}
  .app-link {{ text-decoration: none; }}
  .app-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.7rem 0.8rem; display: flex; align-items: center; gap: 0.5rem; transition: background 0.15s, border-color 0.15s, transform 0.1s; cursor: pointer; }}
  .app-card:hover, .app-card:active {{ background: var(--card-hover); border-color: var(--accent); transform: translateX(3px); }}
  .app-card.favorite {{ border-color: var(--accent); box-shadow: 0 0 0 1px rgba(124,110,230,0.3); }}
  .app-main {{ flex: 1; min-width: 0; }}
  .app-name {{ color: var(--text); font-size: 0.95rem; display: block; }}
  .card-meta {{ display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.25rem; }}
  .badge {{ font-size: 0.62rem; font-weight: 700; letter-spacing: 0.05em; padding: 0.15em 0.45em; border-radius: 4px; text-transform: uppercase; }}
  .badge-new {{ background: rgba(230,110,124,0.2); color: var(--accent2); border: 1px solid rgba(230,110,124,0.4); }}
  .badge-unread {{ background: rgba(124,110,230,0.2); color: var(--accent); border: 1px solid rgba(124,110,230,0.4); }}
  .star-row {{ display: flex; gap: 1px; }}
  .star {{ font-size: 0.8rem; color: var(--border); cursor: pointer; transition: color 0.1s; user-select: none; }}
  .star.filled {{ color: #f0b429; }}
  .star:hover {{ color: #f0b429; }}
  .fav-btn {{ background: none; border: none; cursor: pointer; font-size: 1.1rem; color: var(--muted); padding: 0.1rem 0.2rem; flex-shrink: 0; line-height: 1; transition: color 0.15s, transform 0.15s; }}
  .fav-btn.active {{ color: var(--accent2); }}
  .fav-btn:hover {{ transform: scale(1.2); color: var(--accent2); }}
  .remove-btn {{ background: none; border: none; cursor: pointer; font-size: 0.85rem; color: var(--muted); padding: 0.2rem 0.3rem; flex-shrink: 0; border-radius: 4px; transition: color 0.15s, background 0.15s; opacity: 0.4; }}
  .app-card:hover .remove-btn {{ opacity: 1; }}
  .remove-btn:hover {{ color: var(--accent2); background: rgba(230,110,124,0.15); }}
  .restore-btn {{ background: rgba(124,110,230,0.15); border: 1px solid rgba(124,110,230,0.4); cursor: pointer; font-size: 0.75rem; color: var(--accent); padding: 0.25rem 0.6rem; flex-shrink: 0; border-radius: 6px; transition: background 0.15s; }}
  .restore-btn:hover {{ background: rgba(124,110,230,0.3); }}
  .hidden {{ display: none !important; }}
  @keyframes fadeout {{ to {{ opacity: 0; transform: scaleY(0); max-height: 0; padding: 0; margin: 0; overflow: hidden; }} }}
  .removing {{ animation: fadeout 0.25s ease forwards; transform-origin: top; }}
  #removed-section {{ max-width: 700px; margin: 0 auto; padding: 0 1.5rem 1rem; }}
  .show-removed-btn {{ background: none; border: none; color: var(--muted); font-size: 0.82rem; cursor: pointer; padding: 0.4rem 0; text-decoration: underline; }}
  .show-removed-btn:hover {{ color: var(--text); }}
  #tab-reviews {{ display: none; padding: 1.5rem; max-width: 960px; margin: 0 auto; }}
  .review-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; }}
  .review-date {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 1rem; }}
  .review-card h1 {{ font-size: 1.25rem; color: var(--text); margin-bottom: 1rem; padding-bottom: 0.6rem; border-bottom: 1px solid var(--border); }}
  .review-card h2 {{ font-size: 1.05rem; color: var(--accent); margin: 1.4rem 0 0.6rem; }}
  .review-card h3 {{ font-size: 0.97rem; color: var(--text); margin: 1.1rem 0 0.4rem; }}
  .review-card p {{ color: #bbbbc8; line-height: 1.65; margin-bottom: 0.7rem; }}
  .review-card hr {{ border: none; border-top: 1px solid var(--border); margin: 1.2rem 0; }}
  .review-card ul {{ padding-left: 1.4rem; margin-bottom: 0.8rem; }}
  .review-card li {{ color: #bbbbc8; line-height: 1.65; margin-bottom: 0.3rem; }}
  .review-card code {{ background: #0d0d18; color: #aaffaa; padding: 0.1em 0.4em; border-radius: 4px; font-size: 0.87em; font-family: monospace; }}
  .review-card strong {{ color: var(--text); }}
  .review-card em {{ color: #bbbbdd; font-style: italic; }}
  .review-card a {{ color: var(--accent); }}
  .table-wrap {{ overflow-x: auto; margin: 0.8rem 0; border-radius: 8px; }}
  .review-table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; }}
  .review-table th, .review-table td {{ text-align: left; padding: 0.5rem 0.75rem; border: 1px solid var(--border); }}
  .review-table th {{ background: #111120; color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 0.73rem; letter-spacing: 0.05em; }}
  .review-table td {{ color: #bbbbc8; vertical-align: top; }}
  .review-table tr:hover td {{ background: #1e1e2e; }}
  .rating-pass {{ color: #44ee66 !important; font-weight: 600; }}
  .rating-warn {{ color: #ffaa00 !important; font-weight: 600; }}
  .rating-fail {{ color: #ff4444 !important; font-weight: 600; }}
  .no-reviews {{ color: var(--muted); font-style: italic; }}
  #tab-notes {{ display: none; padding: 1.5rem; max-width: 700px; margin: 0 auto; }}
  .note-compose {{ margin-bottom: 1.5rem; }}
  .note-compose textarea {{
    width: 100%; min-height: 90px; padding: 0.8rem 1rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; color: var(--text); font-size: 0.95rem;
    resize: vertical; outline: none; font-family: inherit; line-height: 1.5;
    transition: border-color 0.2s;
  }}
  .note-compose textarea:focus {{ border-color: var(--accent); }}
  .note-compose textarea::placeholder {{ color: var(--muted); }}
  .note-submit {{
    margin-top: 0.6rem; padding: 0.6rem 1.4rem;
    background: var(--accent); border: none; border-radius: 8px;
    color: #fff; font-size: 0.9rem; font-weight: 600; cursor: pointer;
    transition: opacity 0.15s;
  }}
  .note-submit:hover {{ opacity: 0.85; }}
  .note-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1rem; margin-bottom: 0.8rem;
  }}
  .note-header {{
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 0.5rem; flex-wrap: wrap;
  }}
  .note-ts {{ font-size: 0.75rem; color: var(--muted); flex: 1; }}
  .note-badge {{
    font-size: 0.7rem; font-weight: 700; padding: 0.15em 0.55em;
    border-radius: 99px; text-transform: uppercase; letter-spacing: 0.04em;
  }}
  .note-badge.pending {{ background: rgba(230,110,124,0.15); color: var(--accent2); }}
  .note-badge.reviewed {{ background: rgba(68,238,102,0.12); color: #44ee66; }}
  .note-delete {{
    background: none; border: none; color: var(--muted);
    cursor: pointer; font-size: 1rem; padding: 0; line-height: 1;
  }}
  .note-delete:hover {{ color: var(--accent2); }}
  .note-text {{ color: var(--text); font-size: 0.92rem; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }}
  .ai-response {{
    margin-top: 0.8rem; padding: 0.75rem 0.9rem;
    background: rgba(124,110,230,0.08); border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0; color: #bbbbc8;
    font-size: 0.88rem; line-height: 1.65; white-space: pre-wrap; word-break: break-word;
  }}
  .ai-label {{ font-size: 0.7rem; color: var(--accent); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.3rem; }}
  .no-notes {{ color: var(--muted); font-style: italic; font-size: 0.9rem; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.78rem; padding: 1rem; border-top: 1px solid var(--border); }}
  .app-item {{ position: relative; }}
  .note-quick-btn {{ background: none; border: none; cursor: pointer; font-size: 0.85rem; color: var(--muted); padding: 0.2rem 0.3rem; flex-shrink: 0; border-radius: 4px; transition: color 0.15s, background 0.15s; opacity: 0.4; }}
  .app-card:hover .note-quick-btn {{ opacity: 1; }}
  .note-quick-btn:hover {{ color: var(--accent); background: rgba(124,110,230,0.15); }}
  .remove-btn.remove-confirm {{ color: var(--accent2) !important; opacity: 1 !important; font-size: 0.75rem; font-weight: 700; }}
  .quick-note-form {{ background: var(--surface); border: 1px solid var(--accent); border-top: none; border-radius: 0 0 10px 10px; padding: 0.6rem 0.8rem; margin-top: -2px; }}
  .quick-note-ta {{ width: 100%; min-height: 60px; padding: 0.5rem 0.7rem; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 0.88rem; resize: none; outline: none; font-family: inherit; line-height: 1.4; transition: border-color 0.2s; }}
  .quick-note-ta:focus {{ border-color: var(--accent); }}
  .quick-note-actions {{ display: flex; gap: 0.5rem; margin-top: 0.4rem; justify-content: flex-end; }}
  .quick-note-submit {{ background: var(--accent); border: none; border-radius: 6px; color: #fff; font-size: 0.8rem; font-weight: 600; padding: 0.35rem 0.8rem; cursor: pointer; transition: opacity 0.15s; }}
  .quick-note-submit:hover {{ opacity: 0.85; }}
  .quick-note-cancel {{ background: none; border: 1px solid var(--border); border-radius: 6px; color: var(--muted); font-size: 0.8rem; padding: 0.35rem 0.7rem; cursor: pointer; transition: color 0.15s; }}
  .quick-note-cancel:hover {{ color: var(--text); }}
  .cat-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; padding: 1rem 1.5rem 2rem; max-width: 700px; margin: 0 auto; }}
  .cat-tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1.2rem 1rem; display: flex; flex-direction: column; align-items: center; gap: 0.4rem; cursor: pointer; transition: background 0.15s, border-color 0.15s, transform 0.12s; text-align: center; }}
  .cat-tile:hover, .cat-tile:active {{ background: var(--card-hover); border-color: var(--accent); transform: translateY(-2px); }}
  .cat-tile-icon {{ font-size: 2rem; line-height: 1; }}
  .cat-tile-name {{ color: var(--text); font-size: 0.9rem; font-weight: 600; }}
  .cat-tile-count {{ color: var(--muted); font-size: 0.75rem; }}
  .cat-tile-new {{ color: var(--accent2); font-weight: 700; }}
  .view-cat {{ padding: 0 1.5rem 2rem; max-width: 700px; margin: 0 auto; }}
  .cat-nav {{ display: flex; align-items: center; gap: 0.8rem; padding: 1rem 0 0.8rem; border-bottom: 1px solid var(--border); margin-bottom: 0.8rem; }}
  .back-btn {{ background: none; border: 1px solid var(--border); border-radius: 8px; color: var(--accent); font-size: 0.85rem; padding: 0.35rem 0.75rem; cursor: pointer; flex-shrink: 0; transition: background 0.15s; }}
  .back-btn:hover {{ background: rgba(124,110,230,0.12); }}
  .cat-nav-title {{ color: var(--text); font-size: 1rem; font-weight: 600; flex: 1; }}
  .cat-search-wrap {{ margin-bottom: 0.8rem; }}
  .cat-search {{ width: 100%; padding: 0.65rem 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-size: 0.95rem; outline: none; transition: border-color 0.2s; }}
  .cat-search:focus {{ border-color: var(--accent); }}
  .cat-search::placeholder {{ color: var(--muted); }}
  .cat-app-list {{ display: flex; flex-direction: column; gap: 0.4rem; }}
  #search-global {{ width: 100%; padding: 0.75rem 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; color: var(--text); font-size: 1rem; outline: none; transition: border-color 0.2s; }}
  #search-global:focus {{ border-color: var(--accent); }}
  #search-global::placeholder {{ color: var(--muted); }}
  .search-result-cat {{ font-size: 0.8rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; padding: 0.8rem 0 0.3rem; }}
  .no-results {{ color: var(--muted); font-style: italic; font-size: 0.9rem; padding: 1rem 0; }}
  .search-result-link .app-card {{ border-radius: 10px; }}
  .loading-msg {{ color: var(--muted); font-style: italic; padding: 2rem; text-align: center; }}
  /* ---- Playlists ---- */
  .pin-btn {{ background: none; border: none; cursor: pointer; font-size: 0.85rem; color: var(--muted); padding: 0.2rem 0.3rem; flex-shrink: 0; border-radius: 4px; transition: color 0.15s, background 0.15s; opacity: 0.4; }}
  .app-card:hover .pin-btn {{ opacity: 1; }}
  .pin-btn.pinned {{ color: var(--accent); opacity: 1; }}
  .pin-btn:hover {{ color: var(--accent); background: rgba(124,110,230,0.15); }}
  #tab-playlists {{ display: none; padding: 1.5rem; max-width: 700px; margin: 0 auto; }}
  .pl-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }}
  .pl-header h2 {{ font-size: 1rem; font-weight: 600; color: var(--text); }}
  .pl-new-btn {{ background: var(--accent); border: none; border-radius: 8px; color: #fff; font-size: 0.85rem; font-weight: 600; padding: 0.45rem 1rem; cursor: pointer; transition: opacity 0.15s; }}
  .pl-new-btn:hover {{ opacity: 0.85; }}
  .playlist-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 0.75rem; }}
  .playlist-tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem 0.75rem; cursor: pointer; text-align: center; transition: background 0.15s, border-color 0.15s, transform 0.12s; position: relative; }}
  .playlist-tile:hover {{ background: var(--card-hover); border-color: var(--accent); transform: translateY(-2px); }}
  .playlist-tile-emoji {{ font-size: 2rem; display: block; margin-bottom: 0.4rem; }}
  .playlist-tile-name {{ font-size: 0.85rem; color: var(--text); font-weight: 600; word-break: break-word; }}
  .playlist-tile-count {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.25rem; }}
  .playlist-tile-del {{ position: absolute; top: 0.3rem; right: 0.4rem; background: none; border: none; color: var(--muted); font-size: 0.8rem; cursor: pointer; opacity: 0; transition: opacity 0.15s, color 0.15s; padding: 0.1rem 0.2rem; }}
  .playlist-tile:hover .playlist-tile-del {{ opacity: 1; }}
  .playlist-tile-del:hover {{ color: var(--accent2); }}
  #playlist-view-container {{ padding: 0 1.5rem 2rem; max-width: 700px; margin: 0 auto; }}
  #create-playlist-form {{ background: var(--surface); border: 1px solid var(--accent); border-radius: 10px; padding: 1rem; margin-bottom: 1.2rem; display: none; }}
  #create-playlist-form label {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 0.4rem; }}
  #pl-name-input {{ width: 100%; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.95rem; outline: none; font-family: inherit; transition: border-color 0.2s; margin-bottom: 0.75rem; }}
  #pl-name-input:focus {{ border-color: var(--accent); }}
  .emoji-picker {{ display: flex; gap: 0.35rem; flex-wrap: wrap; margin-bottom: 0.75rem; }}
  .emoji-opt {{ font-size: 1.4rem; cursor: pointer; border-radius: 6px; padding: 0.15rem 0.3rem; border: 2px solid transparent; transition: border-color 0.12s; line-height: 1.4; }}
  .emoji-opt.selected {{ border-color: var(--accent); background: rgba(124,110,230,0.12); }}
  .pl-form-actions {{ display: flex; gap: 0.5rem; justify-content: flex-end; }}
  .pl-create-btn {{ background: var(--accent); border: none; border-radius: 7px; color: #fff; font-size: 0.88rem; font-weight: 600; padding: 0.45rem 1.1rem; cursor: pointer; transition: opacity 0.15s; }}
  .pl-create-btn:hover {{ opacity: 0.85; }}
  .pl-cancel-btn {{ background: none; border: 1px solid var(--border); border-radius: 7px; color: var(--muted); font-size: 0.88rem; padding: 0.45rem 0.85rem; cursor: pointer; transition: color 0.15s; }}
  .pl-cancel-btn:hover {{ color: var(--text); }}
  .pin-picker {{ position: fixed; z-index: 500; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.5rem; min-width: 200px; max-width: 260px; box-shadow: 0 8px 32px rgba(0,0,0,0.55); }}
  .pin-picker-header {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; padding: 0.25rem 0.5rem 0.4rem; }}
  .pin-picker-item {{ display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.5rem; border-radius: 6px; cursor: pointer; transition: background 0.12s; }}
  .pin-picker-item:hover {{ background: var(--card-hover); }}
  .pin-picker-check {{ width: 15px; height: 15px; accent-color: var(--accent); flex-shrink: 0; }}
  .pin-picker-emoji {{ font-size: 0.95rem; flex-shrink: 0; }}
  .pin-picker-label {{ font-size: 0.88rem; color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .pin-picker-empty {{ font-size: 0.82rem; color: var(--muted); padding: 0.4rem 0.5rem; font-style: italic; }}
  .pin-picker-new {{ font-size: 0.82rem; color: var(--accent); padding: 0.45rem 0.5rem; cursor: pointer; border-top: 1px solid var(--border); margin-top: 0.3rem; border-radius: 0 0 6px 6px; transition: background 0.12s; }}
  .pin-picker-new:hover {{ background: rgba(124,110,230,0.12); }}
  .pl-empty {{ color: var(--muted); font-style: italic; font-size: 0.9rem; padding: 1rem 0; }}
  /* ---- App Builder ---- */
  #tab-builder {{ display: none; padding: 1.5rem; max-width: 700px; margin: 0 auto; }}
  .builder-form {{ background: var(--surface); border: 1px solid var(--accent); border-radius: 10px; padding: 1rem; margin-bottom: 1.2rem; }}
  .builder-form label {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; display: block; margin: 0.75rem 0 0.4rem; }}
  .builder-form label:first-child {{ margin-top: 0; }}
  #builder-name-input, #builder-theme-input, #builder-inspired-input, #builder-name-select, #builder-email-input {{ width: 100%; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.95rem; outline: none; font-family: inherit; transition: border-color 0.2s; }}
  #builder-name-input:focus, #builder-theme-input:focus, #builder-inspired-input:focus, #builder-name-select:focus, #builder-email-input:focus {{ border-color: var(--accent); }}
  #builder-name-select {{ margin-bottom: 0.5rem; }}
  .builder-optional {{ text-transform: none; letter-spacing: normal; font-weight: 400; opacity: 0.75; }}
  #builder-idea-input, #builder-tech-input {{ width: 100%; min-height: 60px; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.95rem; outline: none; font-family: inherit; resize: vertical; transition: border-color 0.2s; }}
  #builder-idea-input:focus, #builder-tech-input:focus {{ border-color: var(--accent); }}
  .mode-toggle {{ display: flex; gap: 0.4rem; margin-bottom: 0.5rem; }}
  .mode-toggle-btn {{ flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 0.85rem; font-weight: 600; padding: 0.5rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }}
  .mode-toggle-btn.active {{ color: var(--accent); border-color: var(--accent); background: rgba(124,110,230,0.1); }}
  .choice-group {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}
  .choice-opt {{ font-size: 0.85rem; color: var(--text); cursor: pointer; border-radius: 7px; padding: 0.4rem 0.75rem; border: 2px solid var(--border); transition: border-color 0.12s, background 0.12s; }}
  .choice-opt.selected {{ border-color: var(--accent); background: rgba(124,110,230,0.12); color: var(--accent); }}
  .choice-checkboxes {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
  .choice-checkbox {{ display: flex; align-items: center; gap: 0.35rem; font-size: 0.83rem; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 7px; padding: 0.35rem 0.6rem; cursor: pointer; }}
  .choice-checkbox input {{ accent-color: var(--accent); }}
  #builder-advanced-fields.hidden {{ display: none; }}
  .builder-lists {{ margin-top: 1.5rem; }}
  .builder-list-heading {{ font-size: 0.85rem; font-weight: 600; color: var(--text); margin: 1.2rem 0 0.6rem; }}
  .builder-card-list {{ display: flex; flex-direction: column; gap: 0.6rem; }}
  .builder-empty {{ color: var(--muted); font-style: italic; font-size: 0.88rem; }}
  .builder-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem 0.9rem; }}
  .builder-card-header {{ display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.3rem; }}
  .builder-card-title {{ font-size: 0.9rem; color: var(--text); font-weight: 600; }}
  .builder-card-meta {{ font-size: 0.75rem; color: var(--muted); }}
  .builder-badge {{ font-size: 0.68rem; font-weight: 700; padding: 0.15em 0.55em; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; flex-shrink: 0; }}
  .builder-badge.queued {{ background: rgba(136,136,153,0.15); color: var(--muted); }}
  .builder-badge.generating {{ background: rgba(124,110,230,0.15); color: var(--accent); }}
  .builder-badge.done {{ background: rgba(68,238,102,0.12); color: #44ee66; }}
  .builder-badge.error {{ background: rgba(230,110,124,0.15); color: var(--accent2); }}
  .builder-card-open {{ display: inline-block; margin-top: 0.4rem; margin-right: 0.6rem; font-size: 0.83rem; color: var(--accent); text-decoration: none; font-weight: 600; }}
  .builder-card-open:hover {{ text-decoration: underline; }}
  .builder-card-error {{ margin-top: 0.4rem; font-size: 0.82rem; color: var(--accent2); }}
  .report-btn {{ display: inline-block; margin-top: 0.4rem; font-size: 0.78rem; color: var(--muted); background: none; border: 1px solid var(--border); border-radius: 6px; padding: 0.25rem 0.6rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }}
  .report-btn:hover {{ color: var(--accent2); border-color: var(--accent2); }}
  .report-form {{ margin-top: 0.5rem; }}
  .report-ta {{ width: 100%; min-height: 50px; padding: 0.5rem 0.7rem; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 0.85rem; resize: vertical; outline: none; font-family: inherit; line-height: 1.4; transition: border-color 0.2s; }}
  .report-ta:focus {{ border-color: var(--accent2); }}
  .fix-status {{ margin-top: 0.4rem; font-size: 0.8rem; color: var(--muted); font-style: italic; }}
  .fix-status-done {{ color: #44ee66; font-style: normal; }}
  .fix-status-error {{ color: var(--accent2); font-style: normal; }}
</style>
</head>
<body>
<header>
  <h1>Cowork Apps</h1>
  <p class="subtitle">{app_count} apps &middot; {review_count} {review_label}</p>
  <div class="tabs-nav">
    <button class="tab-btn active" data-tab="apps">&#128241; Apps ({app_count})</button>
    <button class="tab-btn" data-tab="reviews">&#11088; Reviews ({review_count})</button>
    <button class="tab-btn" data-tab="notes">&#128203; Notes {notes_tab_label}</button>
    <button class="tab-btn" data-tab="playlists">&#128204; Lists ({playlist_count})</button>
    <button class="tab-btn" data-tab="builder">&#128736; Build ({app_request_count})</button>
  </div>
</header>

<main>
<div id="tab-apps">
  <div class="search-wrap">
    <input id="search-global" type="search" placeholder="Search all apps..." autocomplete="off">
  </div>
  <div id="view-grid">
    <div class="cat-grid">
{grid_tiles_html}
    </div>
  </div>
  <div id="search-results-view" class="hidden" style="padding:0 1.5rem 2rem;max-width:700px;margin:0 auto;">
    <div id="search-results-list"></div>
  </div>
  <div id="cat-view-container" class="view-cat hidden"></div>
{removed_section}
</div>

<div id="tab-reviews">
{reviews_html}
</div>

<div id="tab-notes">
  <div class="note-compose">
    <textarea id="noteText" placeholder="Type a note for the daily AI check..."></textarea>
    <button class="note-submit" id="addNoteBtn">Add Note</button>
  </div>
  <div id="notesList">
{notes_items_html}  </div>
</div>
</main>

<div id="tab-playlists">
  <div class="pl-header">
    <h2>&#128204; My Playlists</h2>
    <button class="pl-new-btn" id="pl-new-btn">&#65291; New Playlist</button>
  </div>
  <div id="create-playlist-form">
    <label>Playlist name</label>
    <input id="pl-name-input" type="text" placeholder="e.g. Emma&#39;s Games" autocomplete="off" maxlength="40">
    <label>Pick an emoji</label>
    <div class="emoji-picker" id="emoji-picker">
      <span class="emoji-opt selected">&#127918;</span>
      <span class="emoji-opt">&#11088;</span>
      <span class="emoji-opt">&#127775;</span>
      <span class="emoji-opt">&#127926;</span>
      <span class="emoji-opt">&#127968;</span>
      <span class="emoji-opt">&#128218;</span>
      <span class="emoji-opt">&#127358;</span>
      <span class="emoji-opt">&#129309;</span>
    </div>
    <div class="pl-form-actions">
      <button class="pl-cancel-btn" id="pl-cancel-btn">Cancel</button>
      <button class="pl-create-btn" id="pl-create-btn">Create Playlist</button>
    </div>
  </div>
  <div class="playlist-grid" id="playlist-grid"></div>
</div>

<div id="playlist-view-container" class="hidden"></div>

<div id="tab-builder">
  <div class="pl-header">
    <h2>&#128736; Build Your Own App</h2>
  </div>
  <div class="builder-form">
    <label>Your name</label>
    <select id="builder-name-select">
      <option value="">&#10133; New name&hellip;</option>
    </select>
    <input id="builder-name-input" type="text" placeholder="e.g. Emma" autocomplete="off" maxlength="30">

    <label>Email <span class="builder-optional">(optional &mdash; get notified when it's built)</span></label>
    <input id="builder-email-input" type="email" placeholder="you@example.com" autocomplete="off" maxlength="100">

    <div class="mode-toggle">
      <button class="mode-toggle-btn active" id="mode-basic-btn" data-mode="basic">Basic</button>
      <button class="mode-toggle-btn" id="mode-advanced-btn" data-mode="advanced">Advanced</button>
    </div>

    <label>App type</label>
    <div class="choice-group" id="builder-app-type" data-field="app_type">
      <span class="choice-opt selected" data-value="Game">&#127918; Game</span>
      <span class="choice-opt" data-value="Puzzle">&#129513; Puzzle</span>
      <span class="choice-opt" data-value="Quiz">&#10067; Quiz</span>
      <span class="choice-opt" data-value="Story">&#128214; Story</span>
      <span class="choice-opt" data-value="Tool">&#128295; Tool</span>
      <span class="choice-opt" data-value="Art">&#127912; Art</span>
      <span class="choice-opt" data-value="Music">&#127925; Music</span>
    </div>

    <label>Theme / subject</label>
    <input id="builder-theme-input" type="text" placeholder="e.g. dinosaurs, space pirates" autocomplete="off" maxlength="60">

    <label>Difficulty</label>
    <div class="choice-group" id="builder-difficulty" data-field="difficulty">
      <span class="choice-opt selected" data-value="Easy">Easy</span>
      <span class="choice-opt" data-value="Medium">Medium</span>
      <span class="choice-opt" data-value="Hard">Hard</span>
    </div>

    <label>Color vibe</label>
    <div class="choice-group" id="builder-color-vibe" data-field="color_vibe">
      <span class="choice-opt selected" data-value="Bright &amp; Playful">Bright &amp; Playful</span>
      <span class="choice-opt" data-value="Cool &amp; Calm">Cool &amp; Calm</span>
      <span class="choice-opt" data-value="Dark &amp; Mysterious">Dark &amp; Mysterious</span>
      <span class="choice-opt" data-value="Neon &amp; Energetic">Neon &amp; Energetic</span>
      <span class="choice-opt" data-value="Pastel &amp; Soft">Pastel &amp; Soft</span>
    </div>

    <label>Your idea (one line)</label>
    <textarea id="builder-idea-input" placeholder="e.g. A maze game where you're a dragon collecting gems" maxlength="200"></textarea>

    <div id="builder-advanced-fields" class="hidden">
      <label>Mechanics (pick any)</label>
      <div class="choice-checkboxes" id="builder-mechanics">
        <label class="choice-checkbox"><input type="checkbox" value="Timer/Countdown"> Timer/Countdown</label>
        <label class="choice-checkbox"><input type="checkbox" value="Score/Points"> Score/Points</label>
        <label class="choice-checkbox"><input type="checkbox" value="Levels"> Levels</label>
        <label class="choice-checkbox"><input type="checkbox" value="Local multiplayer"> Local multiplayer</label>
        <label class="choice-checkbox"><input type="checkbox" value="Sound effects"> Sound effects</label>
        <label class="choice-checkbox"><input type="checkbox" value="Drag &amp; drop"> Drag &amp; drop</label>
        <label class="choice-checkbox"><input type="checkbox" value="Keyboard controls"> Keyboard controls</label>
        <label class="choice-checkbox"><input type="checkbox" value="Touch/swipe"> Touch/swipe</label>
        <label class="choice-checkbox"><input type="checkbox" value="Randomized"> Randomized</label>
        <label class="choice-checkbox"><input type="checkbox" value="Save progress"> Save progress</label>
      </div>

      <label>Age range</label>
      <div class="choice-group" id="builder-age-range" data-field="age_range">
        <span class="choice-opt" data-value="4-6">4-6</span>
        <span class="choice-opt" data-value="7-9">7-9</span>
        <span class="choice-opt" data-value="10-12">10-12</span>
        <span class="choice-opt" data-value="13-16">13-16</span>
        <span class="choice-opt selected" data-value="All ages">All ages</span>
      </div>

      <label>Anything specific? (optional)</label>
      <textarea id="builder-tech-input" placeholder="e.g. a leaderboard of best times" maxlength="300"></textarea>

      <label>Make it feel like&hellip; (optional)</label>
      <input id="builder-inspired-input" type="text" placeholder="e.g. Flappy Bird" autocomplete="off" maxlength="100">
    </div>

    <div class="pl-form-actions">
      <button class="pl-create-btn" id="builder-submit-btn">Build My App!</button>
    </div>
  </div>

  <div class="builder-lists">
    <h2 class="builder-list-heading">Your Creations</h2>
    <div id="builder-mine-list" class="builder-card-list"></div>
    <h2 class="builder-list-heading">Family Creations</h2>
    <div id="builder-family-list" class="builder-card-list"></div>
  </div>
</div>

<footer>Auto-refreshes on each visit &middot; {APPS_DIR}</footer>

<script>
const ALL_APPS = {all_apps_json};
let PLAYLISTS = {playlists_json};
const catCache = {{}};
const playlistCache = {{}};
let pickerOpen = null;

const tabs = document.querySelectorAll('.tab-btn');
const panels = {{}};
document.querySelectorAll('[id^="tab-"]').forEach(p => {{ panels[p.id.replace('tab-', '')] = p; }});
const plView = document.getElementById('playlist-view-container');

function switchTab(name) {{
  tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  Object.entries(panels).forEach(([k, p]) => {{ p.style.display = k === name ? 'block' : 'none'; }});
  plView.classList.add('hidden');
  if (name === 'playlists') {{
    renderPlaylistGrid();
  }}
  if (name === 'builder') {{
    loadAppRequests();
  }}
  location.hash = name === 'apps' ? '' : name;
}}

tabs.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
const hash = location.hash.slice(1);
if (hash && panels[hash]) switchTab(hash);

function showGrid() {{
  document.getElementById('cat-view-container').classList.add('hidden');
  document.getElementById('search-results-view').classList.add('hidden');
  document.getElementById('view-grid').classList.remove('hidden');
  document.getElementById('search-global').value = '';
}}

function showCat(safeCat) {{
  document.getElementById('view-grid').classList.add('hidden');
  document.getElementById('search-results-view').classList.add('hidden');
  const container = document.getElementById('cat-view-container');
  container.classList.remove('hidden');
  container._currentCat = safeCat;

  if (catCache[safeCat]) {{
    container.innerHTML = catCache[safeCat];
    attachCatListeners(container);
    return;
  }}

  container.innerHTML = '<p class="loading-msg">Loading…</p>';
  fetch('/api/category/' + safeCat)
    .then(r => r.json())
    .then(d => {{
      if (container._currentCat !== safeCat) return;
      catCache[safeCat] = d.html;
      container.innerHTML = d.html;
      attachCatListeners(container);
    }});
}}

document.querySelectorAll('.cat-tile').forEach(tile => {{
  tile.addEventListener('click', () => showCat(tile.dataset.cat));
}});

const searchGlobal = document.getElementById('search-global');
searchGlobal.addEventListener('input', () => {{
  const q = searchGlobal.value.toLowerCase().trim();
  const resultsView = document.getElementById('search-results-view');
  const grid = document.getElementById('view-grid');
  document.getElementById('cat-view-container').classList.add('hidden');

  if (!q) {{
    resultsView.classList.add('hidden');
    grid.classList.remove('hidden');
    return;
  }}
  grid.classList.add('hidden');
  resultsView.classList.remove('hidden');

  const bycat = {{}};
  ALL_APPS.forEach(a => {{
    if (!a.name.toLowerCase().includes(q)) return;
    if (!bycat[a.safeCat]) bycat[a.safeCat] = {{ title: a.catTitle, items: [] }};
    bycat[a.safeCat].items.push(a);
  }});

  let html = '';
  Object.values(bycat).forEach(g => {{
    html += '<div class="search-result-cat">' + g.title + '</div><div class="cat-app-list">';
    g.items.forEach(a => {{
      html += '<a href="/' + a.path + '" class="app-link search-result-link"><div class="app-card"><div class="app-main"><span class="app-name">' + a.name + '</span></div></div></a>';
    }});
    html += '</div>';
  }});

  document.getElementById('search-results-list').innerHTML = html || '<p class="no-results">No apps found.</p>';
}});

async function apiPost(endpoint, body) {{
  try {{
    const r = await fetch(endpoint, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(body)
    }});
    return await r.json();
  }} catch(e) {{
    console.error(endpoint, e);
    return null;
  }}
}}

function toggleFav(btn) {{
  const path = btn.dataset.path;
  const isActive = btn.classList.contains('active');
  btn.classList.toggle('active');
  btn.innerHTML = isActive ? '&#9825;' : '&#9829;';
  const card = btn.closest('.app-card');
  if (card) card.classList.toggle('favorite', !isActive);
  apiPost('/api/favorite', {{path}});
}}

function setRating(star) {{
  const path = star.dataset.path;
  const val = parseInt(star.dataset.star);
  const row = star.closest('.star-row');
  row.querySelectorAll('.star').forEach((s, i) => {{
    s.classList.toggle('filled', i < val);
  }});
  apiPost('/api/rate', {{path, stars: val}});
}}

function removeApp(btn) {{
  if (!btn.dataset.confirmed) {{
    btn.dataset.confirmed = '1';
    btn.textContent = 'Sure?';
    btn.classList.add('remove-confirm');
    setTimeout(() => {{
      if (btn.dataset.confirmed) {{
        delete btn.dataset.confirmed;
        btn.innerHTML = '&#10005;';
        btn.classList.remove('remove-confirm');
      }}
    }}, 2500);
    return;
  }}
  delete btn.dataset.confirmed;
  const path = btn.dataset.path;
  const target = btn.closest('.app-item') || btn.closest('.app-link') || btn.closest('.app-card');
  if (target) {{
    target.classList.add('removing');
    target.addEventListener('animationend', () => target.remove(), {{once: true}});
  }}
  apiPost('/api/remove', {{path}});
}}

function restoreApp(btn) {{
  const path = btn.dataset.path;
  const card = btn.closest('.app-card');
  if (card) {{
    card.classList.add('removing');
    card.addEventListener('animationend', () => {{
      card.remove();
      apiPost('/api/remove', {{path}}).then(() => location.reload());
    }}, {{once: true}});
  }} else {{
    apiPost('/api/remove', {{path}}).then(() => location.reload());
  }}
}}

function markOpen(e, link) {{
  const path = link.dataset.path;
  apiPost('/api/open', {{path}});
  const badge = link.querySelector('.badge-unread');
  if (badge) badge.remove();
}}

let removedLoaded = false;
async function toggleRemoved() {{
  const list = document.getElementById('removed-list');
  const btn = document.getElementById('show-removed-btn');

  if (!removedLoaded) {{
    const orig = btn.textContent;
    btn.textContent = 'Loading…';
    const r = await fetch('/api/removed');
    const d = await r.json();
    list.innerHTML = d.html;
    removedLoaded = true;
    attachRemovedListeners(list);
    btn.textContent = orig;
  }}

  const hidden = list.classList.toggle('hidden');
  btn.textContent = btn.textContent.replace(hidden ? 'Hide' : 'Show', hidden ? 'Show' : 'Hide');
}}

document.getElementById('show-removed-btn')?.addEventListener('click', toggleRemoved);

function attachRemovedListeners(container) {{
  container.querySelectorAll('.fav-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); toggleFav(btn); }});
  }});
  container.querySelectorAll('.restore-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); restoreApp(btn); }});
  }});
  container.querySelectorAll('.star').forEach(s => {{
    s.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); setRating(s); }});
  }});
}}

function attachCatListeners(container) {{
  container.querySelector('.back-btn')?.addEventListener('click', showGrid);

  const catSearch = container.querySelector('.cat-search');
  catSearch?.addEventListener('input', () => {{
    const q = catSearch.value.toLowerCase().trim();
    container.querySelectorAll('.app-item').forEach(item => {{
      const name = item.querySelector('.app-name')?.textContent.toLowerCase() || '';
      item.classList.toggle('hidden', q !== '' && !name.includes(q));
    }});
  }});

  container.querySelectorAll('.fav-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); toggleFav(btn); }});
  }});
  container.querySelectorAll('.remove-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); removeApp(btn); }});
  }});
  container.querySelectorAll('.star').forEach(s => {{
    s.addEventListener('click', e => {{ e.preventDefault(); e.stopPropagation(); setRating(s); }});
  }});
  container.querySelectorAll('.app-link').forEach(link => {{
    link.addEventListener('click', e => {{ markOpen(e, link); }});
  }});
  container.querySelectorAll('.note-quick-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{
      e.preventDefault(); e.stopPropagation();
      const form = document.getElementById('qnote-' + btn.dataset.id);
      if (form) {{ form.classList.toggle('hidden'); if (!form.classList.contains('hidden')) form.querySelector('.quick-note-ta').focus(); }}
    }});
  }});
  container.querySelectorAll('.quick-note-submit').forEach(btn => {{
    btn.addEventListener('click', async e => {{
      e.preventDefault();
      const form = btn.closest('.quick-note-form');
      const ta = form.querySelector('.quick-note-ta');
      const text = ta.value.trim();
      if (!text) {{ ta.focus(); return; }}
      const fullText = '[' + btn.dataset.name + '] ' + text;
      btn.disabled = true; btn.textContent = 'Adding...';
      await apiPost('/api/notes/add', {{text: fullText}});
      form.classList.add('hidden');
      ta.value = '';
      btn.disabled = false; btn.textContent = 'Add Note';
    }});
  }});
  container.querySelectorAll('.quick-note-cancel').forEach(btn => {{
    btn.addEventListener('click', e => {{
      e.preventDefault();
      const form = document.getElementById('qnote-' + btn.dataset.id);
      if (form) {{ form.classList.add('hidden'); form.querySelector('.quick-note-ta').value = ''; }}
    }});
  }});
  attachPinListeners(container);
}}

// ---- Playlists ----
function escHtml(s) {{
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

function renderPlaylistGrid() {{
  const grid = document.getElementById('playlist-grid');
  if (!grid) return;
  const ids = Object.keys(PLAYLISTS);
  if (!ids.length) {{
    grid.innerHTML = '<p class="pl-empty">No playlists yet — tap <strong>+ New Playlist</strong> to create one for your family.</p>';
    return;
  }}
  grid.innerHTML = ids.map(id => {{
    const p = PLAYLISTS[id];
    const cnt = (p.apps || []).length;
    return `<div class="playlist-tile" data-plid="${{id}}">
      <button class="playlist-tile-del" data-plid="${{id}}" title="Delete playlist">&#10005;</button>
      <span class="playlist-tile-emoji">${{escHtml(p.emoji || '📋')}}</span>
      <div class="playlist-tile-name">${{escHtml(p.name)}}</div>
      <div class="playlist-tile-count">${{cnt}} app${{cnt !== 1 ? 's' : ''}}</div>
    </div>`;
  }}).join('');
  grid.querySelectorAll('.playlist-tile').forEach(tile => {{
    tile.addEventListener('click', e => {{
      if (e.target.closest('.playlist-tile-del')) return;
      showPlaylistView(tile.dataset.plid);
    }});
  }});
  grid.querySelectorAll('.playlist-tile-del').forEach(btn => {{
    btn.addEventListener('click', async e => {{
      e.stopPropagation();
      const id = btn.dataset.plid;
      const name = PLAYLISTS[id]?.name || 'this playlist';
      if (!confirm('Delete "' + name + '"?')) return;
      const r = await apiPost('/api/playlist/delete', {{playlist_id: id}});
      if (r?.ok) {{
        delete PLAYLISTS[id];
        delete playlistCache[id];
        updatePlaylistTabCount();
        renderPlaylistGrid();
      }}
    }});
  }});
}}

async function showPlaylistView(id) {{
  const container = document.getElementById('playlist-view-container');
  const tabEl = document.getElementById('tab-playlists');
  tabEl.style.display = 'none';
  container.classList.remove('hidden');
  container._currentPl = id;
  if (playlistCache[id]) {{
    container.innerHTML = playlistCache[id];
    attachCatListeners(container);
    container.querySelector('.pl-back-btn')?.addEventListener('click', backToPlaylists);
    return;
  }}
  container.innerHTML = '<p class="loading-msg">Loading…</p>';
  const resp = await fetch('/api/playlist/' + id);
  const d = await resp.json();
  if (container._currentPl !== id) return;
  if (!d.html) {{ container.innerHTML = '<p style="color:var(--muted);padding:1.5rem;text-align:center">Playlist not found.</p>'; return; }}
  playlistCache[id] = d.html;
  container.innerHTML = d.html;
  attachCatListeners(container);
  container.querySelector('.pl-back-btn')?.addEventListener('click', backToPlaylists);
}}

function backToPlaylists() {{
  const container = document.getElementById('playlist-view-container');
  const tabEl = document.getElementById('tab-playlists');
  container.classList.add('hidden');
  tabEl.style.display = '';
  renderPlaylistGrid();
}}

function openPinPicker(appPath, anchorBtn) {{
  closePicker();
  const picker = document.createElement('div');
  picker.className = 'pin-picker';
  const ids = Object.keys(PLAYLISTS);
  let inner = '<div class="pin-picker-header">Add to playlist</div>';
  if (!ids.length) {{
    inner += '<div class="pin-picker-empty">No playlists yet.</div>';
  }} else {{
    inner += ids.map(id => {{
      const p = PLAYLISTS[id];
      const inPl = (p.apps || []).includes(appPath);
      return `<label class="pin-picker-item">
        <input type="checkbox" class="pin-picker-check" ${{inPl ? 'checked' : ''}} data-plid="${{id}}" data-path="${{appPath}}">
        <span class="pin-picker-emoji">${{escHtml(p.emoji || '📋')}}</span>
        <span class="pin-picker-label">${{escHtml(p.name)}}</span>
      </label>`;
    }}).join('');
  }}
  inner += '<div class="pin-picker-new" id="picker-go-create">&#65291; New Playlist</div>';
  picker.innerHTML = inner;

  const rect = anchorBtn.getBoundingClientRect();
  picker.style.top = (rect.bottom + 6) + 'px';
  picker.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 268)) + 'px';
  document.body.appendChild(picker);
  pickerOpen = picker;

  // Stop click propagation inside the picker so the document close-listener
  // only fires on clicks OUTSIDE the picker (not on checkboxes within it).
  picker.addEventListener('click', e => e.stopPropagation());

  picker.querySelectorAll('.pin-picker-check').forEach(cb => {{
    cb.addEventListener('change', async () => {{
      const plid = cb.dataset.plid;
      const path = cb.dataset.path;
      const r = await apiPost('/api/playlist/toggle', {{playlist_id: plid, path}});
      if (r?.ok) {{
        if (r.in_playlist) {{
          if (!PLAYLISTS[plid].apps) PLAYLISTS[plid].apps = [];
          PLAYLISTS[plid].apps.push(path);
        }} else {{
          PLAYLISTS[plid].apps = (PLAYLISTS[plid].apps || []).filter(a => a !== path);
        }}
        delete playlistCache[plid];
        const appMeta = ALL_APPS.find(a => a.path === path);
        if (appMeta?.safeCat) delete catCache[appMeta.safeCat];
        updatePinBtns(path);
        const plContainer = document.getElementById('playlist-view-container');
        if (!plContainer.classList.contains('hidden') && plContainer._currentPl === plid) {{
          showPlaylistView(plid);
        }}
      }}
    }});
  }});

  picker.querySelector('#picker-go-create')?.addEventListener('click', () => {{
    closePicker();
    switchTab('playlists');
    const form = document.getElementById('create-playlist-form');
    if (window.getComputedStyle(form).display === 'none') form.style.display = 'block';
    document.getElementById('pl-name-input').focus();
  }});

  setTimeout(() => document.addEventListener('click', closePicker, {{once: true}}), 10);
}}

function closePicker() {{
  if (pickerOpen) {{ pickerOpen.remove(); pickerOpen = null; }}
}}

function updatePinBtns(path) {{
  const escaped = path.replace(/[!"#$%&'()*+,.\/:;<=>?@[\\\]^`{{|}}~]/g, '\\\\$&');
  const isPinned = Object.values(PLAYLISTS).some(p => (p.apps || []).includes(path));
  document.querySelectorAll('.pin-btn[data-path="' + path + '"]').forEach(b => {{
    b.classList.toggle('pinned', isPinned);
  }});
}}

function updatePlaylistTabCount() {{
  const btn = document.querySelector('.tab-btn[data-tab="playlists"]');
  if (btn) btn.innerHTML = '&#128204; Lists (' + Object.keys(PLAYLISTS).length + ')';
}}

function attachPinListeners(container) {{
  container.querySelectorAll('.pin-btn').forEach(btn => {{
    btn.addEventListener('click', e => {{
      e.preventDefault(); e.stopPropagation();
      openPinPicker(btn.dataset.path, btn);
    }});
  }});
}}

// New playlist form
document.getElementById('pl-new-btn')?.addEventListener('click', () => {{
  const form = document.getElementById('create-playlist-form');
  const hidden = window.getComputedStyle(form).display === 'none';
  form.style.display = hidden ? 'block' : 'none';
  if (hidden) document.getElementById('pl-name-input').focus();
}});
document.getElementById('pl-cancel-btn')?.addEventListener('click', () => {{
  document.getElementById('create-playlist-form').style.display = 'none';
  document.getElementById('pl-name-input').value = '';
}});
document.getElementById('emoji-picker')?.addEventListener('click', e => {{
  const opt = e.target.closest('.emoji-opt');
  if (!opt) return;
  document.querySelectorAll('.emoji-opt').forEach(o => o.classList.remove('selected'));
  opt.classList.add('selected');
}});
document.getElementById('pl-create-btn')?.addEventListener('click', async () => {{
  const name = document.getElementById('pl-name-input').value.trim();
  if (!name) {{ document.getElementById('pl-name-input').focus(); return; }}
  const emoji = document.querySelector('.emoji-opt.selected')?.textContent || '📋';
  const btn = document.getElementById('pl-create-btn');
  btn.disabled = true; btn.textContent = 'Creating…';
  const r = await apiPost('/api/playlist/create', {{name, emoji}});
  btn.disabled = false; btn.textContent = 'Create Playlist';
  if (r?.ok) {{
    PLAYLISTS[r.id] = {{name, emoji, apps: [], created: new Date().toISOString()}};
    document.getElementById('pl-name-input').value = '';
    document.getElementById('create-playlist-form').style.display = 'none';
    updatePlaylistTabCount();
    renderPlaylistGrid();
  }}
}});
document.getElementById('pl-name-input')?.addEventListener('keydown', e => {{
  if (e.key === 'Enter') document.getElementById('pl-create-btn').click();
}});

// ---- Notes ----
document.getElementById('addNoteBtn')?.addEventListener('click', async () => {{
  const ta = document.getElementById('noteText');
  const text = ta.value.trim();
  if (!text) {{ ta.focus(); return; }}
  const btn = document.getElementById('addNoteBtn');
  btn.disabled = true; btn.textContent = 'Adding...';
  await apiPost('/api/notes/add', {{text}});
  location.reload();
}});
document.querySelectorAll('.note-delete').forEach(btn => {{
  btn.addEventListener('click', async () => {{
    if (!confirm('Delete this note?')) return;
    const r = await apiPost('/api/notes/delete', {{id: btn.dataset.id}});
    if (r && r.ok) location.reload();
  }});
}});

// ---- App Builder ----
let APP_REQUESTS = {app_requests_json};
const BUILDERS = {builders_json};
const builderPolls = {{}};

const builderNameSelect = document.getElementById('builder-name-select');
const builderNameInput = document.getElementById('builder-name-input');
const builderEmailInput = document.getElementById('builder-email-input');

function builderEmailFor(name) {{
  return (BUILDERS.find(b => b.name === name) || {{}}).email || '';
}}

if (builderNameSelect) {{
  for (const b of BUILDERS) {{
    const opt = document.createElement('option');
    opt.value = b.name;
    opt.textContent = b.name;
    builderNameSelect.appendChild(opt);
  }}
  builderNameSelect.addEventListener('change', () => {{
    if (!builderNameSelect.value) return;
    builderNameInput.value = builderNameSelect.value;
    builderEmailInput.value = builderEmailFor(builderNameSelect.value);
    localStorage.setItem('cowork-builder-name', builderNameInput.value);
    localStorage.setItem('cowork-builder-email', builderEmailInput.value);
  }});
}}
if (builderNameInput) {{
  builderNameInput.value = localStorage.getItem('cowork-builder-name') || '';
  if (builderNameSelect && BUILDERS.some(b => b.name === builderNameInput.value)) {{
    builderNameSelect.value = builderNameInput.value;
  }}
  builderNameInput.addEventListener('input', () => {{
    localStorage.setItem('cowork-builder-name', builderNameInput.value.trim());
    if (builderNameSelect) builderNameSelect.value = builderNameSelect.value === builderNameInput.value.trim() ? builderNameSelect.value : '';
  }});
}}
if (builderEmailInput) {{
  builderEmailInput.value = localStorage.getItem('cowork-builder-email') || builderEmailFor(builderNameInput?.value || '');
  builderEmailInput.addEventListener('input', () => {{
    localStorage.setItem('cowork-builder-email', builderEmailInput.value.trim());
  }});
}}

document.getElementById('mode-basic-btn')?.addEventListener('click', () => setBuilderMode('basic'));
document.getElementById('mode-advanced-btn')?.addEventListener('click', () => setBuilderMode('advanced'));
function setBuilderMode(mode) {{
  document.getElementById('mode-basic-btn').classList.toggle('active', mode === 'basic');
  document.getElementById('mode-advanced-btn').classList.toggle('active', mode === 'advanced');
  document.getElementById('builder-advanced-fields').classList.toggle('hidden', mode !== 'advanced');
}}

document.querySelectorAll('.choice-group').forEach(group => {{
  group.addEventListener('click', e => {{
    const opt = e.target.closest('.choice-opt');
    if (!opt || !group.contains(opt)) return;
    group.querySelectorAll('.choice-opt').forEach(o => o.classList.remove('selected'));
    opt.classList.add('selected');
  }});
}});

function builderChoice(fieldId) {{
  return document.querySelector('#' + fieldId + ' .choice-opt.selected')?.dataset.value || '';
}}

document.getElementById('builder-submit-btn')?.addEventListener('click', async () => {{
  const requester_name = builderNameInput?.value.trim() || '';
  if (!requester_name) {{ builderNameInput?.focus(); return; }}
  const requester_email = builderEmailInput?.value.trim() || '';
  const mode = document.getElementById('mode-advanced-btn').classList.contains('active') ? 'advanced' : 'basic';

  const criteria = {{
    app_type: builderChoice('builder-app-type'),
    theme: document.getElementById('builder-theme-input').value.trim(),
    difficulty: builderChoice('builder-difficulty'),
    color_vibe: builderChoice('builder-color-vibe'),
    idea: document.getElementById('builder-idea-input').value.trim(),
  }};
  if (!criteria.theme) {{ document.getElementById('builder-theme-input').focus(); return; }}
  if (!criteria.idea) {{ document.getElementById('builder-idea-input').focus(); return; }}
  if (mode === 'advanced') {{
    criteria.mechanics = Array.from(document.querySelectorAll('#builder-mechanics input:checked')).map(cb => cb.value);
    criteria.age_range = builderChoice('builder-age-range');
    const tech = document.getElementById('builder-tech-input').value.trim();
    const inspired = document.getElementById('builder-inspired-input').value.trim();
    if (tech) criteria.tech_requests = tech;
    if (inspired) criteria.inspired_by = inspired;
  }}

  const btn = document.getElementById('builder-submit-btn');
  btn.disabled = true; btn.textContent = 'Building…';
  const r = await apiPost('/api/app_requests/create', {{requester_name, requester_email, mode, criteria}});
  btn.disabled = false; btn.textContent = 'Build My App!';
  if (r?.ok) {{
    APP_REQUESTS.unshift({{
      id: r.id, requester_name, mode, criteria,
      target_filename: r.target_filename, target_path: 'custom_apps/' + r.target_filename,
      status: 'queued', error_message: null, created: new Date().toISOString(),
      started: null, finished: null,
    }});
    document.getElementById('builder-idea-input').value = '';
    renderBuilderLists();
    pollRequest(r.id);
  }} else {{
    alert(r?.error || 'Could not submit — please try again.');
  }}
}});

function builderCardHtml(r) {{
  const labels = {{queued: 'Queued', generating: 'Building…', done: 'Ready ✅', error: 'Error'}};
  const badgeLabel = labels[r.status] || r.status;
  const idea = escHtml((r.criteria && r.criteria.idea) || '');
  const errorHtml = (r.status === 'error' && r.error_message)
    ? '<div class="builder-card-error" id="builder-error-' + r.id + '">' + escHtml(r.error_message) + '</div>' : '';
  const openHtml = (r.status === 'done')
    ? '<a class="builder-card-open" id="builder-open-' + r.id + '" href="/' + r.target_path + '" target="_blank">Open App &rarr;</a>' : '';
  const appType = escHtml((r.criteria && r.criteria.app_type) || 'App');

  let reportHtml = '';
  if (r.status === 'done') {{
    const fixes = APP_REQUESTS.filter(f => f.kind === 'fix' && f.fix_of === r.id);
    const active = fixes.find(f => f.status === 'queued' || f.status === 'generating');
    const finishedFixes = fixes.filter(f => f.status === 'done' || f.status === 'error')
      .sort((a, b) => (a.finished || '').localeCompare(b.finished || ''));
    const last = finishedFixes[finishedFixes.length - 1];

    let fixStatusHtml = '';
    if (active) {{
      fixStatusHtml = '<div class="fix-status">Fix in progress…</div>';
    }} else if (last && last.status === 'done') {{
      fixStatusHtml = '<div class="fix-status fix-status-done">Fix applied ✅ — try it again</div>';
    }} else if (last && last.status === 'error') {{
      fixStatusHtml = '<div class="fix-status fix-status-error">Fix attempt failed: ' + escHtml(last.error_message || '') + '</div>';
    }}

    reportHtml = '<button class="report-btn" data-id="' + r.id + '">&#128027; Report a problem</button>'
      + '<div class="report-form hidden" id="report-form-' + r.id + '">'
      + '<textarea class="report-ta" placeholder="What went wrong? e.g. arrow keys don&#39;t move the character" maxlength="500"></textarea>'
      + '<div class="quick-note-actions">'
      + '<button class="quick-note-cancel report-cancel-btn" data-id="' + r.id + '">Cancel</button>'
      + '<button class="quick-note-submit report-submit-btn" data-id="' + r.id + '">Submit</button>'
      + '</div></div>'
      + fixStatusHtml;
  }}

  return '<div class="builder-card" id="builder-card-' + r.id + '">'
    + '<div class="builder-card-header">'
    + '<span class="builder-card-title">' + appType + ' — ' + escHtml(r.requester_name || '') + '</span>'
    + '<span class="builder-badge ' + r.status + '" id="builder-badge-' + r.id + '">' + badgeLabel + '</span>'
    + '</div>'
    + '<div class="builder-card-meta">' + idea + '</div>'
    + errorHtml + openHtml + reportHtml
    + '</div>';
}}

function renderBuilderLists() {{
  const myName = (builderNameInput?.value || '').trim().toLowerCase();
  const mineList = document.getElementById('builder-mine-list');
  const familyList = document.getElementById('builder-family-list');
  if (!mineList || !familyList) return;
  const builds = APP_REQUESTS.filter(r => (r.kind || 'build') === 'build');
  const mine = myName ? builds.filter(r => (r.requester_name || '').trim().toLowerCase() === myName) : [];
  mineList.innerHTML = mine.length ? mine.map(builderCardHtml).join('') : '<p class="builder-empty">Nothing yet — build your first app above!</p>';
  familyList.innerHTML = builds.length ? builds.map(builderCardHtml).join('') : '<p class="builder-empty">No apps built yet.</p>';
  APP_REQUESTS.forEach(r => {{
    if (r.status === 'queued' || r.status === 'generating') pollRequest(r.id);
  }});
}}

async function loadAppRequests() {{
  const r = await fetch('/api/app_requests').then(res => res.json()).catch(() => null);
  if (r && r.requests) APP_REQUESTS = r.requests;
  renderBuilderLists();
}}

function pollRequest(id) {{
  if (builderPolls[id]) return;
  // The giveup clock only starts once a job actually begins generating -- not
  // from when polling starts. A job can legitimately sit "queued" behind the
  // 2-concurrent-generation cap for longer than the giveup window (each slot
  // can run up to GENERATION_TIMEOUT_SEC), and that queue wait must never by
  // itself trigger a false "taking longer than expected" error for a job that
  // hasn't even started yet. Uses the server's own `started` timestamp (not a
  // client-observed one) so elapsed time isn't skewed by the 4s poll cadence.
  let generatingStartedAt = null;
  builderPolls[id] = setInterval(async () => {{
    if (generatingStartedAt && Date.now() - generatingStartedAt > 420000) {{
      clearInterval(builderPolls[id]);
      delete builderPolls[id];
      const idx = APP_REQUESTS.findIndex(r => r.id === id);
      if (idx >= 0) APP_REQUESTS[idx] = Object.assign({{}}, APP_REQUESTS[idx], {{status: 'error', error_message: 'Taking longer than expected — refresh to check.'}});
      renderBuilderLists();
      return;
    }}
    const status = await fetch('/api/app_requests/status/' + id).then(res => res.ok ? res.json() : null).catch(() => null);
    if (!status) return;
    if (status.status === 'generating' && !generatingStartedAt && status.started) {{
      generatingStartedAt = Date.parse(status.started + 'Z');
    }}
    const idx = APP_REQUESTS.findIndex(r => r.id === id);
    if (idx >= 0) APP_REQUESTS[idx] = Object.assign({{}}, APP_REQUESTS[idx], status);
    if (status.status === 'done' || status.status === 'error') {{
      clearInterval(builderPolls[id]);
      delete builderPolls[id];
    }}
    renderBuilderLists();
  }}, 4000);
}}

document.querySelector('.builder-lists')?.addEventListener('click', async (e) => {{
  const reportBtn = e.target.closest('.report-btn');
  if (reportBtn) {{
    const form = document.getElementById('report-form-' + reportBtn.dataset.id);
    if (form) {{
      form.classList.toggle('hidden');
      if (!form.classList.contains('hidden')) form.querySelector('.report-ta').focus();
    }}
    return;
  }}
  const cancelBtn = e.target.closest('.report-cancel-btn');
  if (cancelBtn) {{
    const form = document.getElementById('report-form-' + cancelBtn.dataset.id);
    if (form) {{ form.classList.add('hidden'); form.querySelector('.report-ta').value = ''; }}
    return;
  }}
  const submitBtn = e.target.closest('.report-submit-btn');
  if (submitBtn) {{
    const id = submitBtn.dataset.id;
    const form = document.getElementById('report-form-' + id);
    const ta = form?.querySelector('.report-ta');
    const issue_description = ta?.value.trim() || '';
    if (!issue_description) {{ ta?.focus(); return; }}
    const requester_name = builderNameInput?.value.trim() || '';
    if (!requester_name) {{ builderNameInput?.focus(); return; }}
    const requester_email = builderEmailInput?.value.trim() || '';
    submitBtn.disabled = true; submitBtn.textContent = 'Submitting…';
    const r = await apiPost('/api/app_requests/fix', {{requester_name, requester_email, fix_of: id, issue_description}});
    submitBtn.disabled = false; submitBtn.textContent = 'Submit';
    if (r?.ok) {{
      APP_REQUESTS.unshift({{
        id: r.id, kind: 'fix', fix_of: id, requester_name, issue_description,
        status: 'queued', error_message: null, created: new Date().toISOString(),
        started: null, finished: null,
      }});
      renderBuilderLists();
      pollRequest(r.id);
    }} else {{
      alert(r?.error || 'Could not submit — please try again.');
    }}
  }}
}});
</script>
</body>
</html>"""



def _make_png(size, color1=(124, 110, 230), color2=(230, 110, 124)):
    """Generate a simple gradient PNG icon in pure Python."""
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter byte
        for x in range(size):
            t = (x + y) / (size * 2 - 2)
            r = int(color1[0] + (color2[0] - color1[0]) * t)
            g = int(color1[1] + (color2[1] - color1[1]) * t)
            b = int(color1[2] + (color2[2] - color1[2]) * t)
            row.extend([r, g, b])
        rows.append(bytes(row))

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"".join(rows))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


_ICON_192 = None
_ICON_512 = None

def get_icon(size):
    global _ICON_192, _ICON_512
    if size == 192:
        if _ICON_192 is None:
            _ICON_192 = _make_png(192)
        return _ICON_192
    if _ICON_512 is None:
        _ICON_512 = _make_png(512)
    return _ICON_512


def make_manifest():
    return json.dumps({
        "name": "Cowork Apps",
        "short_name": "CoworkApps",
        "description": "Local app launcher for cowork HTML apps",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0f0f13",
        "theme_color": "#7c6ee6",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]
    }, indent=2)

class AppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APPS_DIR), **kwargs)

    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path in ("/", "/index.html", ""):
            base_url = get_base_url()
            apps = discover_apps()
            reviews = discover_reviews()
            html = generate_index(apps, reviews, base_url)
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif path.startswith("/api/category/"):
            safe_cat = path[len("/api/category/"):]
            apps = discover_apps()
            data = load_data()
            for category, items in apps.items():
                sc = re.sub(r'[^a-z0-9]+', '-', category.lower()).strip('-')
                if sc == safe_cat:
                    icon = CATEGORY_ICONS.get(category, "\U0001f4f1")
                    html = build_category_html(category, safe_cat, icon, items, data)
                    self._json({"html": html})
                    return
            self._json({"error": "not found"}, status=404)
        elif path.startswith("/api/playlist/"):
            playlist_id = path[len("/api/playlist/"):]
            data = load_data()
            playlist = data.get("playlists", {}).get(playlist_id)
            if playlist is None:
                self._json({"error": "not found"}, status=404)
                return
            apps = discover_apps()
            all_apps_map = {a["path"]: a for items in apps.values() for a in items}
            html = build_playlist_html(playlist_id, playlist, all_apps_map, data)
            self._json({"html": html})
        elif path == "/api/removed":
            apps = discover_apps()
            data = load_data()
            removed_set = set(data.get("removed", []))
            favorites = set(data.get("favorites", []))
            ratings = data.get("ratings", {})
            opened = set(data.get("opened", []))
            now = time.time()
            threshold_new = 48 * 3600
            cards = ""
            for category, items in apps.items():
                for app in items:
                    if app["path"] in removed_set:
                        cards += _make_card(app, favorites, ratings, removed_set, opened, now, threshold_new, is_removed=True)
            html = (
                f'<div class="category"><h2 class="category-title">'
                f'&#128465;&#65039; Removed Apps</h2>'
                f'<div class="app-list">{cards}</div></div>'
            ) if cards else ""
            self._json({"html": html})
        elif path == "/api/app_requests":
            data = load_data()
            requests_list = sorted(data.get("app_requests", []), key=lambda r: r.get("created", ""), reverse=True)
            self._json({"requests": [strip_private_fields(r) for r in requests_list]})
        elif path.startswith("/api/app_requests/status/"):
            request_id = path[len("/api/app_requests/status/"):]
            data = load_data()
            req = next((r for r in data.get("app_requests", []) if r.get("id") == request_id), None)
            if req is None:
                self._json({"error": "not found"}, status=404)
                return
            self._json(strip_private_fields(req))
        elif path == "/api/builders":
            data = load_data()
            self._json({"builders": list_builders(data)})
        elif path == "/manifest.json":
            data = make_manifest().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/favicon.ico":
            data = get_icon(192)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        elif path in ("/icon-192.png", "/icon-512.png"):
            size = 192 if "192" in path else 512
            data = get_icon(size)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    def do_POST(self):
        path = unquote(self.path.split("?")[0])
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}
        # Whole request handled under DATA_LOCK: load, decide, mutate, save, and
        # respond all happen atomically w.r.t. every other POST and every
        # background generation thread's update_app_request() calls -- see
        # DATA_LOCK's definition for why a load-once-at-the-top snapshot alone
        # isn't safe once background threads can write concurrently.
        with DATA_LOCK:
            self._handle_post(path, payload)

    def _handle_post(self, path, payload):
        app_path = payload.get("path", "")
        data = load_data()

        if path == "/api/favorite":
            favs = data.setdefault("favorites", [])
            if app_path in favs:
                favs.remove(app_path)
            else:
                favs.append(app_path)
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/rate":
            stars = int(payload.get("stars", 0))
            if stars == 0:
                data.setdefault("ratings", {}).pop(app_path, None)
            else:
                data.setdefault("ratings", {})[app_path] = stars
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/remove":
            removed = data.setdefault("removed", [])
            if app_path in removed:
                removed.remove(app_path)
            else:
                removed.append(app_path)
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/open":
            opened = data.setdefault("opened", [])
            if app_path not in opened:
                opened.append(app_path)
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/notes/add":
            text = payload.get("text", "").strip()
            if text:
                note = {
                    "id": uuid.uuid4().hex[:8],
                    "text": text,
                    "created": now_iso(),
                    "reviewed": False,
                    "ai_response": None,
                    "reviewed_at": None
                }
                data.setdefault("notes", []).append(note)
                save_data(data)
            self._json({"ok": True})

        elif path == "/api/notes/delete":
            nid = payload.get("id", "")
            data["notes"] = [n for n in data.get("notes", []) if n.get("id") != nid]
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/playlist/create":
            name = payload.get("name", "").strip()
            emoji = payload.get("emoji", "📋").strip() or "📋"
            if not name:
                self._json({"ok": False, "error": "name required"}, status=400)
                return
            pid = uuid.uuid4().hex[:8]
            data.setdefault("playlists", {})[pid] = {
                "name": name,
                "emoji": emoji,
                "apps": [],
                "created": now_iso(),
            }
            save_data(data)
            self._json({"ok": True, "id": pid})

        elif path == "/api/playlist/toggle":
            pid = payload.get("playlist_id", "")
            app_path = payload.get("path", "")
            playlists = data.setdefault("playlists", {})
            playlist = playlists.get(pid)
            if playlist is None:
                self._json({"ok": False, "error": "playlist not found"}, status=404)
                return
            apps_list = playlist.setdefault("apps", [])
            if app_path in apps_list:
                apps_list.remove(app_path)
                in_playlist = False
            else:
                apps_list.append(app_path)
                in_playlist = True
            save_data(data)
            self._json({"ok": True, "in_playlist": in_playlist})

        elif path == "/api/playlist/delete":
            pid = payload.get("playlist_id", "")
            playlists = data.setdefault("playlists", {})
            playlists.pop(pid, None)
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/playlist/rename":
            pid = payload.get("playlist_id", "")
            name = payload.get("name", "").strip()
            emoji = payload.get("emoji", "").strip()
            playlist = data.get("playlists", {}).get(pid)
            if playlist is None:
                self._json({"ok": False, "error": "not found"}, status=404)
                return
            if name:
                playlist["name"] = name
            if emoji:
                playlist["emoji"] = emoji
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/app_requests/create":
            requester_name = (payload.get("requester_name") or "").strip()[:30]
            requester_email = (payload.get("requester_email") or "").strip()[:100]
            if requester_email and not EMAIL_RE.match(requester_email):
                requester_email = ""
            mode = payload.get("mode") or "basic"
            criteria = payload.get("criteria") or {}
            if mode not in ("basic", "advanced"):
                self._json({"ok": False, "error": "invalid mode"}, status=400)
                return
            if not requester_name:
                self._json({"ok": False, "error": "missing required field: requester_name"}, status=400)
                return
            for field in ("app_type", "theme", "difficulty", "color_vibe", "idea"):
                if not str(criteria.get(field, "")).strip():
                    self._json({"ok": False, "error": f"missing required field: {field}"}, status=400)
                    return

            clean_criteria = {
                "app_type": str(criteria["app_type"]).strip()[:40],
                "theme": str(criteria["theme"]).strip()[:60],
                "difficulty": str(criteria["difficulty"]).strip()[:20],
                "color_vibe": str(criteria["color_vibe"]).strip()[:40],
                "idea": str(criteria["idea"]).strip()[:200],
            }
            if mode == "advanced":
                mechanics = criteria.get("mechanics") or []
                if isinstance(mechanics, list):
                    clean_criteria["mechanics"] = [str(m).strip()[:40] for m in mechanics][:10]
                if criteria.get("age_range"):
                    clean_criteria["age_range"] = str(criteria["age_range"]).strip()[:20]
                if criteria.get("tech_requests"):
                    clean_criteria["tech_requests"] = str(criteria["tech_requests"]).strip()[:300]
                if criteria.get("inspired_by"):
                    clean_criteria["inspired_by"] = str(criteria["inspired_by"]).strip()[:100]

            request_id = uuid.uuid4().hex[:8]
            target_filename = compute_target_filename(clean_criteria, data)
            remember_builder(data, requester_name, requester_email)
            record = {
                "id": request_id,
                "kind": "build",
                "requester_name": requester_name,
                "requester_email": requester_email,
                "mode": mode,
                "criteria": clean_criteria,
                "target_filename": target_filename,
                "target_path": f"custom_apps/{target_filename}",
                "status": "queued",
                "error_message": None,
                "created": now_iso(),
                "started": None,
                "finished": None,
                "log_tail": "",
            }
            data.setdefault("app_requests", []).append(record)
            save_data(data)
            threading.Thread(target=generate_app_worker, args=(request_id,), daemon=True).start()
            self._json({"ok": True, "id": request_id, "target_filename": target_filename})

        elif path == "/api/app_requests/fix":
            requester_name = (payload.get("requester_name") or "").strip()[:30]
            requester_email = (payload.get("requester_email") or "").strip()[:100]
            if requester_email and not EMAIL_RE.match(requester_email):
                requester_email = ""
            fix_of = (payload.get("fix_of") or "").strip()
            issue_description = (payload.get("issue_description") or "").strip()[:500]
            if not requester_name:
                self._json({"ok": False, "error": "missing required field: requester_name"}, status=400)
                return
            if not issue_description:
                self._json({"ok": False, "error": "missing required field: issue_description"}, status=400)
                return
            original = next((r for r in data.get("app_requests", []) if r.get("id") == fix_of), None)
            if original is None or original.get("status") != "done":
                self._json({"ok": False, "error": "original app not found or not ready"}, status=404)
                return

            request_id = uuid.uuid4().hex[:8]
            remember_builder(data, requester_name, requester_email)
            record = {
                "id": request_id,
                "kind": "fix",
                "fix_of": fix_of,
                "requester_name": requester_name,
                "issue_description": issue_description,
                "target_filename": original["target_filename"],
                "target_path": original["target_path"],
                "status": "queued",
                "error_message": None,
                "created": now_iso(),
                "started": None,
                "finished": None,
                "log_tail": "",
            }
            data.setdefault("app_requests", []).append(record)
            save_data(data)
            threading.Thread(target=generate_app_worker, args=(request_id,), daemon=True).start()
            self._json({"ok": True, "id": request_id})

        else:
            self._json({"ok": False, "error": "unknown endpoint"}, status=404)

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} -- {fmt % args}")


def main():
    import sys
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ip = get_local_ip()
    apps = discover_apps()
    count = sum(len(v) for v in apps.values())

    # Bind the port FIRST, with allow_reuse_address left at its default False.
    # Deliberately NOT setting allow_reuse_address = True here: on Windows,
    # SO_REUSEADDR lets a second process silently bind the same port while the
    # first is still live (routing between them becomes "indeterminate" per
    # Microsoft's own Winsock docs) instead of raising an error -- exactly the
    # wrong behavior for the "only one true server" invariant the crash-recovery
    # sweep below depends on. Plain socketserver.ThreadingTCPServer's default
    # (exclusive bind) is what makes a losing contender fail cleanly with
    # OSError instead of silently sharing the port with two servers racing to
    # handle the same requests.
    try:
        httpd = socketserver.ThreadingTCPServer(("0.0.0.0", PORT), AppHandler)
    except OSError as e:
        print(f"Could not bind port {PORT}: {e}")
        print("Another server instance is likely already running. Exiting without changes.")
        sys.exit(1)

    # Crash recovery: a killed subprocess can't be resumed, so any app_request
    # still "generating" from a previous run is stuck forever -- surface it as an
    # error. Safe to run now: we hold the port, so we are the one true server.
    data = load_data()
    interrupted = 0
    for req in data.get("app_requests", []):
        if req.get("status") == "generating":
            req["status"] = "error"
            req["error_message"] = "Interrupted by server restart -- please resubmit."
            req["finished"] = now_iso()
            interrupted += 1
    if interrupted:
        save_data(data)
        print(f"[builder] marked {interrupted} interrupted app_request(s) as error on startup")

    print(f"""
+----------------------------------------------+
|          Cowork Apps Local Server            |
+----------------------------------------------+
|  Apps found : {count:<30} |
|  Local URL  : http://localhost:{PORT:<14} |
|  Network URL: http://{ip}:{PORT:<14} |
+----------------------------------------------+

  >> Open on your phone/tablet: http://{ip}:{PORT}
  >> Index auto-updates when new apps are added
  >> Press Ctrl+C to stop
""")

    with httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")


if __name__ == "__main__":
    main()
