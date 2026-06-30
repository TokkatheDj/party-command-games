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
import time
import uuid
import os
from pathlib import Path
from urllib.parse import unquote

APPS_DIR = Path(__file__).parent
PORT = 8080
DATA_FILE = APPS_DIR / ".app_data.json"

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
    defaults = {"favorites": [], "ratings": {}, "removed": [], "opened": [], "notes": [], "playlists": {}}
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

    qr_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=180x180&data={base_url}&margin=10"
    )
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
  .qr-section {{ display: flex; align-items: center; justify-content: center; gap: 1.2rem; background: rgba(124,110,230,0.08); border: 1px solid rgba(124,110,230,0.3); border-radius: 12px; padding: 1rem 1.5rem; max-width: 480px; margin: 0 auto 1.5rem; }}
  .qr-section img {{ border-radius: 8px; background: white; padding: 4px; }}
  .qr-text {{ text-align: left; }}
  .qr-text p {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 0.3rem; }}
  .qr-url {{ font-family: monospace; font-size: 1rem; color: var(--accent); font-weight: 600; word-break: break-all; }}
  .qr-hint {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.4rem; }}
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
</style>
</head>
<body>
<header>
  <h1>Cowork Apps</h1>
  <p class="subtitle">{app_count} apps &middot; {review_count} {review_label}</p>
  <div class="qr-section">
    <img src="{qr_url}" width="80" height="80" alt="QR" onerror="this.style.display='none'">
    <div class="qr-text">
      <p>Scan or visit on your device:</p>
      <div class="qr-url">{base_url}</div>
      <p class="qr-hint">Requires Tailscale on your device</p>
    </div>
  </div>
  <div class="tabs-nav">
    <button class="tab-btn active" data-tab="apps">&#128241; Apps ({app_count})</button>
    <button class="tab-btn" data-tab="reviews">&#11088; Reviews ({review_count})</button>
    <button class="tab-btn" data-tab="notes">&#128203; Notes {notes_tab_label}</button>
    <button class="tab-btn" data-tab="playlists">&#128204; Lists ({playlist_count})</button>
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


def make_manifest(base_url):
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
            ip = get_local_ip()
            base_url = f"http://{ip}:{PORT}"
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
        elif path == "/manifest.json":
            ip = get_local_ip()
            data = make_manifest(f"http://{ip}:{PORT}").encode("utf-8")
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
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
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
                "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
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

    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), AppHandler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped.")


if __name__ == "__main__":
    main()
