#!/usr/bin/env python3
"""
daily_check.py -- Daily AI review of Cowork Apps notes.
Reads unreviewed notes, asks Claude to analyze each one, saves responses.
Scheduled via Windows Task Scheduler (see Setup-DailyCheck.ps1).
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

APPS_DIR  = Path(__file__).parent
DATA_FILE = APPS_DIR / ".app_data.json"
LOG_FILE  = APPS_DIR / "daily_check.log"


def log(msg):
    ts   = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ask_claude(prompt):
    """Call the Claude Code CLI. Returns (response_text, success: bool).

    This job only ever needs a text answer -- it must NOT be able to touch the
    filesystem or run commands. The prompt embeds untrusted note text (added by
    anyone via the web UI), and the user's global settings.json pre-approves
    mcp-coderunner (shell) and mcp-filesystem (write/delete). A plain `claude -p`
    would inherit those, turning a malicious note into arbitrary code execution.
    So we launch hermetically: --strict-mcp-config with an empty --mcp-config
    loads NO MCP servers, and the empty allow / explicit disallow lists deny
    every built-in tool. The model can produce text and nothing else.
    """
    try:
        result = subprocess.run(
            ["claude", "-p", prompt,
             "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}',
             "--allowedTools", "",
             "--disallowedTools",
             "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
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


def load_data_file():
    """Read .app_data.json with a try/except. Returns dict or None on failure."""
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Could not read data file: {e}")
        return None


def save_data_atomic(data):
    """Write data atomically via temp file + os.replace to avoid corruption on kill."""
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def update_note(note_id, reviewed_at, response):
    """Re-read the data file, update one note, write back atomically.

    Re-reading before each write avoids clobbering changes the HTTP server
    made while Claude was processing the previous note.
    """
    data = load_data_file()
    if data is None:
        log(f"  Skipping save for note {note_id} -- data file unreadable")
        return
    for note in data.get("notes", []):
        if note.get("id") == note_id:
            note["reviewed"]    = True
            note["ai_response"] = response
            note["reviewed_at"] = reviewed_at
            break
    save_data_atomic(data)


def discover_app_names():
    """Return a list of app display names for Claude context."""
    ignore = {"node_modules", "test_reports", ".playwright-mcp", ".claude", "Reviews"}
    names = []
    for html in sorted(APPS_DIR.rglob("*.html")):
        if any(p.name in ignore for p in html.parents):
            continue
        name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", html.stem)
        name = name.replace("-", " ").replace("_", " ").title()
        names.append(name)
    return names


def main():
    log("=" * 50)
    log("Daily Cowork Apps Check starting")

    if not DATA_FILE.exists():
        log("No .app_data.json found -- nothing to review.")
        return

    data = load_data_file()
    if data is None:
        log("Aborting -- data file could not be parsed.")
        return

    notes = data.get("notes", [])
    unreviewed = [n for n in notes if not n.get("reviewed")]

    if not unreviewed:
        log(f"No unreviewed notes ({len(notes)} total). All done.")
        log("=" * 50)
        return

    app_list = ", ".join(discover_app_names()[:20])
    log(f"Found {len(unreviewed)} unreviewed note(s) of {len(notes)} total")

    reviewed_count = 0
    for note in unreviewed:
        note_id = note.get("id", "")
        text    = note.get("text", "").strip()
        log(f"Reviewing: {text[:80]}{'...' if len(text) > 80 else ''}")

        prompt = (
            "You are an AI assistant reviewing developer notes for a local web app collection "
            "called 'Cowork Apps' -- self-contained HTML apps stored at "
            "D:\\Documents\\Claude Local\\cowork apps\\ covering kids games, music, "
            "puzzles, education, art, and productivity.\n\n"
            f"Current apps: {app_list}\n\n"
            f"Developer note: \"{text}\"\n\n"
            "Provide a concise, actionable response (2-5 sentences). "
            "For bug reports: suggest how to investigate and fix. "
            "For feature ideas: assess feasibility and outline an approach. "
            "For questions: answer directly. "
            "Be specific -- reference actual file names or code patterns if relevant."
        )

        response, success = ask_claude(prompt)

        if success:
            reviewed_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            update_note(note_id, reviewed_at, response)
            reviewed_count += 1
            log(f"Response saved ({len(response)} chars)")
        else:
            log(f"Claude failed for note {note_id}, leaving pending: {response[:120]}")

    log(f"Completed: {reviewed_count}/{len(unreviewed)} note(s) reviewed.")
    log("=" * 50)


if __name__ == "__main__":
    main()