#!/usr/bin/env python3
"""arcade_weekly.py - play every public Games Arcade tile once a week (13 Oct 2026).

The nightly new_app_check.py plays NEW apps; nothing re-played the 64 public tiles after
an edit. This runs arcade_play_check.js (every tile, through the catalog, phone + tablet),
saves test_reports/arcade-weekly.json and a line in arcade-weekly.log, and sends tile
names and results to the house status page - the URLs in test_reports/report-to.txt
(gitignored; this repo is public), with /door/apps swapped for /door/arcade.

    python arcade_weekly.py                 every tile (~55 min)
    python arcade_weekly.py "^party-simon"  just the matching tile ids
Runs from the "CoworkApps-ArcadeWeekly" scheduled task (pythonw, no window).
"""
import json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "test_reports")
OUT = os.path.join(REPORTS, "arcade-weekly.json")
LOG = os.path.join(REPORTS, "arcade-weekly.log")
REPORT_TO = os.path.join(REPORTS, "report-to.txt")
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
NO_WINDOW = 0x08000000


def log(msg):
    os.makedirs(REPORTS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def main():
    root = os.environ.get("ARCADE_ROOT") or os.path.dirname(HERE)      # a throwaway copy, for tests
    args = [NODE, os.path.join(HERE, "arcade_play_check.js"), root] + sys.argv[1:2]
    r = subprocess.run(args, cwd=HERE, capture_output=True, text=True, encoding="utf-8",
                       timeout=3 * 3600, creationflags=NO_WINDOW)
    try:
        result = json.loads(r.stdout)
    except ValueError:
        log("checker failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return 1
    json.dump(result, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    bad = [t for t in result["tiles"] if not t["ok"]]
    log("played %d tiles, %d need a look%s" % (len(result["tiles"]), len(bad),
        (": " + ", ".join(t["name"] for t in bad)) if bad else ""))

    if sys.argv[1:2] and not os.environ.get("ARCADE_POST"):   # a partial run doesn't speak for the whole Arcade
        return 0
    body = json.dumps({"tiles": len(result["tiles"]),
                       "broken": [{"name": t["name"][:60], "problems": [p[:200] for p in t["problems"][:4]]}
                                  for t in bad[:20]]}).encode()
    try:
        urls = [u.strip().replace("/door/apps", "/door/arcade") for u in open(REPORT_TO, encoding="utf-8")
                if u.strip() and not u.startswith("#")]
    except OSError:
        urls = []
    for url in urls:
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST",
                                   headers={"Content-Type": "application/json"}), timeout=5).read()
            break
        except Exception:
            continue
    else:
        if urls:
            log("the status page didn't answer - not updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
