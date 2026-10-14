#!/usr/bin/env python3
"""new_app_check.py - the nightly check of NEW Cowork apps (13 Oct 2026).

New apps arrive almost daily and sat unplayed until someone checked them by
hand; of the five from 9-10 Oct, two were broken in ways a load test misses.
This plays, with smoke_new_apps.js, every app that is
  - NEW: made in the last RECENT_DAYS days (date in the file name, or changed since),
    in ANY folder - the routines make ~20 a day, mostly in private (gitignored)
    folders that git status never shows; the first version only saw ~1 in 10, or
  - WAITING: new or changed since the last commit in a public folder (git status),
skipping any it already played unchanged (by hash), and writes:

  test_reports/new-apps.json      every app still new or waiting, with its result
  Reviews/review-<date>.md        a "Played" section under that day's code-reading
                                  review (it can't run the apps; on 10 Oct it passed
                                  Ricochet Arena, which hit GAME OVER on its own)
  test_reports/new-apps.log       one line per run
  the house status page           POST <url>/door/apps - titles and results only,
                                  best effort, never fails the run. The URLs live in
                                  test_reports/report-to.txt (one per line, gitignored -
                                  this repo is public); no file, no report.

    python new_app_check.py            check what's new
    python new_app_check.py --all-again  re-play every new/waiting app, changed or not

A public app leaves the list when it's committed - i.e. once someone has looked at
it; a private one when it's older than RECENT_DAYS. Public waiting apps that passed also get ONE waiting SHIP IT step, "put these on the Games Arcade"
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
             "test_results/", "test-results/", "test_screenshots/", "surface-setup/", "Reviews/",
             "vr_prompts/", "__pycache__/")
RECENT_DAYS = 3                 # covers a night or two with the desktop asleep
BATCH = 8                       # apps per browser run; progress is saved after each
REVIEWS = os.path.join(HERE, "Reviews")
MARK = "<!-- played by new_app_check.py -->"
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


def recent_apps():
    """Every app made in the last RECENT_DAYS days, in any folder (private ones too)."""
    days = {time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)) for i in range(RECENT_DAYS)}
    cutoff = time.time() - RECENT_DAYS * 86400
    out = []
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__")]
        for f in files:
            if not f.lower().endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(root, f), HERE).replace(os.sep, "/")
            if "/" not in rel or rel.startswith(SKIP_DIRS):
                continue
            if f[:10] in days or os.path.getmtime(os.path.join(root, f)) >= cutoff:
                out.append(rel)
    return sorted(out)


def private(rels):
    """The ones in gitignored folders - never published, never offered to the Arcade."""
    folder = os.path.relpath(HERE, REPO).replace(os.sep, "/")
    r = subprocess.run([GIT, "-C", REPO, "check-ignore", "--stdin"], input="\n".join(folder + "/" + x for x in rels),
                       capture_output=True, text=True, encoding="utf-8", creationflags=NO_WINDOW)
    return {ln.strip()[len(folder) + 1:] for ln in r.stdout.splitlines() if ln.strip()}


def play(apps):
    r = subprocess.run([NODE, os.path.join(HERE, "smoke_new_apps.js")] + apps, cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", timeout=60 * (2 + 2 * len(apps)),
                       creationflags=NO_WINDOW)
    try:
        return json.loads(r.stdout)
    except ValueError:
        log("checker failed (exit %s): %s" % (r.returncode, (r.stderr or r.stdout)[-300:].strip()))
        return None


def note_reviews(known):
    """A "Played" section in each day's review file (Reviews/ is gitignored), replaced each run."""
    by_day = {}
    for k, v in known.items():
        day = os.path.basename(k)[:10]
        if os.path.isfile(os.path.join(REVIEWS, "review-%s.md" % day)):
            by_day.setdefault(day, []).append((k, v))
    for day, rows in by_day.items():
        path = os.path.join(REVIEWS, "review-%s.md" % day)
        text = open(path, encoding="utf-8").read()
        text = text.split("\n\n" + MARK)[0].rstrip("\n")
        lines = ["", "", MARK, "## Played (nightly check)", "",
                 "Each app loaded and played on a phone and a tablet screen: idle 15 s, then Start and 5 s of play. "
                 "Not a substitute for a person playing it; it catches what code-reading can't.", "",
                 "| App | Played | What happened |", "|---|---|---|"]
        for k, v in sorted(rows):
            what = "; ".join(v["problems"][:3] + ["accessibility: " + x for x in v.get("a11y", [])][:2]).replace("|", "/") \
                or "nothing wrong seen"
            lines.append("| %s | %s | %s |" % (os.path.basename(k), "✅ plays" if v["ok"] else "❌ broken", what[:400]))
        lines.append("")
        lines.append("*%s*" % time.strftime("played %Y-%m-%d %H:%M"))
        open(path, "w", encoding="utf-8").write(text + "\n".join(lines) + "\n")


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
    recent = recent_apps()
    every = sorted(set(waiting) | set(recent))
    hidden = private(every)
    redo = "--all-again" in sys.argv
    todo = [a for a in every if redo or known.get(a, {}).get("sha") != sha(a)]

    def save():
        json.dump({"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "apps": known},
                  open(STATE, "w", encoding="utf-8"), indent=1)

    failed = 0
    for i in range(0, len(todo), BATCH):
        result = play(todo[i:i + BATCH])
        if result is None:
            failed += 1
            continue
        for a in result["apps"]:
            known[a["app"]] = {"sha": sha(a["app"]), "title": a["title"], "ok": a["ok"],
                               "problems": a["problems"], "a11y": a.get("a11y", []), "checked": result["checked_at"]}
        save()                  # a long first run keeps what it has done
    for k, v in known.items():
        v["public"] = k not in hidden
        v["waiting"] = k in waiting

    # only apps still new, or waiting to be committed, stay on the list
    known = {k: v for k, v in known.items() if k in waiting or k in recent}
    save()
    run_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    bad = [v["title"] for v in known.values() if not v["ok"]]
    log("played %d new/changed (%d batch(es) failed), %d on the list, %d need a look%s"
        % (len(todo), failed, len(known), len(bad), (": " + ", ".join(bad)) if bad else ""))
    try:
        note_reviews(known)
    except OSError as e:
        log("couldn't add to the review files: %s" % e)

    # to the status page: how many were played, and only the ones worth a row -
    # broken ones, and public apps waiting to go on the Arcade. A waiting public app that
    # fails the accessibility scan counts as needing a look (the Arcade is kept clean);
    # private apps' accessibility only goes in the review files.
    def ready(v):
        return v["ok"] and not (v["waiting"] and v["public"] and v.get("a11y"))
    report = {"run_at": run_at, "played": len(known), "days": RECENT_DAYS,
              "apps": [{"title": v["title"][:80], "ok": ready(v), "waiting": v["waiting"],
                        "problems": [p[:200] for p in (v["problems"] + (["accessibility: " + x for x in v.get("a11y", [])]
                                                                        if v["waiting"] and v["public"] else []))[:4]]}
                       for k, v in sorted(known.items()) if not ready(v) or v["waiting"]]}
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
    queue_arcade_step({k: v for k, v in known.items() if v["waiting"] and v["public"]})
    return 1 if failed else 0


def queue_arcade_step(known):
    """Keep ONE waiting SHIP IT step, "put these on the Arcade", for the apps that passed -
    a phone tap once you've played them (add_to_arcade.py does the work). Updated each
    night; removed when nothing that passed is waiting. No ship-queue.txt, no step."""
    try:
        qpath = open(SHIP_QUEUE, encoding="utf-8").read().strip()
        q = json.load(open(qpath, encoding="utf-8"))
    except (OSError, ValueError):
        return
    ok = sorted((k, v) for k, v in known.items() if v.get("ok") and not v.get("a11y"))
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
