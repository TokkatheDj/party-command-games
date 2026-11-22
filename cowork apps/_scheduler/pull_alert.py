#!/usr/bin/env python3
"""
pull_alert.py - email Lance once a day when the Surface can't pull from GitHub (22 Nov 2026).

Why: Update-Routines.ps1 never blocks a run. When `git pull --ff-only` is refused it logs
"WARN: routines NOT updated" and the routine runs on the prompts already on disk. Nobody reads
that line: 11-14 Nov (an unpushed Surface commit) and 20-21 Nov (an unpushed commit plus 10
untracked apps) the factory ran ~64 times on stale generator prompts, and Mo Mouse (19 Nov) went
out without the saved-data rule pushed that day.

    python pull_alert.py "<the WARN line>"            send (at most once per day)
    python pull_alert.py --dry-run "<the WARN line>"  print what would be sent, change nothing
    options: --state <file> (default Logs/pull-alert-sent.txt), --repo <path>

Called by PullAlert.ps1 (Invoke-PullAlert) from Run-CoworkRoutine.ps1 after Update-Routines
returns "kept". Never raises: a missing email_config.json or an SMTP error is printed and the
exit code is still 0, so a factory run is never affected. Uses serve_apps.load_email_config()
and the same SMTP settings as the AppVerse note emails (email_config.json, gitignored).
"""
import argparse
import datetime
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.dirname(HERE)                      # ...\cowork apps
REPO = os.path.dirname(APPS)                      # ...\Claude Local
DEFAULT_STATE = os.path.join(HERE, "Logs", "pull-alert-sent.txt")


def classify(warn):
    """(skip, cause, fix) for a WARN line from Update-Routines.ps1."""
    w = warn or ""
    if "another run held the pull" in w:
        return True, "another routine was pulling at the same moment", ""   # clears itself on the next run
    if "Diverging branches" in w or "Not possible to fast-forward" in w:
        return (False, "the Surface has a commit of its own that was never pushed to GitHub",
                "On the Surface, in Claude Local: `git fetch`, then `git rebase origin/master` "
                "(or cherry-pick the local commit onto origin/master) and `git push`. Check what "
                "the local commit is first: `git log origin/master..master`.")
    if "untracked file(s) differ" in w or "untracked working tree files would be overwritten" in w:
        return (False, "untracked files on the Surface are in the way, and they differ from GitHub's copies",
                "Compare each listed file with GitHub's (`git diff --no-index <(git show origin/master:<path>) <path>`). "
                "GitHub's copy usually carries fixes; back the local ones up, remove those GitHub has, "
                "commit the rest, push.")
    if "uncommitted" in w.lower() or "local changes" in w.lower():
        return (False, "uncommitted edits on the Surface are in the way",
                "On the Surface, in Claude Local: `git status`, then commit or stash the edits and pull.")
    return (False, "git pull was refused or failed (see the line below)",
            "On the Surface, in Claude Local: `git status -sb` and `git pull --ff-only` to see the full message.")


def ahead_behind(repo):
    try:
        out = subprocess.run(["git", "-C", repo, "rev-list", "--left-right", "--count", "HEAD...@{u}"],
                             capture_output=True, text=True, timeout=20).stdout.split()
        return int(out[0]), int(out[1])
    except Exception:
        return None, None


def already_sent_today(state, today):
    try:
        with open(state, encoding="utf-8") as f:
            return f.read().strip().startswith(today)
    except OSError:
        return False


def build_message(warn, cause, fix, ahead, behind, to_email, from_addr, from_name):
    msg = EmailMessage()
    msg["Subject"] = "Cowork factory: the Surface can't pull from GitHub - routines are using old prompts"
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_email
    ab = "" if ahead is None else f"\nThe Surface is {ahead} commit(s) ahead and {behind} behind GitHub.\n"
    msg.set_content(
        "The Surface's cowork apps factory could not update from GitHub before a routine ran, so it is "
        "making apps with the generator prompts already on disk. Any prompt change pushed since then "
        "(new rules, fixes) is being missed until this is cleared.\n"
        f"\nCause: {cause}.\n{ab}"
        f"\nHow to clear it:\n{fix}\n"
        f"\nThe log line:\n{warn}\n"
        "\nThis is sent at most once a day; it stops by itself once a pull succeeds. "
        "Sent by cowork apps/_scheduler/pull_alert.py.\n"
    )
    return msg


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("warn")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--repo", default=REPO)
    a = ap.parse_args(argv)
    try:
        skip, cause, fix = classify(a.warn)
        if skip:
            print(f"pull_alert: not sent ({cause})")
            return 0
        today = datetime.date.today().isoformat()
        if already_sent_today(a.state, today):
            print(f"pull_alert: not sent (already sent today, {a.state})")
            return 0
        ahead, behind = ahead_behind(a.repo)
        if a.dry_run:
            m = build_message(a.warn, cause, fix, ahead, behind, "<owner_email>", "<smtp_user>", "AppVerse")
            print("pull_alert: DRY RUN, would send:\nSubject: " + m["Subject"] + "\n\n" + m.get_content())
            return 0
        sys.path.insert(0, APPS)
        from serve_apps import load_email_config          # same config as the AppVerse note emails
        cfg = load_email_config()
        if not cfg or not cfg.get("owner_email"):
            print("pull_alert: not sent (email_config.json missing, incomplete, or no owner_email)")
            return 0
        msg = build_message(a.warn, cause, fix, ahead, behind, cfg["owner_email"], cfg["smtp_user"],
                            cfg.get("from_name", "AppVerse"))
        with smtplib.SMTP(cfg["smtp_host"], cfg.get("smtp_port", 587), timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["smtp_user"], cfg["smtp_app_password"])
            smtp.send_message(msg)
        os.makedirs(os.path.dirname(a.state), exist_ok=True)
        with open(a.state, "w", encoding="utf-8") as f:
            f.write(f"{today} {datetime.datetime.now().strftime('%H:%M:%S')} {cause}\n")
        print("pull_alert: sent")
    except Exception as e:                                # never break a factory run
        print(f"pull_alert: failed to send: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
