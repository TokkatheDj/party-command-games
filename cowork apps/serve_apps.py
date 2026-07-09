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

from applock import data_lock

APPS_DIR = Path(__file__).parent
PORT = 8080
DATA_FILE = APPS_DIR / ".app_data.json"
CUSTOM_APPS_DIR = APPS_DIR / "custom_apps"
EMAIL_CONFIG_FILE = APPS_DIR / "email_config.json"
MAX_CONCURRENT_GENERATIONS = 2
GENERATION_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_GENERATIONS)
GENERATION_TIMEOUT_SEC = 600
NOTE_REVIEW_SEMAPHORE = threading.Semaphore(2)
NOTE_REVIEW_TIMEOUT_SEC = 120
# JSON payloads here are tiny (a few KB at most given per-field length caps);
# cap the request body so a bogus/huge Content-Length can't drive a large read.
MAX_POST_BODY = 256 * 1024
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

# discover_apps() runs on every "/" load and several /api/* hits; a full rglob
# + per-file stat over a OneDrive-backed tree dominates page-load latency. Cache
# the result for a few seconds so one interaction's burst of requests shares a
# single scan. New/edited apps still surface within the TTL on the next refresh.
_APPS_CACHE = {"at": 0.0, "apps": None}
_APPS_CACHE_LOCK = threading.Lock()
_APPS_CACHE_TTL = 5.0


def discover_apps():
    now = time.time()
    with _APPS_CACHE_LOCK:
        cached = _APPS_CACHE["apps"]
        if cached is not None and (now - _APPS_CACHE["at"]) < _APPS_CACHE_TTL:
            return cached
    apps = _discover_apps_uncached()
    with _APPS_CACHE_LOCK:
        _APPS_CACHE["apps"] = apps
        _APPS_CACHE["at"] = time.time()
    return apps


def _discover_apps_uncached():
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
FEEDBACK_RATINGS = {"love", "like", "meh", "dislike"}


def strip_private_fields(request_record):
    """Drop fields from an app_request record that shouldn't leave the server:
    log_tail (debug-only subprocess output) and requester_email (only needed
    server-side to send the build-finished notification, not for card display).
    has_email tells the client whether a notification will fire, without ever
    exposing the actual address."""
    stripped = {k: v for k, v in request_record.items() if k not in ("log_tail", "requester_email")}
    stripped["has_email"] = bool(request_record.get("requester_email"))
    return stripped


def remember_builder(data, name, email):
    """Track name -> email so the name dropdown can offer returning guests
    their name (and re-use their email for build notifications) without
    asking them to retype it every time.

    A blank email always clears whatever was stored (an explicit opt-out --
    otherwise there'd be no way to stop being auto-filled/notified). A
    non-blank email is only stored the *first* time it's seen for a given
    name; it does not silently overwrite an existing different email.
    Display names aren't unique identities here (no auth), so without this,
    two different people who happen to submit under the same name (or a
    generic name like "Dad") would clobber each other's stored email and
    the dropdown would start auto-filling -- and notifying -- the wrong
    person."""
    builders = data.setdefault("builders", {})
    if not email:
        builders[name] = ""
    elif not builders.get(name):
        builders[name] = email


def list_builders(data):
    return sorted(
        ({"name": name, "email": email} for name, email in data.get("builders", {}).items() if name),
        key=lambda b: b["name"].lower(),
    )


# Light/dark theme: shared CSS custom-property values, the anti-flash init
# script (must run before first paint, so it's inlined as the first thing in
# <head>), and the toggle button + its wiring JS. Used by both generate_index()
# and generate_builder_page() so there's one definition of "what dark mode
# looks like" instead of two that can drift.
THEME_ROOT_VARS = """
  :root {
    --bg: #f5f5fa;
    --surface: #ffffff;
    --border: #dcdce6;
    --accent: #6d5ce0;
    --accent2: #d1495c;
    --text: #1c1c26;
    --muted: #62626f;
    --card-hover: #eeeef6;
  }
  :root[data-theme="dark"] {
    --bg: #0f0f13;
    --surface: #2a1f4d;
    --border: #3d2e6b;
    --accent: #7c6ee6;
    --accent2: #e66e7c;
    --text: #e8e8f0;
    --muted: #a99ce0;
    --card-hover: #352763;
  }
"""

THEME_INIT_SCRIPT = """<script>
(function(){var t=localStorage.getItem('appverse-theme');if(t==='dark')document.documentElement.setAttribute('data-theme','dark');})();
</script>"""

THEME_TOGGLE_HTML = '<button id="theme-toggle-btn" class="theme-toggle-btn" type="button" aria-label="Toggle dark mode">&#127769;</button>'

THEME_TOGGLE_JS = """
// ---- Theme toggle ----
const themeToggleBtn = document.getElementById('theme-toggle-btn');
function updateThemeToggleIcon() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (themeToggleBtn) themeToggleBtn.textContent = isDark ? '☀️' : '🌙';
}
updateThemeToggleIcon();
themeToggleBtn?.addEventListener('click', () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('appverse-theme', 'light');
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('appverse-theme', 'dark');
  }
  updateThemeToggleIcon();
});
"""


# Builder widget: shared CSS/HTML/JS used by both the "Build" tab inside the
# main SPA (generate_index) and the standalone /build page (generate_builder_page),
# so there's exactly one copy of the form/list markup and card-rendering logic
# to maintain instead of two that can drift.
BUILDER_STYLES = """
/* ---- Theme toggle ---- */
.theme-toggle-btn { position: fixed; top: 0.7rem; right: 0.8rem; z-index: 50; background: rgba(20,20,30,0.55); border: 1px solid rgba(255,255,255,0.25); color: #fff; border-radius: 8px; width: 2.2rem; height: 2.2rem; font-size: 1.1rem; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.15s; }
.theme-toggle-btn:hover { background: rgba(20,20,30,0.75); }
/* ---- App Builder ---- */
#tab-builder { display: none; padding: 1.5rem; max-width: 700px; margin: 0 auto; }
.builder-form { background: var(--surface); border: 1px solid var(--accent); border-radius: 10px; padding: 1rem; margin-bottom: 1.2rem; }
.builder-form label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; display: block; margin: 0.75rem 0 0.4rem; }
.builder-form label:first-child { margin-top: 0; }
#builder-name-input, #builder-theme-input, #builder-inspired-input, #builder-name-select, #builder-email-input { width: 100%; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.95rem; outline: none; font-family: inherit; transition: border-color 0.2s; }
#builder-name-input:focus, #builder-theme-input:focus, #builder-inspired-input:focus, #builder-name-select:focus, #builder-email-input:focus { border-color: var(--accent); }
#builder-name-select { margin-bottom: 0.5rem; }
.builder-optional { text-transform: none; letter-spacing: normal; font-weight: 400; opacity: 0.75; }
#builder-idea-input, #builder-tech-input { width: 100%; min-height: 60px; padding: 0.6rem 0.85rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.95rem; outline: none; font-family: inherit; resize: vertical; transition: border-color 0.2s; }
#builder-idea-input:focus, #builder-tech-input:focus { border-color: var(--accent); }
.builder-select { width: 100%; margin-bottom: 0.5rem; min-height: 44px; padding: 0.5rem 0.85rem; border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; font-family: inherit; outline: none; border: 1px solid var(--accent); color: var(--accent); background: rgba(124,110,230,0.1); transition: border-color 0.15s; }
.choice-group { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.choice-opt { font-size: 0.85rem; color: var(--text); cursor: pointer; border-radius: 7px; padding: 0.4rem 0.75rem; border: 2px solid var(--border); transition: border-color 0.12s, background 0.12s; min-height: 44px; display: inline-flex; align-items: center; }
.choice-opt.selected { border-color: var(--accent); background: rgba(124,110,230,0.12); color: var(--accent); }
.choice-checkboxes { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.choice-checkbox { display: flex; align-items: center; gap: 0.35rem; font-size: 0.83rem; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 7px; padding: 0.35rem 0.6rem; cursor: pointer; min-height: 44px; }
.choice-checkbox input { accent-color: var(--accent); }
#builder-advanced-fields.hidden { display: none; }
.idea-chips { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
.idea-chip { font-size: 0.8rem; }
.builder-share { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.85rem 1rem; margin-bottom: 1.2rem; }
.builder-share label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; display: block; margin-bottom: 0.5rem; }
.builder-share-row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
#builder-share-link { flex: 1; min-width: 140px; padding: 0.5rem 0.7rem; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 0.82rem; outline: none; font-family: inherit; }
.builder-copy-btn, .builder-share-btn { background: var(--accent); border: none; border-radius: 8px; color: #fff; font-size: 0.82rem; font-weight: 600; padding: 0.5rem 0.85rem; cursor: pointer; transition: opacity 0.15s; white-space: nowrap; }
.builder-copy-btn:hover, .builder-share-btn:hover { opacity: 0.85; }
.builder-share-copied { display: inline-block; margin-top: 0.4rem; font-size: 0.78rem; color: #44ee66; }
.builder-print-link { display: block; margin-top: 0.6rem; font-size: 0.8rem; color: var(--accent); text-decoration: none; }
.builder-print-link:hover { text-decoration: underline; }
.builder-lists { margin-top: 1.5rem; }
.builder-list-heading { font-size: 0.85rem; font-weight: 600; color: var(--text); margin: 1.2rem 0 0.6rem; }
.builder-card-list { display: flex; flex-direction: column; gap: 0.6rem; }
.builder-empty { color: var(--muted); font-style: italic; font-size: 0.88rem; }
.builder-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem 0.9rem; }
.builder-card-highlight { outline: 2px solid var(--accent); outline-offset: 2px; }
.builder-next-steps { margin-top: 0.4rem; font-size: 0.8rem; color: var(--muted); line-height: 1.4; }
.builder-card-header { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.3rem; }
.builder-card-title { font-size: 0.9rem; color: var(--text); font-weight: 600; }
.builder-card-meta { font-size: 0.75rem; color: var(--muted); }
.builder-badge { font-size: 0.68rem; font-weight: 700; padding: 0.15em 0.55em; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.03em; flex-shrink: 0; }
.builder-badge.queued { background: rgba(136,136,153,0.15); color: var(--muted); }
.builder-badge.generating { background: rgba(124,110,230,0.15); color: var(--accent); }
.builder-badge.done { background: rgba(68,238,102,0.12); color: #44ee66; }
.builder-badge.error { background: rgba(230,110,124,0.15); color: var(--accent2); }
.builder-card-open { display: inline-block; margin-top: 0.4rem; margin-right: 0.6rem; font-size: 0.83rem; color: var(--accent); text-decoration: none; font-weight: 600; }
.builder-card-open:hover { text-decoration: underline; }
.builder-card-error { margin-top: 0.4rem; font-size: 0.82rem; color: var(--accent2); }
.report-btn { display: inline-block; margin-top: 0.4rem; font-size: 0.78rem; color: var(--muted); background: none; border: 1px solid var(--border); border-radius: 6px; padding: 0.25rem 0.6rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
.report-btn:hover { color: var(--accent2); border-color: var(--accent2); }
.dismiss-btn { display: inline-block; margin-top: 0.4rem; margin-right: 0.4rem; font-size: 0.78rem; color: var(--accent2); background: none; border: 1px solid var(--accent2); border-radius: 6px; padding: 0.25rem 0.6rem; cursor: pointer; transition: opacity 0.15s; }
.dismiss-btn:hover { opacity: 0.8; }
.report-form { margin-top: 0.5rem; }
.report-ta { width: 100%; min-height: 50px; padding: 0.5rem 0.7rem; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 0.85rem; resize: vertical; outline: none; font-family: inherit; line-height: 1.4; transition: border-color 0.2s; }
.report-ta:focus { border-color: var(--accent2); }
.fix-status { margin-top: 0.4rem; font-size: 0.8rem; color: var(--muted); font-style: italic; }
.fix-status-done { color: #44ee66; font-style: normal; }
.fix-status-error { color: var(--accent2); font-style: normal; }
.feedback-btn { display: inline-block; margin-top: 0.4rem; margin-right: 0.4rem; font-size: 0.78rem; color: var(--accent); background: none; border: 1px solid var(--accent); border-radius: 6px; padding: 0.25rem 0.6rem; cursor: pointer; transition: opacity 0.15s; }
.feedback-btn:hover { opacity: 0.8; }
.feedback-form { margin-top: 0.5rem; }
.feedback-emoji-row { display: flex; gap: 0.5rem; margin-top: 0.4rem; }
.feedback-emoji-opt { font-size: 1.4rem; min-width: 44px; min-height: 44px; border: 2px solid var(--border); border-radius: 8px; background: var(--bg); cursor: pointer; transition: border-color 0.12s; }
.feedback-emoji-opt:hover { border-color: var(--accent); }
.feedback-given { margin-top: 0.4rem; font-size: 0.8rem; color: var(--muted); font-style: italic; }
.feedback-comment-text { margin-top: 0.3rem; font-size: 0.83rem; color: var(--text); font-style: italic; line-height: 1.4; }
.feedback-comment-btn { background: none; border: none; color: var(--accent); font-size: 0.78rem; cursor: pointer; text-decoration: underline; padding: 0; }
.feedback-comment-form { margin-top: 0.4rem; }
.feedback-comment-ta { width: 100%; min-height: 50px; padding: 0.5rem 0.7rem; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text); font-size: 0.85rem; resize: vertical; outline: none; font-family: inherit; line-height: 1.4; transition: border-color 0.2s; }
.feedback-comment-ta:focus { border-color: var(--accent); }
.feedback-popup { position: fixed; left: 0.75rem; right: 0.75rem; bottom: 0.75rem; z-index: 60; background: var(--surface); border: 1px solid var(--accent); border-radius: 12px; padding: 0.85rem 1rem; box-shadow: 0 4px 18px rgba(0,0,0,0.25); max-width: 420px; margin: 0 auto; }
.feedback-popup-text { font-size: 0.88rem; color: var(--text); font-weight: 600; margin-bottom: 0.3rem; }
.feedback-popup-close { display: block; margin-top: 0.5rem; background: none; border: none; color: var(--muted); font-size: 0.78rem; cursor: pointer; padding: 0.3rem 0; }
.standalone-wrap { max-width: 700px; margin: 0 auto; padding: 1.5rem; }
.standalone-header { text-align: center; margin-bottom: 1.2rem; }
.standalone-header h1 { font-size: 1.4rem; font-weight: 700; background: linear-gradient(90deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 0.3rem; }
.standalone-header p { color: var(--muted); font-size: 0.85rem; }
.standalone-footer { text-align: center; margin-top: 1.5rem; }
.standalone-footer a { color: var(--accent); font-size: 0.85rem; text-decoration: none; }
.standalone-footer a:hover { text-decoration: underline; }
"""

BUILDER_FORM_HTML = """  <div class="builder-form">
    <label>Your name</label>
    <select id="builder-name-select">
      <option value="">&#10133; New name&hellip;</option>
    </select>
    <input id="builder-name-input" type="text" placeholder="e.g. Emma" autocomplete="off" maxlength="30">

    <label>Email <span class="builder-optional">(so we can tell you when it's ready)</span></label>
    <input id="builder-email-input" type="email" placeholder="you@example.com" autocomplete="off" maxlength="100">

    <select class="builder-select" id="builder-mode-select">
      <option value="basic" selected>Basic</option>
      <option value="advanced">Advanced</option>
    </select>

    <label>App type</label>
    <select class="builder-select" id="builder-app-type" data-field="app_type">
      <option value="Arcade Game" selected>&#127918; Arcade Game</option>
      <option value="Puzzle">&#129513; Puzzle</option>
      <option value="Quiz">&#10067; Quiz</option>
      <option value="Story">&#128214; Story</option>
      <option value="Tool">&#128295; Tool</option>
      <option value="Arts/Crafts">&#127912; Arts/Crafts</option>
      <option value="Music">&#127925; Music</option>
      <option value="Sports">&#127941; Sports</option>
      <option value="Card Game">&#127183; Card Game</option>
      <option value="Interactive Game">&#127939; Interactive Game</option>
      <option value="Cooking">&#127859; Cooking</option>
      <option value="Party Game">&#127881; Party Game</option>
    </select>

    <label>Theme</label>
    <select class="builder-select" id="builder-color-vibe" data-field="color_vibe">
      <option value="Bright &amp; Playful" selected>&#127752; Bright &amp; Playful</option>
      <option value="Cool &amp; Calm">&#128167; Cool &amp; Calm</option>
      <option value="Dark &amp; Mysterious">&#127769; Dark &amp; Mysterious</option>
      <option value="Neon &amp; Energetic">&#9889; Neon &amp; Energetic</option>
      <option value="Pastel &amp; Soft">&#127800; Pastel &amp; Soft</option>
      <option value="Retro &amp; Nostalgic">&#128252; Retro &amp; Nostalgic</option>
      <option value="Nature &amp; Earthy">&#127811; Nature &amp; Earthy</option>
      <option value="Elegant &amp; Minimal">&#10024; Elegant &amp; Minimal</option>
      <option value="Spooky &amp; Fun">&#127875; Spooky &amp; Fun</option>
    </select>
    <label>Subject <span class="builder-optional">(optional)</span></label>
    <input id="builder-theme-input" type="text" placeholder="e.g. dinosaurs, space pirates" autocomplete="off" maxlength="60">

    <label>Age range</label>
    <select class="builder-select" id="builder-age-range" data-field="age_range">
      <option value="Under 6">&#128118; Under 6</option>
      <option value="6-9">&#129490; 6-9</option>
      <option value="10-13">&#127890; 10-13</option>
      <option value="14-17">&#127911; 14-17</option>
      <option value="18+">&#129489; 18+</option>
      <option value="All ages" selected>&#128106; All ages</option>
    </select>

    <label>Your idea (one line)</label>
    <div class="idea-chips" id="builder-idea-chips"></div>
    <textarea id="builder-idea-input" placeholder="e.g. A maze game where you're a dragon collecting gems" maxlength="200"></textarea>

    <div id="builder-advanced-fields" class="hidden">
      <label>Difficulty</label>
      <div class="choice-group" id="builder-difficulty" data-field="difficulty">
        <span class="choice-opt selected" data-value="Easy">&#128994; Easy</span>
        <span class="choice-opt" data-value="Medium">&#128993; Medium</span>
        <span class="choice-opt" data-value="Hard">&#128308; Hard</span>
      </div>

      <label>Mechanics (pick any)</label>
      <div class="choice-checkboxes" id="builder-mechanics">
        <label class="choice-checkbox"><input type="checkbox" value="Timer/Countdown"> &#9201;&#65039; Timer/Countdown</label>
        <label class="choice-checkbox"><input type="checkbox" value="Score/Points"> &#127919; Score/Points</label>
        <label class="choice-checkbox"><input type="checkbox" value="Levels"> &#129692; Levels</label>
        <label class="choice-checkbox"><input type="checkbox" value="Local multiplayer"> &#128101; Local multiplayer</label>
        <label class="choice-checkbox"><input type="checkbox" value="Sound effects"> &#128266; Sound effects</label>
        <label class="choice-checkbox"><input type="checkbox" value="Drag &amp; drop"> &#9995; Drag &amp; drop</label>
        <label class="choice-checkbox"><input type="checkbox" value="Keyboard controls"> &#9000;&#65039; Keyboard controls</label>
        <label class="choice-checkbox"><input type="checkbox" value="Touch/swipe"> &#128070; Touch/swipe</label>
        <label class="choice-checkbox"><input type="checkbox" value="Randomized"> &#127922; Randomized</label>
        <label class="choice-checkbox"><input type="checkbox" value="Save progress"> &#128190; Save progress</label>
      </div>

      <label>Anything specific? (optional)</label>
      <textarea id="builder-tech-input" placeholder="e.g. a leaderboard of best times" maxlength="300"></textarea>

      <label>Make it feel like&hellip; (optional)</label>
      <input id="builder-inspired-input" type="text" placeholder="e.g. Flappy Bird" autocomplete="off" maxlength="100">
    </div>

    <div class="pl-form-actions">
      <button class="pl-create-btn" id="builder-submit-btn">Build My App!</button>
    </div>
  </div>"""

BUILDER_LISTS_HTML = """  <div class="builder-lists">
    <h2 class="builder-list-heading">Your Creations</h2>
    <div id="builder-mine-list" class="builder-card-list"></div>
    <h2 class="builder-list-heading">Family Creations</h2>
    <div id="builder-family-list" class="builder-card-list"></div>
  </div>"""

SHARED_JS_HELPERS = """
async function apiPost(endpoint, body) {
  try {
    const r = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    return await r.json();
  } catch(e) {
    console.error(endpoint, e);
    return null;
  }
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
"""


BUILD_PRINT_OPTIONS = {
    "App type": [
        ("Arcade Game", "&#127918;"), ("Puzzle", "&#129513;"), ("Quiz", "&#10067;"),
        ("Story", "&#128214;"), ("Tool", "&#128295;"), ("Arts/Crafts", "&#127912;"),
        ("Music", "&#127925;"), ("Sports", "&#127941;"), ("Card Game", "&#127183;"),
        ("Interactive Game", "&#127939;"), ("Cooking", "&#127859;"), ("Party Game", "&#127881;"),
    ],
    "Theme": [
        ("Bright &amp; Playful", "&#127752;"), ("Cool &amp; Calm", "&#128167;"), ("Dark &amp; Mysterious", "&#127769;"),
        ("Neon &amp; Energetic", "&#9889;"), ("Pastel &amp; Soft", "&#127800;"), ("Retro &amp; Nostalgic", "&#128252;"),
        ("Nature &amp; Earthy", "&#127811;"), ("Elegant &amp; Minimal", "&#10024;"), ("Spooky &amp; Fun", "&#127875;"),
    ],
    "Age range": [
        ("Under 6", "&#128118;"), ("6-9", "&#129490;"), ("10-13", "&#127890;"),
        ("14-17", "&#127911;"), ("18+", "&#129489;"), ("All ages", "&#128106;"),
    ],
    "Difficulty": [
        ("Easy", "&#128994;"), ("Medium", "&#128993;"), ("Hard", "&#128308;"),
    ],
    "Mechanics (pick any)": [
        ("Timer/Countdown", "&#9201;&#65039;"), ("Score/Points", "&#127919;"), ("Levels", "&#129692;"),
        ("Local multiplayer", "&#128101;"), ("Sound effects", "&#128266;"), ("Drag &amp; drop", "&#9995;"),
        ("Keyboard controls", "&#9000;&#65039;"), ("Touch/swipe", "&#128070;"), ("Randomized", "&#127922;"),
        ("Save progress", "&#128190;"),
    ],
}


def print_bubble_grid(label, multi=False):
    """Renders one BUILD_PRINT_OPTIONS field as a grid of paper 'bubbles' --
    circles for single-pick fields, checkbox squares for multi-pick (Mechanics)
    -- each with the same emoji+label pairing already used in the live
    dropdowns/checkboxes, so someone filling this out on paper sees exactly the
    same options as the digital form."""
    mark = "&#9723;" if multi else "&#9675;"
    items = "".join(
        f'<div class="print-bubble"><span class="print-mark">{mark}</span> {emoji} {name}</div>'
        for name, emoji in BUILD_PRINT_OPTIONS[label]
    )
    return f'<div class="print-field"><div class="print-label">{label}</div><div class="print-bubble-grid">{items}</div></div>'


BUILD_PRINT_STYLES = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1a1a1a; background: #fff; max-width: 780px; margin: 0 auto; padding: 1.5rem; }
  .print-toolbar { text-align: center; margin-bottom: 1.2rem; }
  .print-btn { background: #7c6ee6; color: #fff; border: none; border-radius: 8px; padding: 0.7rem 1.4rem; font-size: 1rem; font-weight: 600; cursor: pointer; }
  .print-header { text-align: center; margin-bottom: 1.2rem; }
  .print-header h1 { font-size: 1.5rem; margin-bottom: 0.3rem; }
  .print-instructions { background: #f3f1ff; border: 1px solid #ddd6ff; border-radius: 10px; padding: 0.9rem 1.1rem; font-size: 0.92rem; line-height: 1.5; margin-bottom: 1.4rem; }
  .print-instructions strong { color: #5b4dc2; }
  .print-section-title { font-size: 1.1rem; font-weight: 700; margin: 1.6rem 0 0.9rem; padding-bottom: 0.3rem; border-bottom: 2px solid #1a1a1a; }
  .print-section-title.advanced { color: #555; }
  .print-advanced-note { font-size: 0.85rem; color: #555; font-style: italic; margin-bottom: 0.8rem; }
  .print-field { margin-bottom: 1.1rem; }
  .print-label { font-weight: 700; font-size: 0.92rem; margin-bottom: 0.4rem; }
  .print-bubble-grid { display: flex; flex-wrap: wrap; gap: 0.5rem 1.1rem; }
  .print-bubble { font-size: 0.92rem; white-space: nowrap; }
  .print-mark { font-size: 1.1rem; }
  .print-line { border-bottom: 1px solid #999; height: 1.6rem; margin-top: 0.2rem; }
  .print-lines-3 .print-line { margin-bottom: 0.5rem; }
  .print-footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ccc; text-align: center; font-size: 0.85rem; color: #555; }
  .print-footer .url { font-weight: 700; color: #5b4dc2; }
  @media print {
    .print-toolbar { display: none; }
    body { padding: 0.3in; }
    .print-section-title { break-after: avoid; }
    .print-field { break-inside: avoid; }
  }
"""


def generate_build_print_page(share_url):
    """Paper version of the Build wizard for someone without easy phone/computer
    access at the moment -- fill it out with a pencil, then have someone type
    the answers into the real form at share_url to actually kick off the build
    (this page has no submit capability of its own, it's pure static HTML)."""
    idea_lines = "".join('<div class="print-line"></div>' for _ in range(3))
    tech_lines = "".join('<div class="print-line"></div>' for _ in range(2))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Build Your Own App &mdash; Printable Form</title>
<style>
{BUILD_PRINT_STYLES}
</style>
</head>
<body>
  <div class="print-toolbar">
    <button class="print-btn" type="button" onclick="window.print()">&#128424; Print this page</button>
  </div>
  <div class="print-header">
    <h1>&#128736; Build Your Own App</h1>
  </div>
  <div class="print-instructions">
    Fill this out with a pencil &mdash; circle or check the bubbles you want, and write on the blank lines.
    Then go to <strong>{share_url}</strong> on a phone or computer and enter your answers there to actually
    build the app.
  </div>

  <div class="print-section-title">Basic</div>

  <div class="print-field">
    <div class="print-label">Your name</div>
    <div class="print-line"></div>
  </div>
  <div class="print-field">
    <div class="print-label">Email <span style="font-weight:400;">(so we can tell you when it's ready)</span></div>
    <div class="print-line"></div>
  </div>
  {print_bubble_grid("App type")}
  {print_bubble_grid("Theme")}
  <div class="print-field">
    <div class="print-label">Subject <span style="font-weight:400;">(optional &mdash; e.g. dinosaurs, space pirates)</span></div>
    <div class="print-line"></div>
  </div>
  {print_bubble_grid("Age range")}
  <div class="print-field">
    <div class="print-label">Your idea <span style="font-weight:400;">(one or two sentences)</span></div>
    <div class="print-lines-3">{idea_lines}</div>
  </div>

  <div class="print-section-title advanced">Advanced <span style="font-weight:400;">(optional &mdash; skip if Basic is enough)</span></div>
  <div class="print-advanced-note">Only fill this out if you want more control over how the app turns out.</div>

  {print_bubble_grid("Difficulty")}
  {print_bubble_grid("Mechanics (pick any)", multi=True)}
  <div class="print-field">
    <div class="print-label">Anything specific? <span style="font-weight:400;">(optional &mdash; e.g. a leaderboard of best times)</span></div>
    <div class="print-lines-3">{tech_lines}</div>
  </div>
  <div class="print-field">
    <div class="print-label">Make it feel like&hellip; <span style="font-weight:400;">(optional &mdash; e.g. Flappy Bird)</span></div>
    <div class="print-line"></div>
  </div>

  <div class="print-footer">
    Enter these answers at<br><span class="url">{share_url}</span>
  </div>
</body>
</html>"""


def builder_share_row_html(share_url):
    return f"""  <div class="builder-share">
    <label>Share this form</label>
    <div class="builder-share-row">
      <input id="builder-share-link" type="text" readonly value="{share_url}">
      <button class="builder-copy-btn" id="builder-copy-btn" type="button">&#128203; Copy Link</button>
      <button class="builder-share-btn hidden" id="builder-native-share-btn" type="button">&#128228; Share&hellip;</button>
    </div>
    <span class="builder-share-copied hidden" id="builder-share-copied">Copied!</span>
    <a class="builder-print-link" href="/build/print" target="_blank">&#128424; Prefer paper? Print a blank form</a>
  </div>"""


def builder_logic_js(app_requests_json, builders_json, share_url):
    """Data seed + all interaction logic for the builder widget (name/email sync,
    mode toggle, choice-groups, submit, card rendering, polling, dismiss/report,
    idea-starter chips, and the share-link widget). Called from both generate_index()
    (embedded in the Build tab's own <script>, which already defines apiPost/escHtml)
    and generate_builder_page() (the standalone page, which includes SHARED_JS_HELPERS
    first) -- identical behavior either way since it drives the same DOM element IDs."""
    share_url_json = json.dumps(share_url)
    return f"""
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

function showNameControl(which) {{
  if (!builderNameSelect || !builderNameInput) return;
  builderNameSelect.classList.toggle('hidden', which !== 'select');
  builderNameInput.classList.toggle('hidden', which !== 'input');
  if (which === 'input') builderNameInput.focus();
}}

if (builderNameSelect) {{
  for (const b of BUILDERS) {{
    const opt = document.createElement('option');
    opt.value = b.name;
    opt.textContent = b.name;
    builderNameSelect.appendChild(opt);
  }}
  builderNameSelect.addEventListener('change', () => {{
    if (!builderNameSelect.value) {{
      // "New name..." chosen -- hand off to the text input, on the same line,
      // ready to type, instead of showing both controls at once.
      builderNameInput.value = '';
      if (builderEmailInput) builderEmailInput.value = '';
      localStorage.removeItem('cowork-builder-name');
      localStorage.removeItem('cowork-builder-email');
      showNameControl('input');
      return;
    }}
    builderNameInput.value = builderNameSelect.value;
    builderEmailInput.value = builderEmailFor(builderNameSelect.value);
    localStorage.setItem('cowork-builder-name', builderNameInput.value);
    localStorage.setItem('cowork-builder-email', builderEmailInput.value);
  }});
}}
if (builderNameInput) {{
  builderNameInput.value = localStorage.getItem('cowork-builder-name') || '';
  const knownName = builderNameSelect && BUILDERS.some(b => b.name === builderNameInput.value);
  if (knownName) {{
    builderNameSelect.value = builderNameInput.value;
    showNameControl('select');
  }} else {{
    showNameControl('input');
  }}
  builderNameInput.addEventListener('input', () => {{
    const typed = builderNameInput.value.trim();
    localStorage.setItem('cowork-builder-name', typed);
    // If a dropdown selection is currently in effect and the typed name no longer
    // matches it, the auto-filled email belongs to whoever was selected before --
    // clear it along with the selection instead of silently carrying a stranger's
    // email forward onto a new name.
    if (builderNameSelect && builderNameSelect.value && builderNameSelect.value !== typed) {{
      builderNameSelect.value = '';
      if (builderEmailInput) builderEmailInput.value = '';
      localStorage.removeItem('cowork-builder-email');
    }}
  }});
}}
if (builderEmailInput) {{
  builderEmailInput.value = localStorage.getItem('cowork-builder-email') || builderEmailFor(builderNameInput?.value || '');
  builderEmailInput.addEventListener('input', () => {{
    localStorage.setItem('cowork-builder-email', builderEmailInput.value.trim());
  }});
}}

document.getElementById('builder-mode-select')?.addEventListener('change', (e) => setBuilderMode(e.target.value));
function setBuilderMode(mode) {{
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

document.getElementById('builder-app-type')?.addEventListener('change', (e) => renderIdeaChips(e.target.value));

function builderChoice(fieldId) {{
  const el = document.getElementById(fieldId);
  if (el && el.tagName === 'SELECT') return el.value || '';
  return document.querySelector('#' + fieldId + ' .choice-opt.selected')?.dataset.value || '';
}}

const IDEA_SUGGESTIONS = {{
  "Arcade Game": [
    ['🏰', 'Escape the maze', 'A maze game where you escape before time runs out'],
    ['🎯', 'Beat the clock', 'Race against the clock to beat your best score'],
    ['🐉', 'Collect the treasure', 'Collect gems while avoiding obstacles'],
    ['🕹️', 'Dodge and survive', 'Dodge falling obstacles and survive as long as you can'],
    ['🏆', 'Beat the boss', 'Defeat a boss by solving three challenges in a row'],
  ],
  Puzzle: [
    ['🧩', 'Match the pairs', 'Flip cards and match the pairs before you run out of tries'],
    ['🔢', 'Slide the tiles', 'Slide numbered tiles into order to solve the puzzle'],
    ['🔗', 'Connect the dots', 'Connect matching colors without crossing lines'],
    ['🧱', 'Stack and clear', 'Stack falling blocks and clear full rows'],
    ['🗝️', 'Unlock the door', 'Solve a chain of riddles to unlock the door'],
  ],
  Quiz: [
    ['❓', 'Guess the answer', 'Multiple choice trivia with a timer for each question'],
    ['🧠', 'Test your knowledge', 'A quiz that gets harder each round'],
    ['🔤', 'Word guess', 'Guess the hidden word letter by letter'],
    ['🌍', 'True or false', 'Rapid-fire true or false questions on a topic'],
    ['🏅', 'Beat your score', 'Answer as many questions as you can before time runs out'],
  ],
  Story: [
    ['📖', 'Choose your path', 'A choose-your-own-adventure story with branching endings'],
    ['🐲', 'Tell a tale', 'An illustrated story that turns the page as you read'],
    ['🕵️', 'Solve the mystery', 'A mystery story where you pick clues to solve the case'],
    ['🌌', 'Explore a world', 'An interactive story exploring a fantasy world'],
    ['🎭', 'Pick the ending', 'A story where your choices change how it ends'],
  ],
  Tool: [
    ['⏱️', 'Track the time', 'A timer/stopwatch with lap tracking'],
    ['✅', 'Make a list', 'A simple checklist or to-do tracker'],
    ['🎲', 'Pick for me', 'A random picker/spinner for choosing between options'],
    ['🧮', 'Do the math', 'A calculator for a specific everyday task'],
    ['📆', 'Plan it out', 'A simple planner or countdown to an event'],
  ],
  "Arts/Crafts": [
    ['🎨', 'Design your own', 'A drawing canvas where you can pick colors and shapes'],
    ['🖌️', 'Paint by numbers', 'A paint-by-numbers picture to color in'],
    ['🌈', 'Mix the colors', 'An interactive canvas for mixing and blending colors'],
    ['✂️', 'Build a collage', 'Drag and arrange shapes and stickers to build a scene'],
    ['🖼️', 'Color the picture', 'An outline picture to fill in with color'],
    ['🧵', 'Design a pattern', 'A tool for designing a repeating pattern with shapes and colors'],
    ['🏺', 'Shape the clay', 'A virtual pottery wheel where you shape and decorate a pot'],
    ['🌿', 'Press the flowers', 'A nature-craft app for arranging pressed flowers and leaves into art'],
    ['🧸', 'Build a creature', 'A tool for mixing and matching parts to build a silly creature'],
    ['🎀', 'Wrap it up', 'A gift-wrapping or decorating activity with paper, ribbon, and stickers'],
  ],
  Music: [
    ['🎹', 'Play a tune', 'A simple piano/keyboard you can play with taps'],
    ['🥁', 'Make a beat', 'A drum pad for making your own beat'],
    ['🎼', 'Follow the notes', 'A rhythm game where you match falling notes'],
    ['🎤', 'Sing along', 'A karaoke-style app that shows lyrics as music plays'],
    ['🔊', 'Mix the sounds', 'An app for layering and mixing different sound effects'],
  ],
  Sports: [
    ['⛳', 'Mini golf run', 'A mini golf course where you putt through obstacles to sink the ball'],
    ['🏹', 'Hit the target', 'An archery or target-throwing game aiming for the highest score'],
    ['⚾', 'Swing for it', 'A batting or swinging game timed to hit a pitch or ball'],
    ['🎳', 'Bowl a strike', 'A bowling game where you aim and knock down all the pins'],
    ['🥊', 'Beat the record', 'A reflex sports challenge where you try to beat your own best time'],
  ],
  "Card Game": [
    ['🂡', 'Deal me in', 'A classic card game like solitaire or rummy playable solo'],
    ['🃏', 'Match the set', 'A card matching game where you collect sets before your opponent'],
    ['🎴', 'Build the deck', 'A roguelike deck-builder where you draft cards to beat escalating foes'],
    ['♠️', 'Beat the dealer', 'A blackjack-style card game against the house'],
    ['🀄', 'Memory match', 'A card-flipping memory game where you find every matching pair'],
  ],
  "Interactive Game": [
    ['🌋', 'Floor is lava', 'A floor-is-lava game where the phone calls out safe spots to jump to before time runs out'],
    ['🎌', 'Simon says', 'A Simon Says game where you follow commands only when Simon says comes first'],
    ['🚦', 'Red light green light', 'A red light green light game where you move on green and freeze on red'],
    ['🧊', 'Freeze dance', 'A freeze dance game where you dance until the music stops, then freeze'],
    ['🙋', 'Follow the leader', 'A follow-the-leader game where the phone calls out actions to copy'],
  ],
  Cooking: [
    ['🍕', 'Build the order', 'A kitchen game where you build orders correctly before time runs out'],
    ['🥧', 'Bake it right', 'A baking simulation where you follow steps to bake something'],
    ['🍹', 'Mix the recipe', 'A drink or recipe mixer where you combine ingredients in the right order'],
    ['🍳', 'Beat the rush', 'A restaurant rush game serving as many customers as you can'],
    ['🍪', 'Decorate it', 'A cookie or cake decorating activity with toppings and icing'],
  ],
  "Party Game": [
    ['🎉', 'Pass and play', 'A pass-the-device party game for a group taking turns'],
    ['🗳️', 'Vote it out', 'A group voting game where everyone picks their favorite answer'],
    ['🎤', 'Guess who', 'A charades or guessing game where one player acts and others guess'],
    ['🎲', 'Roll and dare', 'A party game combining dice rolls with fun prompts or dares'],
    ['🏁', 'Team challenge', 'A multiplayer mini-game where teams compete in quick challenges'],
  ],
}};

function renderIdeaChips(appType) {{
  const container = document.getElementById('builder-idea-chips');
  if (!container) return;
  const suggestions = IDEA_SUGGESTIONS[appType] || IDEA_SUGGESTIONS["Arcade Game"];
  container.innerHTML = suggestions.map(([emoji, label, value]) =>
    '<span class="choice-opt idea-chip" data-value="' + escHtml(value) + '">' + emoji + ' ' + escHtml(label) + '</span>'
  ).join('');
}}

renderIdeaChips(builderChoice('builder-app-type') || 'Arcade Game');

document.getElementById('builder-idea-chips')?.addEventListener('click', (e) => {{
  const chip = e.target.closest('.idea-chip');
  if (!chip) return;
  const container = document.getElementById('builder-idea-chips');
  container?.querySelectorAll('.idea-chip').forEach(c => c.classList.remove('selected'));
  chip.classList.add('selected');
  const ta = document.getElementById('builder-idea-input');
  if (ta) {{ ta.value = chip.dataset.value; ta.focus(); }}
}});

document.getElementById('builder-submit-btn')?.addEventListener('click', async () => {{
  const requester_name = builderNameInput?.value.trim() || '';
  if (!requester_name) {{ alert('Please enter your name.'); builderNameInput?.focus(); return; }}
  const requester_email = builderEmailInput?.value.trim() || '';
  if (!requester_email) {{ alert('Please enter your email so we can tell you when it is ready.'); builderEmailInput?.focus(); return; }}
  const mode = document.getElementById('builder-mode-select')?.value || 'basic';

  const criteria = {{
    app_type: builderChoice('builder-app-type'),
    theme: document.getElementById('builder-theme-input').value.trim(),
    age_range: builderChoice('builder-age-range'),
    color_vibe: builderChoice('builder-color-vibe'),
    idea: document.getElementById('builder-idea-input').value.trim(),
  }};
  if (!criteria.idea) {{ document.getElementById('builder-idea-input').focus(); return; }}
  if (mode === 'advanced') {{
    criteria.difficulty = builderChoice('builder-difficulty');
    criteria.mechanics = Array.from(document.querySelectorAll('#builder-mechanics input:checked')).map(cb => cb.value);
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
      id: r.id, requester_name, mode, criteria, has_email: true,
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

const FEEDBACK_EMOJI = {{love: "😍", like: "🙂", meh: "😐", dislike: "🙁"}};

function feedbackWidgetHtml(r) {{
  if (r.feedback) {{
    const canComment = !r.feedback.comment;
    let html = '<div class="feedback-given">Thanks for the feedback! ' + (FEEDBACK_EMOJI[r.feedback.rating] || '')
      + (canComment ? ' <button class="feedback-comment-btn" data-id="' + r.id + '">Add a comment</button>' : '')
      + '</div>';
    if (r.feedback.comment) {{
      html += '<div class="feedback-comment-text">&ldquo;' + escHtml(r.feedback.comment) + '&rdquo;</div>';
    }}
    if (canComment) {{
      html += '<div class="feedback-comment-form hidden" id="feedback-comment-form-' + r.id + '">'
        + '<textarea class="feedback-comment-ta" placeholder="Anything else? (optional)" maxlength="300"></textarea>'
        + '<div class="quick-note-actions">'
        + '<button class="quick-note-submit feedback-comment-submit" data-id="' + r.id + '">Submit</button>'
        + '</div></div>';
    }}
    return html;
  }}
  return '<button class="feedback-btn" data-id="' + r.id + '">&#128172; Tell us what you think</button>'
    + '<div class="feedback-form hidden" id="feedback-form-' + r.id + '">'
    + '<div class="feedback-emoji-row">'
    + Object.keys(FEEDBACK_EMOJI).map(k => '<button class="feedback-emoji-opt" data-id="' + r.id + '" data-rating="' + k + '">' + FEEDBACK_EMOJI[k] + '</button>').join('')
    + '</div></div>';
}}

function builderCardHtml(r) {{
  const labels = {{queued: 'Queued', generating: 'Building…', done: 'Ready ✅', error: 'Error'}};
  const badgeLabel = labels[r.status] || r.status;
  const idea = escHtml((r.criteria && r.criteria.idea) || '');
  const errorHtml = (r.status === 'error' && r.error_message)
    ? '<div class="builder-card-error" id="builder-error-' + r.id + '">' + escHtml(r.error_message) + '</div>' : '';
  const dismissHtml = (r.status === 'error')
    ? '<button class="dismiss-btn" data-id="' + r.id + '">&#10005; Remove</button>' : '';
  const openHtml = (r.status === 'done')
    ? '<a class="builder-card-open" id="builder-open-' + r.id + '" href="/' + r.target_path + '" target="_blank">Open App &rarr;</a>' : '';
  const appType = escHtml((r.criteria && r.criteria.app_type) || 'App');

  let nextStepsHtml = '';
  if (r.status === 'queued' || r.status === 'generating') {{
    const waitLine = r.status === 'queued'
      ? 'Lined up to build, usually starts within a minute.'
      : 'Building now, usually takes 1 to 4 minutes (a little longer if a few apps are building at once).';
    const emailLine = r.has_email
      ? 'We will email you the second it is ready, feel free to close this tab.'
      : 'No email was given, so keep this tab open or check back to see when it is done.';
    nextStepsHtml = '<div class="builder-next-steps">' + waitLine + ' ' + emailLine + '</div>';
  }}

  let reportHtml = '';
  let feedbackHtml = '';
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

    feedbackHtml = feedbackWidgetHtml(r);
  }}

  return '<div class="builder-card" id="builder-card-' + r.id + '">'
    + '<div class="builder-card-header">'
    + '<span class="builder-card-title">' + appType + ' — ' + escHtml(r.requester_name || '') + '</span>'
    + '<span class="builder-badge ' + r.status + '" id="builder-badge-' + r.id + '">' + badgeLabel + '</span>'
    + '</div>'
    + '<div class="builder-card-meta">' + idea + '</div>'
    + nextStepsHtml + errorHtml + dismissHtml + openHtml + reportHtml + feedbackHtml
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
  const familyRecent = builds.slice(0, 5);
  familyList.innerHTML = familyRecent.length ? familyRecent.map(builderCardHtml).join('') : '<p class="builder-empty">No apps built yet.</p>';
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
    if (generatingStartedAt && Date.now() - generatingStartedAt > 660000) {{
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
    const prevStatus = idx >= 0 ? APP_REQUESTS[idx].status : null;
    if (idx >= 0) APP_REQUESTS[idx] = Object.assign({{}}, APP_REQUESTS[idx], status);
    if (status.status === 'done' && prevStatus !== 'done' && !status.feedback && (status.kind || 'build') === 'build') {{
      showFeedbackPopup(id);
    }}
    if (status.status === 'done' || status.status === 'error') {{
      clearInterval(builderPolls[id]);
      delete builderPolls[id];
    }}
    renderBuilderLists();
  }}, 4000);
}}

function showFeedbackPopup(id) {{
  document.getElementById('feedback-popup')?.remove();
  const popup = document.createElement('div');
  popup.className = 'feedback-popup';
  popup.id = 'feedback-popup';
  popup.innerHTML = '<div class="feedback-popup-text">Your app is ready! What did you think?</div>'
    + '<div class="feedback-emoji-row">'
    + Object.keys(FEEDBACK_EMOJI).map(k => '<button class="feedback-emoji-opt" data-id="' + id + '" data-rating="' + k + '">' + FEEDBACK_EMOJI[k] + '</button>').join('')
    + '</div>'
    + '<button class="feedback-popup-close" type="button">Not now</button>';
  document.querySelector('.builder-lists')?.appendChild(popup);
  popup.querySelector('.feedback-popup-close').addEventListener('click', () => popup.remove());
}}

document.querySelector('.builder-lists')?.addEventListener('click', async (e) => {{
  const dismissBtn = e.target.closest('.dismiss-btn');
  if (dismissBtn) {{
    if (!confirm('Remove this failed build from the list?')) return;
    const id = dismissBtn.dataset.id;
    dismissBtn.disabled = true;
    const r = await apiPost('/api/app_requests/dismiss', {{id}});
    if (r?.ok) {{
      APP_REQUESTS = APP_REQUESTS.filter(x => x.id !== id);
      renderBuilderLists();
    }} else {{
      dismissBtn.disabled = false;
      alert(r?.error || 'Could not remove — please try again.');
    }}
    return;
  }}
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
    if (!requester_name) {{ alert('Please enter your name above (under Your Name) so we know who this is from.'); builderNameInput?.focus(); return; }}
    const requester_email = builderEmailInput?.value.trim() || '';
    if (!requester_email) {{ alert('Please enter your email above (under Email) so we can tell you when it is fixed.'); builderEmailInput?.focus(); return; }}
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
    return;
  }}
  const feedbackBtn = e.target.closest('.feedback-btn');
  if (feedbackBtn) {{
    const form = document.getElementById('feedback-form-' + feedbackBtn.dataset.id);
    if (form) form.classList.toggle('hidden');
    return;
  }}
  const emojiOpt = e.target.closest('.feedback-emoji-opt');
  if (emojiOpt) {{
    const id = emojiOpt.dataset.id;
    const rating = emojiOpt.dataset.rating;
    const r = await apiPost('/api/app_requests/feedback', {{id, rating, comment: ''}});
    if (r?.ok) {{
      const idx = APP_REQUESTS.findIndex(x => x.id === id);
      if (idx >= 0) APP_REQUESTS[idx] = Object.assign({{}}, APP_REQUESTS[idx], {{feedback: {{rating, comment: ''}}}});
      document.getElementById('feedback-popup')?.remove();
      renderBuilderLists();
    }}
    return;
  }}
  const commentBtn = e.target.closest('.feedback-comment-btn');
  if (commentBtn) {{
    const form = document.getElementById('feedback-comment-form-' + commentBtn.dataset.id);
    if (form) {{
      form.classList.toggle('hidden');
      if (!form.classList.contains('hidden')) form.querySelector('.feedback-comment-ta').focus();
    }}
    return;
  }}
  const commentSubmitBtn = e.target.closest('.feedback-comment-submit');
  if (commentSubmitBtn) {{
    const id = commentSubmitBtn.dataset.id;
    const existing = APP_REQUESTS.find(x => x.id === id);
    const rating = existing?.feedback?.rating;
    if (!rating) return;
    const form = document.getElementById('feedback-comment-form-' + id);
    const ta = form?.querySelector('.feedback-comment-ta');
    const comment = ta?.value.trim() || '';
    commentSubmitBtn.disabled = true;
    const r = await apiPost('/api/app_requests/feedback', {{id, rating, comment}});
    commentSubmitBtn.disabled = false;
    if (r?.ok) {{
      const idx = APP_REQUESTS.findIndex(x => x.id === id);
      if (idx >= 0) APP_REQUESTS[idx] = Object.assign({{}}, APP_REQUESTS[idx], {{feedback: {{rating, comment}}}});
      renderBuilderLists();
    }}
  }}
}});

const builderShareBtn = document.getElementById('builder-native-share-btn');
const builderCopyBtn = document.getElementById('builder-copy-btn');
const builderShareLink = document.getElementById('builder-share-link');
const builderShareCopied = document.getElementById('builder-share-copied');
const BUILDER_SHARE_URL = {share_url_json};
if (builderShareBtn && navigator.share) {{
  builderShareBtn.classList.remove('hidden');
  builderShareBtn.addEventListener('click', () => {{
    navigator.share({{title: 'Build Your Own App', url: BUILDER_SHARE_URL}}).catch(() => {{}});
  }});
}}
builderCopyBtn?.addEventListener('click', async () => {{
  try {{
    await navigator.clipboard.writeText(BUILDER_SHARE_URL);
  }} catch(e) {{
    builderShareLink?.select();
    document.execCommand('copy');
  }}
  if (builderShareCopied) {{
    builderShareCopied.classList.remove('hidden');
    setTimeout(() => builderShareCopied.classList.add('hidden'), 1800);
  }}
}});

function focusRequestFromHash() {{
  const m = location.hash.match(/^#request-([a-z0-9]+)$/);
  if (!m) return;
  const id = m[1];
  const tryFocus = () => {{
    const card = document.getElementById('builder-card-' + id);
    if (!card) return false;
    card.scrollIntoView({{behavior: 'smooth', block: 'center'}});
    card.classList.add('builder-card-highlight');
    setTimeout(() => card.classList.remove('builder-card-highlight'), 4000);
    card.querySelector('.feedback-btn')?.click();
    return true;
  }};
  if (!tryFocus()) {{
    const iv = setInterval(() => {{ if (tryFocus()) clearInterval(iv); }}, 300);
    setTimeout(() => clearInterval(iv), 5000);
  }}
}}
"""


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


def notify_async(requester_name, requester_email, target_path, request_id):
    """Fires send_build_notification() on its own daemon thread instead of
    calling it inline. generate_app_worker calls this from inside
    `with GENERATION_SEMAPHORE:` -- a blocking SMTP call there would hold a
    generation slot open (delaying the next queued build) for however long a
    slow or unreachable mail server takes to respond, for a reason that has
    nothing to do with app generation."""
    threading.Thread(
        target=send_build_notification, args=(requester_name, requester_email, target_path, request_id), daemon=True,
    ).start()


def send_build_notification(requester_name, requester_email, target_path, request_id):
    """Best-effort 'your app is ready' email. Must never raise into the caller --
    a missing/unconfigured email_config.json or an SMTP hiccup should not affect
    the build itself, so every failure path here just logs and returns."""
    if not requester_email:
        return
    cfg = load_email_config()
    if not cfg:
        return
    link = f"{get_base_url()}/{target_path}"
    feedback_link = f"{get_base_url()}/build#request-{request_id}"
    msg = EmailMessage()
    msg["Subject"] = f"Your app is ready, {requester_name}!"
    msg["From"] = f'{cfg.get("from_name", "AppVerse")} <{cfg["smtp_user"]}>'
    msg["To"] = requester_email
    msg.set_content(
        f"Hi {requester_name},\n\n"
        f"Your app is built and ready to play:\n{link}\n\n"
        f"Tell us what you think:\n{feedback_link}\n\n"
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


def notify_feedback_async(requester_name, rating, comment, request_id):
    """Same fire-and-forget pattern as notify_async(), mirroring
    notify_note_async()/send_note_notification() -- reused here because the
    feedback endpoint runs synchronously inside _handle_post, which already
    holds DATA_LOCK/data_lock() for its whole duration. A blocking SMTP call
    on that path would stall every other concurrent request, including the
    background worker's own lock-needing writes."""
    threading.Thread(
        target=send_feedback_notification, args=(requester_name, rating, comment, request_id), daemon=True,
    ).start()


def send_feedback_notification(requester_name, rating, comment, request_id):
    """Best-effort 'new feedback' email to the site owner. Must never raise
    into the caller -- see send_build_notification for the same reasoning.
    Requires an 'owner_email' field in email_config.json; silently skips
    without one."""
    cfg = load_email_config()
    if not cfg:
        return
    to_email = cfg.get("owner_email")
    if not to_email:
        return
    link = f"{get_base_url()}/build#request-{request_id}"
    msg = EmailMessage()
    msg["Subject"] = f"AppVerse: {requester_name} left feedback"
    msg["From"] = f'{cfg.get("from_name", "AppVerse")} <{cfg["smtp_user"]}>'
    msg["To"] = to_email
    msg.set_content(
        f"{requester_name} rated their app: {rating}\n\n"
        + (f"Comment:\n{comment}\n\n" if comment else "")
        + f"View it: {link}\n"
    )
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 587), timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["smtp_user"], cfg["smtp_app_password"])
            smtp.send_message(msg)
        print(f"[builder] feedback notification email sent to {to_email}", flush=True)
    except Exception as e:
        print(f"[builder] feedback notification email failed: {e}", flush=True)


def update_app_request(request_id, **fields):
    """Re-read data fresh before writing, mirroring daily_check.py's update_note()
    idiom, so a slow generation doesn't clobber concurrent HTTP-server writes.
    Holds DATA_LOCK for the whole read-modify-write cycle -- see DATA_LOCK's
    definition for why a re-read alone isn't a strong enough guarantee. Also
    takes the cross-process data_lock() so a background generation thread's
    write can't lose (or be lost to) a concurrent daily_check.py write."""
    with DATA_LOCK, data_lock():
        data = load_data()
        for req in data.get("app_requests", []):
            if req.get("id") == request_id:
                req.update(fields)
                break
        save_data(data)


def app_names_for_context(limit=20):
    apps = discover_apps()
    names = [a["name"] for cat in apps.values() for a in cat]
    return ", ".join(names[:limit])


NEEDS_REPLY_INSTRUCTION = (
    "After your response, on its own final line, write exactly 'NEEDS_REPLY: yes' "
    "if you asked a question or are waiting on a decision from them before doing "
    "anything else, or 'NEEDS_REPLY: no' if this is purely informational and needs "
    "no further input from them."
)

NEEDS_REPLY_RE = re.compile(r'\n?NEEDS_REPLY:\s*(yes|no)\s*$', re.IGNORECASE)


def parse_needs_reply(response):
    """Strips the trailing NEEDS_REPLY marker the prompt asks for and returns
    (cleaned_response, needs_reply: bool). If the model didn't include the
    marker, needs_reply defaults to False and the text is returned as-is."""
    m = NEEDS_REPLY_RE.search(response)
    if not m:
        return response, False
    return response[:m.start()].rstrip(), m.group(1).lower() == "yes"


def build_note_prompt(text):
    return (
        "You are an AI assistant reviewing developer notes for a local family app "
        f"library called 'AppVerse' -- self-contained HTML apps stored at {APPS_DIR} "
        "covering kids games, music, puzzles, education, art, and productivity.\n\n"
        f"Current apps: {app_names_for_context()}\n\n"
        f"Developer note: \"{text}\"\n\n"
        "Provide a concise, actionable response (2-5 sentences). "
        "For bug reports: suggest how to investigate and fix. "
        "For feature ideas: assess feasibility and outline an approach. "
        "For questions: answer directly. "
        "Be specific -- reference actual file names or code patterns if relevant.\n\n"
        f"{NEEDS_REPLY_INSTRUCTION}"
    )


def build_note_reply_prompt(note, reply_text):
    """Builds a conversation transcript from the note's original exchange plus
    every earlier reply, so the model answers the latest message in context
    instead of cold, one-shot like the first response."""
    convo = [f'Family member: "{note.get("text", "")}"']
    if note.get("ai_response"):
        convo.append(f'You (AI): "{note["ai_response"]}"')
    for r in note.get("replies", []):
        convo.append(f'Family member: "{r.get("text", "")}"')
        if r.get("ai_response"):
            convo.append(f'You (AI): "{r["ai_response"]}"')
    convo.append(f'Family member: "{reply_text}"')
    transcript = "\n".join(convo)
    return (
        "You are an AI assistant continuing a conversation about a developer note for a "
        f"local family app library called 'AppVerse' -- self-contained HTML apps stored "
        f"at {APPS_DIR} covering kids games, music, puzzles, education, art, and "
        "productivity.\n\n"
        f"Current apps: {app_names_for_context()}\n\n"
        f"Conversation so far:\n{transcript}\n\n"
        "Reply to the family member's latest message with a concise, actionable response "
        "(2-5 sentences), continuing the conversation naturally given everything said "
        "above. You cannot write or edit files yourself in this conversation -- if they've "
        "asked you to go ahead and build or implement something, say so plainly and "
        "summarize exactly what change a person should make in a real Claude Code session.\n\n"
        f"{NEEDS_REPLY_INSTRUCTION}"
    )


def ask_claude_note(prompt, timeout):
    """Runs headless `claude -p` and returns (response_text, success).

    The prompt embeds untrusted note/reply text typed by anyone via the web
    UI, and a plain `claude -p` would inherit the user's global settings.json
    allow-list (which pre-approves mcp-coderunner/mcp-filesystem) -- turning a
    malicious note into arbitrary code execution the moment it's reviewed.
    This job only ever needs a text answer, so it runs hermetically: no MCP
    servers, no tools allowed, every built-in tool explicitly denied. Same
    hardening as daily_check.py's ask_claude() -- see there for the full
    rationale."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt,
             "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}',
             "--allowedTools", "",
             "--disallowedTools",
             "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", cwd=str(APPS_DIR),
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip() or f"exit code {result.returncode}"
            return err, False
        text = (result.stdout or "").strip()
        return (text or "(no response)"), True
    except subprocess.TimeoutExpired:
        return "Timed out waiting for Claude response.", False
    except FileNotFoundError:
        return "claude CLI not found -- ensure Claude Code is installed and on PATH.", False
    except Exception as e:
        return f"Error: {e}", False


def update_note_review(note_id, reply_id, response, needs_reply=False):
    """Re-read-modify-write under DATA_LOCK, mirroring update_app_request(). If
    reply_id is set, updates that reply inside the note's replies list;
    otherwise updates the note's own top-level review fields. Also takes the
    cross-process data_lock() -- daily_check.py can be reviewing a different
    pending item at the same moment this real-time worker saves one."""
    with DATA_LOCK, data_lock():
        data = load_data()
        note = next((n for n in data.get("notes", []) if n.get("id") == note_id), None)
        if note is None:
            return
        reviewed_at = now_iso()
        if reply_id:
            reply = next((r for r in note.get("replies", []) if r.get("id") == reply_id), None)
            if reply is None:
                return
            reply["reviewed"] = True
            reply["ai_response"] = response
            reply["reviewed_at"] = reviewed_at
            reply["needs_reply"] = needs_reply
        else:
            note["reviewed"] = True
            note["ai_response"] = response
            note["reviewed_at"] = reviewed_at
            note["needs_reply"] = needs_reply
        save_data(data)


def notify_note_async(snippet, response, is_reply, needs_reply=False):
    threading.Thread(target=send_note_notification, args=(snippet, response, is_reply, needs_reply), daemon=True).start()


def send_note_notification(snippet, response, is_reply, needs_reply=False):
    """Best-effort 'your note got an AI reply' email. Must never raise into the
    caller -- see send_build_notification for the same reasoning. Requires an
    'owner_email' field in email_config.json; silently skips without one."""
    cfg = load_email_config()
    if not cfg:
        return
    to_email = cfg.get("owner_email")
    if not to_email:
        return
    link = f"{get_base_url()}/#notes"
    if needs_reply:
        kind = "is waiting on your reply"
    else:
        kind = "replied to your note" if is_reply else "reviewed your note"
    msg = EmailMessage()
    msg["Subject"] = f"AppVerse: AI {kind}"
    msg["From"] = f'{cfg.get("from_name", "AppVerse")} <{cfg["smtp_user"]}>'
    msg["To"] = to_email
    msg.set_content(
        f"You wrote:\n{(snippet or '')[:200]}\n\n"
        f"AI response:\n{response}\n\n"
        f"Reply here: {link}\n"
    )
    try:
        with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 587), timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["smtp_user"], cfg["smtp_app_password"])
            smtp.send_message(msg)
        print(f"[notes] notification email sent to {to_email}", flush=True)
    except Exception as e:
        print(f"[notes] notification email failed: {e}", flush=True)


def review_note_worker(note_id, reply_id=None):
    with NOTE_REVIEW_SEMAPHORE:
        data = load_data()
        note = next((n for n in data.get("notes", []) if n.get("id") == note_id), None)
        if note is None:
            return
        tag = f"{note_id}/{reply_id}" if reply_id else note_id

        if reply_id:
            reply = next((r for r in note.get("replies", []) if r.get("id") == reply_id), None)
            if reply is None:
                return
            prompt = build_note_reply_prompt(note, reply.get("text", ""))
            snippet = reply.get("text", "")
        else:
            prompt = build_note_prompt(note.get("text", ""))
            snippet = note.get("text", "")

        print(f"[notes] reviewing {tag}", flush=True)
        response, success = ask_claude_note(prompt, NOTE_REVIEW_TIMEOUT_SEC)
        if success:
            response, needs_reply = parse_needs_reply(response)
            update_note_review(note_id, reply_id, response, needs_reply)
            print(f"[notes] {tag} reviewed ({len(response)} chars, needs_reply={needs_reply})", flush=True)
            notify_note_async(snippet, response, is_reply=bool(reply_id), needs_reply=needs_reply)
        else:
            print(f"[notes] {tag} failed, leaving pending: {response[:150]}", flush=True)


def build_prompt(criteria, mode, target_filename, requester_name):
    target_full = CUSTOM_APPS_DIR / target_filename
    mechanics_line = f"Requested mechanics: {', '.join(criteria.get('mechanics', []))}\n" if criteria.get("mechanics") else ""
    theme_line = f"Theme: {criteria.get('theme')}\n" if criteria.get("theme") else ""
    difficulty_line = f"Difficulty: {criteria.get('difficulty')}\n" if criteria.get("difficulty") else ""
    tech_line = f"Specific technical requests: {criteria.get('tech_requests')}\n" if criteria.get("tech_requests") else ""
    inspired_line = f"Should feel similar in spirit to: {criteria.get('inspired_by')}\n" if criteria.get("inspired_by") else ""
    slug = slug_from_filename(target_filename)

    return (
        "You are generating exactly ONE new self-contained HTML app for a local family app "
        "library called 'AppVerse', built by a kid using a 'Build Your Own App' wizard.\n\n"
        f"App type: {criteria.get('app_type')}\n"
        f"{theme_line}"
        f"Target age range: {criteria.get('age_range')}\n"
        f"Visual color vibe: {criteria.get('color_vibe')}\n"
        f"One-line idea: {criteria.get('idea')}\n"
        f"{mechanics_line}{difficulty_line}{tech_line}{inspired_line}"
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
        "no CDN links, no external fonts or images. There is NO server and NO internet access "
        "available to you or the app -- if the request mentions \"online\" play, real-time "
        "networked multiplayer, or connecting with players on other devices, build it as local "
        "same-device pass-and-play or split-screen multiplayer instead (this is always possible "
        "and is what \"Local multiplayer\" already means in this project); never attempt real "
        "network code, and never spend extra turns trying to reconcile an online request with "
        "these constraints -- just build the local equivalent and move on.\n"
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
        "MAKE IT FEEL FINISHED, NOT JUST FUNCTIONAL -- this applies to every build, regardless of "
        "which mechanics were requested above:\n"
        "- Add short sound effects for key interactions (a tap, a win, a mistake) synthesized live "
        "with the Web Audio API -- no external audio files.\n"
        "- Animate state changes instead of snapping: use CSS transitions/keyframes or a JS easing "
        "loop for movement, appearance, and feedback. A little bounce, pulse, or particle burst on "
        "the main interaction goes a long way.\n"
        "- Give it a title/start screen with a clear call-to-action button, and a real win/complete/"
        "game-over state with a way to play again -- don't drop the player straight into a bare "
        "canvas with no framing.\n"
        "- Any illustration or drawn asset should be shaded/filled and use the full color palette, "
        "not a thin single-color outline sketch -- it should look like something a kid would want "
        "to show a friend, not a wireframe.\n\n"
        "Build the complete, working app in one pass -- do not ask clarifying questions, do not "
        "produce placeholder or skeleton code."
    )


def build_fix_prompt(original, issue_description, target_filename):
    target_full = CUSTOM_APPS_DIR / target_filename
    criteria = (original or {}).get("criteria", {})
    return (
        "You are fixing a bug in an existing self-contained HTML app in a local family app "
        "library called 'AppVerse'. The app was originally generated by an earlier AI pass "
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
            mtime_before = target_full_path.stat().st_mtime_ns if target_full_path.exists() else 0
        else:
            criteria = req.get("criteria", {})
            mode = req.get("mode", "basic")
            prompt = build_prompt(criteria, mode, target_filename, requester_name)
            mtime_before = None

        log_tail = ""
        try:
            result = subprocess.run(
                ["claude", "--permission-mode", "dontAsk", "-p", prompt,
                 # Every file tool is scoped to custom_apps. The prompt embeds
                 # untrusted user input (idea/theme/issue_description), so an
                 # unscoped Read/Glob/Grep would be a prompt-injection primitive
                 # for reading anything on disk (e.g. email_config.json's SMTP
                 # password) and writing it into the served HTML. The generator
                 # only ever needs to touch the one target file, so deny the
                 # rest -- builds read nothing; a fix reads its own file here.
                 "--allowedTools",
                 f"Write({CUSTOM_APPS_DIR}\\**),Edit({CUSTOM_APPS_DIR}\\**),Read({CUSTOM_APPS_DIR}\\**)",
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
                touched = target_full_path.exists() and target_full_path.stat().st_mtime_ns > mtime_before
                if touched:
                    print(f"[builder] {request_id} done (fix applied) -> {target_filename}", flush=True)
                    update_app_request(request_id, status="done", finished=finished, log_tail=log_tail)
                    notify_async(requester_name, req.get("requester_email", ""), req.get("target_path", f"custom_apps/{target_filename}"), request_id)
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
                notify_async(requester_name, req.get("requester_email", ""), f"custom_apps/{actual_filename}", request_id)
            else:
                err = f"No file was created (exit code {result.returncode})."
                print(f"[builder] {request_id} error: {err}", flush=True)
                update_app_request(request_id, status="error", finished=finished, error_message=err, log_tail=log_tail)

        except subprocess.TimeoutExpired as e:
            # subprocess.run() populates e.stdout/e.stderr with whatever the child
            # had produced before it was killed -- capture it so a repeat timeout
            # is diagnosable instead of leaving log_tail blank.
            finished = now_iso()
            log_tail = ((e.stdout or "") + (e.stderr or ""))[-2000:]
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
    def _note_pending(n):
        return not n.get("reviewed") or any(not r.get("reviewed") for r in n.get("replies", []))
    def _note_needs_reply(n):
        replies = n.get("replies", [])
        latest = replies[-1] if replies else n
        return bool(latest.get("reviewed")) and bool(latest.get("needs_reply"))
    pending_count = sum(1 for n in notes if _note_pending(n))
    needs_reply_count = sum(1 for n in notes if _note_needs_reply(n))
    if pending_count and needs_reply_count:
        notes_tab_label = f"({pending_count} pending, {needs_reply_count} need reply)"
    elif needs_reply_count:
        notes_tab_label = f"({needs_reply_count} need reply)"
    elif pending_count:
        notes_tab_label = f"({pending_count} pending)"
    else:
        notes_tab_label = f"({note_count})"
    playlists = data.get("playlists", {})
    playlists_json = json.dumps(playlists).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    playlist_count = len(playlists)

    app_requests = data.get("app_requests", [])
    app_requests_public = [strip_private_fields(r) for r in app_requests]
    app_requests_json = json.dumps(app_requests_public).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    app_request_count = len(app_requests)

    builders_json = json.dumps(list_builders(data)).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    share_url = f"{base_url}/build"

    notes_items_html = ""
    for note in notes:
        created = note.get("created", "")[:16].replace("T", " ")
        replies = note.get("replies", [])
        if not note.get("reviewed"):
            status_cls, status_txt = "pending", "Pending AI Review"
        elif not replies and note.get("needs_reply"):
            status_cls, status_txt = "needs-reply", "Awaiting Your Reply"
        else:
            status_cls, status_txt = "reviewed", "AI Reviewed"
        _air = (note.get("ai_response") or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        ai_block = f'<div class="ai-response">{_air}</div>' if _air else ""
        nid = note.get("id", "")
        ntxt = note.get("text","").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

        replies_html = ""
        for idx, r in enumerate(replies):
            is_latest = idx == len(replies) - 1
            r_created = r.get("created", "")[:16].replace("T", " ")
            if not r.get("reviewed"):
                r_status_cls, r_status_txt = "pending", "Pending AI Review"
            elif is_latest and r.get("needs_reply"):
                r_status_cls, r_status_txt = "needs-reply", "Awaiting Your Reply"
            else:
                r_status_cls, r_status_txt = "reviewed", "AI Reviewed"
            r_air = (r.get("ai_response") or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            r_ai_block = f'<div class="ai-response">{r_air}</div>' if r_air else ""
            r_txt = (r.get("text","")).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            replies_html += (
                f'<div class="note-reply"><div class="note-header"><span class="note-ts">{r_created}</span>'
                f'<span class="note-badge {r_status_cls}">{r_status_txt}</span></div>'
                f'<div class="note-text">{r_txt}</div>{r_ai_block}</div>\n'
            )

        reply_form = (
            f'<div class="note-reply-toggle-row"><button class="note-reply-toggle-btn" data-id="{nid}">&#128172; Reply</button></div>'
            f'<div class="quick-note-form hidden" id="reply-{nid}">'
            f'<textarea class="quick-note-ta" placeholder="Reply to the AI..."></textarea>'
            f'<div class="quick-note-actions">'
            f'<button class="quick-note-submit note-reply-submit" data-id="{nid}">Send</button>'
            f'<button class="quick-note-cancel note-reply-cancel" data-id="{nid}">Cancel</button>'
            f'</div></div>'
        ) if note.get("reviewed") else ""

        notes_items_html += (
            f'<div class="note-card" id="note-{nid}"><div class="note-header"><span class="note-ts">{created}</span>'
            f'<span class="note-badge {status_cls}">{status_txt}</span>'
            f'<button class="note-delete" data-id="{nid}">&#x1F5D1;</button></div>'
            f'<div class="note-text">{ntxt}</div>{ai_block}{replies_html}{reply_form}</div>\n'
        )
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
{THEME_INIT_SCRIPT}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AppVerse</title>
<meta name="description" content="A local launcher for {app_count} HTML apps — games, tools, education, music, and more.">
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#7c6ee6">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="AppVerse">
<link rel="apple-touch-icon" href="/icon-192.png">
<style>
{THEME_ROOT_VARS}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
  header {{ background: var(--surface); padding: 2rem 1.5rem 0; border-bottom: 1px solid var(--border); text-align: center; }}
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
  .note-badge.needs-reply {{ background: rgba(230,162,60,0.16); color: #e6a23c; }}
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
  .note-reply {{ margin: 0.6rem 0 0 1rem; padding: 0.7rem 0.9rem; border-left: 2px solid var(--border); background: rgba(124,110,230,0.04); border-radius: 0 8px 8px 0; }}
  .note-reply-toggle-row {{ margin-top: 0.7rem; }}
  .note-reply-toggle-btn {{ background: none; border: 1px solid var(--border); border-radius: 6px; color: var(--muted); font-size: 0.78rem; padding: 0.3rem 0.7rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }}
  .note-reply-toggle-btn:hover {{ color: var(--accent); border-color: var(--accent); }}
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
{BUILDER_STYLES}
</style>
</head>
<body>
{THEME_TOGGLE_HTML}
<header>
  <h1>AppVerse</h1>
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
{builder_share_row_html(share_url)}
{BUILDER_FORM_HTML}
{BUILDER_LISTS_HTML}
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
document.querySelectorAll('.note-reply-toggle-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const form = document.getElementById('reply-' + btn.dataset.id);
    if (form) {{ form.classList.toggle('hidden'); if (!form.classList.contains('hidden')) form.querySelector('textarea').focus(); }}
  }});
}});
document.querySelectorAll('.note-reply-submit').forEach(btn => {{
  btn.addEventListener('click', async () => {{
    const form = document.getElementById('reply-' + btn.dataset.id);
    const ta = form.querySelector('textarea');
    const text = ta.value.trim();
    if (!text) {{ ta.focus(); return; }}
    btn.disabled = true; btn.textContent = 'Sending...';
    await apiPost('/api/notes/reply', {{note_id: btn.dataset.id, text}});
    location.reload();
  }});
}});
document.querySelectorAll('.note-reply-cancel').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const form = document.getElementById('reply-' + btn.dataset.id);
    if (form) {{ form.classList.add('hidden'); form.querySelector('textarea').value = ''; }}
  }});
}});

{builder_logic_js(app_requests_json, builders_json, share_url)}
{THEME_TOGGLE_JS}
</script>
</body>
</html>"""


def generate_builder_page(app_requests_public, builders, share_url):
    """Standalone version of the Build tab -- just the form + creation lists, no
    tabs nav / apps grid / other tabs -- so it can be bookmarked, texted, or
    emailed as a link that opens straight into building an app (`share_url`,
    `/build`) instead of requiring someone to load the full hub and navigate to
    the Build tab first. Reuses the exact same BUILDER_FORM_HTML/BUILDER_LISTS_HTML/
    builder_logic_js() as the tab -- same DOM ids, same behavior, same data."""
    app_requests_json = json.dumps(app_requests_public).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    builders_json = json.dumps(builders).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT_SCRIPT}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Build Your Own App &mdash; AppVerse</title>
<meta name="description" content="Build your own app: pick a type, theme, and idea, and a real playable app gets created for you.">
<meta name="theme-color" content="#7c6ee6">
<style>
{THEME_ROOT_VARS}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}
  .hidden {{ display: none !important; }}
  #tab-builder {{ display: block; padding: 0; max-width: none; margin: 0; }}
{BUILDER_STYLES}
</style>
</head>
<body>
{THEME_TOGGLE_HTML}
<div class="standalone-wrap">
  <div class="standalone-header">
    <h1>&#128736; Build Your Own App</h1>
    <p>Describe an app and it'll be built for you &mdash; playable in a few minutes.</p>
  </div>
{builder_share_row_html(share_url)}
{BUILDER_FORM_HTML}
{BUILDER_LISTS_HTML}
  <div class="standalone-footer">
    <a href="/">&#127968; Open the full AppVerse hub</a>
  </div>
</div>
<script>
{SHARED_JS_HELPERS}
{builder_logic_js(app_requests_json, builders_json, share_url)}
{THEME_TOGGLE_JS}
loadAppRequests().then(focusRequestFromHash);
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
        "name": "AppVerse",
        "short_name": "AppVerse",
        "description": "Local app launcher for family-made HTML apps",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f5f5fa",
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
        elif path == "/build":
            data = load_data()
            app_requests_public = [strip_private_fields(r) for r in data.get("app_requests", [])]
            share_url = f"{get_base_url()}/build"
            html = generate_builder_page(app_requests_public, list_builders(data), share_url)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/build/print":
            share_url = f"{get_base_url()}/build"
            html = generate_build_print_page(share_url)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
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
            # Deny-by-default: this directory is the source tree + data store +
            # SMTP config, NOT a public docroot. SimpleHTTPRequestHandler would
            # happily serve serve_apps.py, .app_data.json (names/emails/notes),
            # and email_config.json (SMTP password) to anyone who can reach the
            # port (bound 0.0.0.0, plus a Tailscale PUBLIC_URL). Only the
            # self-contained .html apps and image assets are public.
            if not self._is_public_static(path):
                self.send_error(404, "Not Found")
                return
            super().do_GET()

    @staticmethod
    def _is_public_static(path):
        # No dotfiles or dotdirs (.app_data.json, .claude/, email_config.json is
        # not a dotfile but is denied by the suffix whitelist below anyway), and
        # only known static app/media types. Everything else -- .py, .json,
        # .ps1/.bat/.vbs, .md, .txt, config -- is not downloadable.
        if any(seg.startswith(".") for seg in path.split("/") if seg):
            return False
        return path.lower().endswith(
            (".html", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
             ".woff", ".woff2")
        )

    def do_POST(self):
        path = unquote(self.path.split("?")[0])
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = -1
        if length < 0 or length > MAX_POST_BODY:
            self.send_error(413, "Payload too large")
            return
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}
        # Whole request handled under DATA_LOCK: load, decide, mutate, save, and
        # respond all happen atomically w.r.t. every other POST and every
        # background generation thread's update_app_request() calls -- see
        # DATA_LOCK's definition for why a load-once-at-the-top snapshot alone
        # isn't safe once background threads can write concurrently. data_lock()
        # extends that guarantee across processes (vs. daily_check.py), whose
        # writes DATA_LOCK -- an in-process threading.Lock -- cannot see.
        with DATA_LOCK, data_lock():
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
                    "reviewed_at": None,
                    "needs_reply": False,
                    "replies": []
                }
                data.setdefault("notes", []).append(note)
                save_data(data)
                threading.Thread(target=review_note_worker, args=(note["id"],), daemon=True).start()
            self._json({"ok": True})

        elif path == "/api/notes/delete":
            nid = payload.get("id", "")
            data["notes"] = [n for n in data.get("notes", []) if n.get("id") != nid]
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/notes/reply":
            nid = payload.get("note_id", "")
            text = payload.get("text", "").strip()
            note = next((n for n in data.get("notes", []) if n.get("id") == nid), None)
            if note and text:
                reply = {
                    "id": uuid.uuid4().hex[:8],
                    "text": text,
                    "created": now_iso(),
                    "reviewed": False,
                    "ai_response": None,
                    "reviewed_at": None,
                    "needs_reply": False
                }
                note.setdefault("replies", []).append(reply)
                save_data(data)
                threading.Thread(target=review_note_worker, args=(nid, reply["id"]), daemon=True).start()
                self._json({"ok": True, "id": reply["id"]})
            else:
                self._json({"ok": False})

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
            raw_email = (payload.get("requester_email") or "").strip()[:100]
            requester_email = raw_email if EMAIL_RE.match(raw_email) else ""
            mode = payload.get("mode") or "basic"
            criteria = payload.get("criteria") or {}
            if mode not in ("basic", "advanced"):
                self._json({"ok": False, "error": "invalid mode"}, status=400)
                return
            if not requester_name:
                self._json({"ok": False, "error": "missing required field: requester_name"}, status=400)
                return
            if not raw_email:
                self._json({"ok": False, "error": "missing required field: requester_email"}, status=400)
                return
            if not requester_email:
                self._json({"ok": False, "error": "please enter a valid email address"}, status=400)
                return
            for field in ("app_type", "age_range", "color_vibe", "idea"):
                if not str(criteria.get(field, "")).strip():
                    self._json({"ok": False, "error": f"missing required field: {field}"}, status=400)
                    return

            clean_criteria = {
                "app_type": str(criteria["app_type"]).strip()[:40],
                "age_range": str(criteria["age_range"]).strip()[:20],
                "color_vibe": str(criteria["color_vibe"]).strip()[:40],
                "idea": str(criteria["idea"]).strip()[:200],
            }
            if criteria.get("theme"):
                clean_criteria["theme"] = str(criteria["theme"]).strip()[:60]
            if mode == "advanced":
                mechanics = criteria.get("mechanics") or []
                if isinstance(mechanics, list):
                    clean_criteria["mechanics"] = [str(m).strip()[:40] for m in mechanics][:10]
                if criteria.get("difficulty"):
                    clean_criteria["difficulty"] = str(criteria["difficulty"]).strip()[:20]
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
            raw_email = (payload.get("requester_email") or "").strip()[:100]
            requester_email = raw_email if EMAIL_RE.match(raw_email) else ""
            fix_of = (payload.get("fix_of") or "").strip()
            issue_description = (payload.get("issue_description") or "").strip()[:500]
            if not requester_name:
                self._json({"ok": False, "error": "missing required field: requester_name"}, status=400)
                return
            if not raw_email:
                self._json({"ok": False, "error": "missing required field: requester_email"}, status=400)
                return
            if not requester_email:
                self._json({"ok": False, "error": "please enter a valid email address"}, status=400)
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
                "requester_email": requester_email,
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

        elif path == "/api/app_requests/dismiss":
            request_id = (payload.get("id") or "").strip()
            req = next((r for r in data.get("app_requests", []) if r.get("id") == request_id), None)
            if req is None:
                self._json({"ok": False, "error": "not found"}, status=404)
                return
            if req.get("status") != "error":
                # Only failed builds can be cleared this way -- removing a "done"
                # record would orphan its generated file and any fix history
                # pointing at it, so that's not exposed here.
                self._json({"ok": False, "error": "can only remove failed builds"}, status=400)
                return
            data["app_requests"] = [r for r in data.get("app_requests", []) if r.get("id") != request_id]
            save_data(data)
            self._json({"ok": True})

        elif path == "/api/app_requests/feedback":
            request_id = (payload.get("id") or "").strip()
            rating = (payload.get("rating") or "").strip()
            comment = (payload.get("comment") or "").strip()[:300]
            if rating not in FEEDBACK_RATINGS:
                self._json({"ok": False, "error": "invalid rating"}, status=400)
                return
            req = next((r for r in data.get("app_requests", []) if r.get("id") == request_id), None)
            if req is None or req.get("status") != "done" or req.get("kind", "build") != "build":
                self._json({"ok": False, "error": "not found or not ready"}, status=404)
                return
            req["feedback"] = {"rating": rating, "comment": comment, "submitted_at": now_iso()}
            save_data(data)
            notify_feedback_async(req.get("requester_name", ""), rating, comment, request_id)
            self._json({"ok": True})

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
    with data_lock():
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

    # Kick off review for anything still unreviewed from before this startup --
    # e.g. a note added while the server was down, or one left pending by an
    # older build that predates real-time review.
    pending_notes = []
    for note in data.get("notes", []):
        if not note.get("reviewed"):
            pending_notes.append((note.get("id"), None))
        for r in note.get("replies", []):
            if not r.get("reviewed"):
                pending_notes.append((note.get("id"), r.get("id")))
    for note_id, reply_id in pending_notes:
        threading.Thread(target=review_note_worker, args=(note_id, reply_id), daemon=True).start()
    if pending_notes:
        print(f"[notes] kicked off review for {len(pending_notes)} note item(s) pending from before startup")

    print(f"""
+----------------------------------------------+
|            AppVerse Local Server             |
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
