#!/usr/bin/env python3
"""new_app_check.py - the nightly check of NEW Cowork apps (13 Oct 2026).

New apps arrive almost daily and sat unplayed until someone checked them by
hand; of the five from 9-10 Oct, two were broken in ways a load test misses.
This finds every app that is new or changed since the last commit (git status
on the repo that holds this folder), skips any it already checked unchanged,
plays the rest with smoke_new_apps.js, and:

  test_reports/new-apps.json      every app waiting to be committed, with its result
  test_reports/new-apps.log       one line per run
  the house status page           POST <url>/door/apps - titles and results only,
                                  best effort, never fails the run. The URLs live in
                                  test_reports/report-to.txt (one per line, gitignored -
                                  this repo is public); no file, no report.

    python new_app_check.py            check what's new
    python new_app_check.py --all-again  re-check every waiting app, changed or not

An app leaves the list when it's committed - i.e. once someone has looked at it.
Runs from the "CoworkApps-NewAppCheck" scheduled task (pythonw, no window).
"""
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REPORTS = os.path.join(HERE, "test_reports")
STATE = os.path.join(REPORTS, "new-apps.json")
LOG = os.path.join(REPORTS, "new-apps.log")
REPORT_TO = os.path.join(REPORTS, "report-to.txt")
SKIP_DIRS = ("test_reports/", "node_modules/", "review-kit/", "_retired_launchers/", "_scheduler/",
             "test_results/", "test-results/", "test_screenshots/", "surface-setup/")
NO_WINDOW = 0x08000000
# the scheduled task's PATH can be thinner than a terminal's
NODE = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
GIT = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"


def log(msg):
    os.makedirs(REPORTS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def waiting_apps():
    """HTML files in this folder that git calls new (??) or modified ( M / M ), as paths
    relative to this folder."""
    folder = os.path.relpath(HERE, REPO).replace(os.sep, "/")
    r = subprocess.run([GIT, "-C", REPO, "status", "--porcelain", "--untracked-files=all", "--", folder],
                       capture_output=True, text=True, encoding="utf-8", creationflags=NO_WINDOW)
    if r.returncode:        # an empty answer would read as "nothing waiting" - say so instead
        raise RuntimeError("git status failed: " + r.stderr.strip()[-200:])
    out = []
    for line in r.stdout.splitlines():
        code, p = line[:2], line[3:].strip().strip('"')
        if "D" in code or not p.lower().endswith(".html"):
            continue
        if "->" in p:                                   # a rename: "old -> new"
            p = p.split("->")[-1].strip().strip('"')
        rel = p[len(folder) + 1:] if p.startswith(folder + "/") else p
        if rel.startswith(SKIP_DIRS) or "/" not in rel:   # loose files in the root aren't apps
            continue
        out.append(rel)
    return sorted(set(out))


def sha(rel):
    return hashlib.sha1(open(os.path.join(HERE, rel), "rb").read()).hexdigest()


def main():
    try:
        state = json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        state = {"apps": {}}
    known = state.get("apps", {})
    try:
        waiting = waiting_apps()
    except (OSError, RuntimeError) as e:
        log(str(e))
        return 1
    redo = "--all-again" in sys.argv
    todo = [a for a in waiting if redo or known.get(a, {}).get("sha") != sha(a)]

    if todo:
        r = subprocess.run([NODE, os.path.join(HERE, "smoke_new_apps.js")] + todo, cwd=HERE,
                           capture_output=True, text=True, encoding="utf-8", timeout=60 * (2 + 2 * len(todo)),
                           creationflags=NO_WINDOW)
        try:
            result = json.loads(r.stdout)
        except ValueError:
            log("checker failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
            return 1
        for a in result["apps"]:
            known[a["app"]] = {"sha": sha(a["app"]), "title": a["title"], "ok": a["ok"],
                               "problems": a["problems"], "checked": result["checked_at"]}

    # only apps still waiting to be committed stay on the list
    known = {k: v for k, v in known.items() if k in waiting}
    state = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "apps": known}
    json.dump(state, open(STATE, "w", encoding="utf-8"), indent=1)
    bad = [v["title"] for v in known.values() if not v["ok"]]
    log("checked %d new/changed, %d waiting in all, %d need a look%s"
        % (len(todo), len(known), len(bad), (": " + ", ".join(bad)) if bad else ""))

    report = {"run_at": state["run_at"],
              "apps": [{"title": v["title"][:80], "app": k[:160], "ok": v["ok"],
                        "problems": [p[:200] for p in v["problems"][:4]]} for k, v in sorted(known.items())]}
    body = json.dumps(report).encode()
    try:
        urls = [u.strip() for u in open(REPORT_TO, encoding="utf-8") if u.strip() and not u.startswith("#")]
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
