#!/usr/bin/env python3
"""
daily_check.py -- Backstop AI review of AppVerse notes.

serve_apps.py now reviews notes and replies in real time as they're
submitted (review_note_worker()), emailing a notification as soon as each
one is answered. This script exists only to catch anything that stayed
unreviewed anyway -- submitted while the server was down, a headless
`claude -p` call that timed out, etc. -- via a once-a-day Task Scheduler
run. It reuses the exact same prompt-building, review-saving (including the
hardened, hermetic `claude -p` invocation and cross-process data_lock()),
and notification-email logic as the real-time path (imported from
serve_apps) so the two never drift apart.
"""
import time
from pathlib import Path

from serve_apps import (
    APPS_DIR, DATA_FILE, NOTE_REVIEW_TIMEOUT_SEC,
    load_data, build_note_prompt, build_note_reply_prompt,
    update_note_review, notify_note_async, ask_claude_note,
)

LOG_FILE = APPS_DIR / "daily_check.log"


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_pending(data):
    """Returns a list of (note_id, reply_id_or_None) for everything still
    unreviewed -- the note itself if it has no ai_response yet, plus any of
    its replies that don't either."""
    pending = []
    for note in data.get("notes", []):
        if not note.get("reviewed"):
            pending.append((note.get("id"), None))
        for r in note.get("replies", []):
            if not r.get("reviewed"):
                pending.append((note.get("id"), r.get("id")))
    return pending


def main():
    log("=" * 50)
    log("Daily Cowork Apps Check starting")

    if not DATA_FILE.exists():
        log("No .app_data.json found -- nothing to review.")
        return

    data = load_data()
    notes = data.get("notes", [])
    pending = find_pending(data)

    if not pending:
        log(f"Nothing left pending ({len(notes)} note(s) total) -- real-time review already caught everything.")
        log("=" * 50)
        return

    log(f"Found {len(pending)} item(s) still unreviewed after real-time review")

    reviewed_count = 0
    for note_id, reply_id in pending:
        # Re-read fresh each iteration: real-time review may have already
        # caught this one (or an earlier iteration's save changed the file).
        data = load_data()
        note = next((n for n in data.get("notes", []) if n.get("id") == note_id), None)
        if note is None:
            continue

        if reply_id:
            reply = next((r for r in note.get("replies", []) if r.get("id") == reply_id), None)
            if reply is None or reply.get("reviewed"):
                continue
            prompt = build_note_reply_prompt(note, reply.get("text", ""))
            snippet = reply.get("text", "")
        else:
            if note.get("reviewed"):
                continue
            prompt = build_note_prompt(note.get("text", ""))
            snippet = note.get("text", "")

        tag = f"{note_id}/{reply_id}" if reply_id else note_id
        log(f"Reviewing {tag}: {snippet[:80]}{'...' if len(snippet) > 80 else ''}")

        response, success = ask_claude_note(prompt, NOTE_REVIEW_TIMEOUT_SEC)

        if success:
            update_note_review(note_id, reply_id, response)
            notify_note_async(snippet, response, is_reply=bool(reply_id))
            reviewed_count += 1
            log(f"Response saved ({len(response)} chars)")
        else:
            log(f"Claude failed for {tag}, leaving pending: {response[:120]}")

    log(f"Completed: {reviewed_count}/{len(pending)} item(s) reviewed.")
    log("=" * 50)


if __name__ == "__main__":
    main()
