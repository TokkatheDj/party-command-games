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
Apps that passed also get ONE waiting SHIP IT step, "put these on the Games Arcade"
(add_to_arcade.py; the SHIP IT list's path is in test_reports/ship-queue.txt) - tap it
once you've played them. It goes away by itself when nothing that passed is waiting.
Runs from the "CoworkApps-NewAppCheck" scheduled task (pythonw, no window).
"""
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REPORTS = os.path.join(HERE, "test_reports")
STATE = os.path.join(REPORTS, "new-apps.json")
LOG = os.path.join(REPORTS, "new-apps.log")
REPORT_TO = os.path.join(REPORTS, "report-to.txt")
SHIP_QUEUE = os.path.join(REPORTS, "ship-queue.txt")   # path of the SHIP IT list (your-turn.json); gitignored
ARCADE = "https://tokkathedj.github.io/party-command-games/"
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
    queue_arcade_step(known)
    return 0


def queue_arcade_step(known):
    """Keep ONE waiting SHIP IT step, "put these on the Arcade", for the apps that passed -
    a phone tap once you've played them (add_to_arcade.py does the work). Updated each
    night; removed when nothing that passed is waiting. No ship-queue.txt, no step."""
    try:
        qpath = open(SHIP_QUEUE, encoding="utf-8").read().strip()
        q = json.load(open(qpath, encoding="utf-8"))
    except (OSError, ValueError):
        return
    ok = sorted((k, v) for k, v in known.items() if v.get("ok"))
    steps = [st for st in q.get("steps", []) if not (st.get("id", "").startswith("arcade-add-") and st.get("status") == "waiting")]
    if ok:
        names = ", ".join(v["title"][:40] for _, v in ok)
        steps.append({
            "id": "arcade-add-" + time.strftime("%Y-%m-%d-%H%M"),
            "title": "Put on the Games Arcade - only once you've played them: " + names,
            "why": "The nightly check played these and found nothing wrong. This commits them, adds their tiles "
                   "to the Arcade, pushes, and waits for the live site. PUBLIC.",
            "from": "new_app_check.py",
            "guard": {"cwd": HERE, "run": '"%s" add_to_arcade.py --waiting --dry' % sys.executable.replace("pythonw", "python"),
                      "explain": "something waiting didn't pass the nightly check, or nothing is waiting"},
            "commands": [{"cwd": HERE, "run": '"%s" add_to_arcade.py --waiting' % sys.executable.replace("pythonw", "python")}],
            "verify": [{"label": "%s is on the Arcade" % v["title"][:40], "type": "http", "url": ARCADE, "status": 200,
                        "contains": "src: '%s'" % "/".join(x.replace(" ", "%20") for x in k.split("/")), "patience": 120}
                       for k, v in ok],
            "status": "waiting", "done_at": None, "error": None})
    if steps == q.get("steps", []):
        return
    q["steps"] = steps
    q["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = qpath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, indent=2, ensure_ascii=False)
    os.replace(tmp, qpath)
    log("SHIP IT: %s" % ("arcade step for %d app(s)" % len(ok) if ok else "arcade step removed - nothing waiting"))


if __name__ == "__main__":
    sys.exit(main())
