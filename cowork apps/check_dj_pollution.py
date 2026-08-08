#!/usr/bin/env python3
"""
check_dj_pollution.py -- scheduled recurrence check for the dj_music_apps
display-name pollution (see Cleanup-DjMusicPollution.ps1).

Runs the cleanup script in DRY-RUN, decides clean vs. polluted from its output,
appends to dj_pollution_check.log, and -- only when the state flips to polluted --
writes dj_pollution_ALERT.txt and emails the owner (email_config.json). Clears the
alert when clean again. Exit codes: 0 clean, 1 pollution present, 2 inconclusive.
"""
import os, re, sys, json, time, shutil, subprocess, smtplib
from email.message import EmailMessage
from pathlib import Path

HERE      = Path(__file__).resolve().parent
CLEANUP   = HERE / "Cleanup-DjMusicPollution.ps1"
LOG       = HERE / "dj_pollution_check.log"
ALERT     = HERE / "dj_pollution_ALERT.txt"
EMAIL_CFG = HERE / "email_config.json"


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[{}] {}".format(ts, msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_powershell():
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return exe
    return None


def run_dryrun():
    ps = find_powershell()
    if not ps:
        log("ERROR: neither pwsh nor powershell found on PATH")
        return None
    if not CLEANUP.exists():
        log("ERROR: cleanup script not found at {}".format(CLEANUP))
        return None
    try:
        r = subprocess.run(
            [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CLEANUP), "-Root", str(HERE)],
            capture_output=True, text=True, timeout=300)
        return (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception as e:
        log("ERROR running cleanup dry-run: {}".format(e))
        return None


def parse(out):
    n = 0
    m = re.search(r"Files to relocate\s*:\s*(\d+)", out)
    if m:
        n = int(m.group(1))
    unknown = []
    m = re.search(r"UNRECOGNIZED subfolders in dj_music_apps[^:]*:\s*(.+)", out)
    if m:
        unknown = [s.strip() for s in m.group(1).split(",") if s.strip()]
    return n, unknown


def send_email(subject, body):
    if not EMAIL_CFG.exists():
        log("no email_config.json -- skipping email (marker/log only)")
        return
    try:
        cfg = json.load(open(EMAIL_CFG, encoding="utf-8"))
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = "{} <{}>".format(cfg.get("from_name", "Cowork Apps"), cfg["smtp_user"])
        msg["To"] = cfg["owner_email"]
        msg.set_content(body)
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587)), timeout=30) as s:
            s.starttls()
            s.login(cfg["smtp_user"], cfg["smtp_app_password"])
            s.send_message(msg)
        log("alert email sent to {}".format(cfg["owner_email"]))
    except Exception as e:
        log("ERROR sending email: {}".format(e))


def main():
    host = os.environ.get("COMPUTERNAME", "this machine")
    out = run_dryrun()
    if out is None:
        log("inconclusive -- could not run the dry-run; leaving any existing alert in place")
        sys.exit(2)

    n, unknown = parse(out)
    polluted = (n > 0) or bool(unknown)

    if not polluted:
        log("clean -- dj_music_apps has no pollution ({})".format(host))
        if ALERT.exists():
            ALERT.unlink()
            log("cleared previous ALERT marker (pollution resolved)")
        sys.exit(0)

    detail = "{} file(s) to relocate".format(n)
    if unknown:
        detail += "; unrecognized subfolders: {}".format(", ".join(unknown))
    log("POLLUTION DETECTED on {} -- {}".format(host, detail))

    already = ALERT.exists()
    with open(ALERT, "w", encoding="utf-8") as f:
        f.write("dj_music_apps pollution detected {} on {}\n{}\n\n".format(
            time.strftime("%Y-%m-%d %H:%M:%S"), host, detail))
        f.write("Fix -- run in {}:\n  pwsh -File Cleanup-DjMusicPollution.ps1 -Apply\n".format(HERE))

    if not already:
        body = (
            "The AppVerse recurrence check found the dj_music_apps pollution again.\n\n"
            "Machine : {host}\nWhen    : {when}\nDetail  : {detail}\n\n"
            "To fix, from {here}:\n"
            "  pwsh -File Cleanup-DjMusicPollution.ps1          (preview)\n"
            "  pwsh -File Cleanup-DjMusicPollution.ps1 -Apply   (relocate)\n\n"
            "Reminder: the daily generator routines are NOT the cause (each saves to its\n"
            "correct slug folder). Look for a run whose working directory was set inside\n"
            "dj_music_apps. You will not get another email until this clears and recurs.\n"
        ).format(host=host, when=time.strftime("%Y-%m-%d %H:%M:%S"), detail=detail, here=HERE)
        send_email("[AppVerse] dj_music_apps pollution detected on {}".format(host), body)
    else:
        log("ALERT marker already present -- not re-emailing (still unresolved)")

    sys.exit(1)


if __name__ == "__main__":
    main()
