#!/usr/bin/env python3
"""arcade_weekly.py - play every public Games Arcade tile once a week (13 Oct 2026).

The nightly new_app_check.py plays NEW apps; nothing re-played the 64 public tiles after
an edit. This runs arcade_play_check.js (every tile, through the catalog, phone + tablet),
saves test_reports/arcade-weekly.json and a line in arcade-weekly.log, and sends tile
names and results to the house status page - the URLs in test_reports/report-to.txt
(gitignored; this repo is public), with /door/apps swapped for /door/arcade.

    python arcade_weekly.py                 every tile (~55 min), then the worksheet fill-in
                                            check and the phone fit check (~25 min more)
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


def blanks_check():
    """Every fill-in spot on the live maths worksheets takes typing (worksheet_blanks_check.js,
    28 Oct 2026). Returns the pages that failed, shaped like broken tiles."""
    r = subprocess.run([NODE, os.path.join(HERE, "worksheet_blanks_check.js")], cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", timeout=1800, creationflags=NO_WINDOW)
    try:
        pages = json.loads(r.stdout)["pages"]
    except (ValueError, KeyError):
        log("worksheet blanks check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Math worksheets: fill-in check", "ok": False, "problems": ["the check itself failed"]}]
    bad = [{"name": "Math worksheets: " + p["url"].split("/")[2], "ok": False,
            "problems": p.get("untypeable", []) + p.get("errors", [])} for p in pages if not p["ok"]]
    log("worksheet fill-in spots: %d pages, %s" % (len(pages), "%d need a look" % len(bad) if bad else "all typeable"))
    return bad


SUBJECTS_LIVE = ("https://tokkathedj.github.io/party-command-games/cowork%20apps/Educational%20Apps/"
                 "educational_apps/2026-10-29-guided-subject-worksheets.html")


def subjects_check():
    """Every Science/English/Art/History/Spanish worksheet on the live site can be done in student
    mode and checks answers right (subject_worksheets_check.js, built with the app 29 Oct 2026)."""
    r = subprocess.run([NODE, os.path.join(HERE, "subject_worksheets_check.js"), SUBJECTS_LIVE], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", timeout=3600, creationflags=NO_WINDOW)
    try:
        res = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        log("subject worksheets check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Subject worksheets", "ok": False, "problems": ["the check itself failed"]}]
    probs = res.get("failures", []) + ["dialog: " + d for d in res.get("dialogs", [])] + res.get("errors", [])
    log("subject worksheets: %s topics, %s problems, %s" % (res.get("topics"), res.get("problems"),
        "%d need a look" % len(probs) if probs or not res.get("ok") else "all pass"))
    return [] if res.get("ok") and not probs else [{"name": "Subject worksheets", "ok": False, "problems": probs or ["check not ok"]}]


def worksheet_a11y():
    """Every worksheet of both worksheet apps, live, passes the accessibility scan in student mode at
    phone and desktop width (worksheet_a11y_check.js, 29 Oct 2026). The nightly scan sees only an
    app's opening screen; the 29 Oct contrast slips were behind tabs."""
    r = subprocess.run([NODE, os.path.join(HERE, "worksheet_a11y_check.js")], cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", timeout=5400, creationflags=NO_WINDOW)
    try:
        pages = json.loads(r.stdout)["pages"]
    except (ValueError, KeyError):
        log("worksheet accessibility check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Worksheets: accessibility", "ok": False, "problems": ["the check itself failed"]}]
    bad = [{"name": "Worksheets accessibility: " + p["url"].split("/")[-1], "ok": False,
            "problems": p.get("issues", []) + p.get("errors", [])} for p in pages if not p["ok"]]
    log("worksheet accessibility: %d views, %s" % (sum(p.get("views", 0) for p in pages),
        "%d page(s) need a look" % len(bad) if bad else "clean"))
    return bad


def phone_fit(root):
    """Every tile and game file on a phone with its browser bars showing (phone_fit_check.js,
    28 Oct 2026). The nightly check covers NEW apps only; this catches an edit that pushes an
    existing game under the toolbar. Returns what failed, shaped like broken tiles."""
    r = subprocess.run([NODE, os.path.join(HERE, "phone_fit_check.js"), root], cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", timeout=2 * 3600, creationflags=NO_WINDOW)
    try:
        results = json.loads(r.stdout)["results"]
    except (ValueError, KeyError):
        log("phone fit check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Phone fit check", "ok": False, "problems": ["the check itself failed"]}]
    bad = [{"name": "Phone fit: %s (%s)" % (x["what"], x["how"]), "ok": False, "problems": x["problems"]}
           for x in results if not x["ok"]]
    log("phone fit: %d checks, %s" % (len(results), "%d cut off" % len(bad) if bad else "all fit"))
    return bad


NETLIFY_APPS = r"G:\My Drive\Netlify Apps"


def netlify_sites():
    """Every hand-deployed kids' site folder on Drive is whole and not older than its live site
    (predeploy_check.js, 18 Nov 2026: Carnival Games and Splashy Bubbles had Drive copies four months
    behind live, so a redeploy would have rolled them back). Needs Google Drive and the logged-in
    netlify CLI; skips with a log line if Drive isn't there."""
    if not os.path.isdir(NETLIFY_APPS):
        log("deploy folders: skipped - %s isn't there (Google Drive not running?)" % NETLIFY_APPS)
        return []
    r = subprocess.run([NODE, os.path.join(HERE, "predeploy_check.js"), "--all", NETLIFY_APPS, "--json"], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", timeout=1800, creationflags=NO_WINDOW)
    try:
        sites = json.loads(r.stdout[r.stdout.index("{"):])["sites"]
    except ValueError:
        log("deploy folder check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Deploy folders check", "ok": False, "problems": ["the check itself failed"]}]
    bad = [{"name": "Deploy folder %s: %s" % (s["name"], s["status"]), "ok": False, "problems": s["problems"]}
           for s in sites if s["status"] in ("ROLLBACK", "NOT WHOLE", "UNKNOWN")]
    log("deploy folders: %d sites, %s" % (len(sites), "%d need a look" % len(bad) if bad else "all safe to deploy"))
    return bad


def controllers():
    """Game controllers still work on the live Games Arcade (every tile) and Amigo Arcade, and every
    copy of pad.js matches cowork apps/pad.js (controller_check.js, 19 Nov 2026). Returns what failed,
    shaped like broken tiles."""
    r = subprocess.run([NODE, os.path.join(HERE, "controller_check.js")], cwd=HERE, capture_output=True,
                       text=True, encoding="utf-8", timeout=3600, creationflags=NO_WINDOW)
    try:
        res = json.loads(r.stdout[r.stdout.index("{"):])
    except ValueError:
        log("controller check failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return [{"name": "Controller check", "ok": False, "problems": ["the check itself failed"]}]
    bad = [{"name": "Controller: %s - %s" % (c["site"], c["name"]), "ok": False, "problems": [c["detail"]] if c["detail"] else []}
           for c in res["checks"] if not c["ok"]]
    bad += [{"name": "Controller: Games Arcade tile " + t["id"], "ok": False, "problems": [t["problem"]]}
            for t in res["tiles"] if not t["ok"]]
    bad += [{"name": "Controller: pad.js copy on the " + d["copy"] + " differs from cowork apps/pad.js", "ok": False,
             "problems": ["sha " + d["sha"]]} for d in res["drift"] if not d["ok"]]
    log("controllers: %d checks, %d tiles, %d pad.js copies, %s" % (len(res["checks"]), len(res["tiles"]), len(res["drift"]),
        "%d need a look" % len(bad) if bad else "all working"))
    return bad


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
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    bad = [t for t in result["tiles"] if not t["ok"]]
    if not sys.argv[1:2]:
        bad += blanks_check() + subjects_check() + worksheet_a11y() + netlify_sites() + controllers()
        bad += phone_fit(root)
    log("played %d tiles, %d need a look%s" % (len(result["tiles"]), len(bad),
        (": " + ", ".join(t["name"] for t in bad)) if bad else ""))

    if sys.argv[1:2] and not os.environ.get("ARCADE_POST"):   # a partial run doesn't speak for the whole Arcade
        return 0
    body = json.dumps({"tiles": len(result["tiles"]),
                       "broken": [{"name": t["name"][:60], "problems": [p[:200] for p in t["problems"][:4]]}
                                  for t in bad[:20]]}).encode()
    try:
        with open(REPORT_TO, encoding="utf-8") as f:
            urls = [u.strip().replace("/door/apps", "/door/arcade") for u in f
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
