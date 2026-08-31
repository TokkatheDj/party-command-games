"""Extract a snapshot of the cowork-apps factory for the App Factory Floor dashboard."""
import json, re, pathlib, collections, datetime
import pathlib as _pl
# Paths are derived from this file's location so the folder can be moved or the
# repo cloned elsewhere. dashboard/ -> _scheduler/ -> cowork apps/
HERE = _pl.Path(__file__).resolve().parent
COWORK = HERE.parent.parent

ROOT = COWORK
REG = ROOT / "_scheduler" / "Registry"
LOGS = ROOT / "_scheduler" / "Logs"
MANIFEST = ROOT / "_scheduler" / "manifest.json"

QUARANTINE = "dj_music_apps"

# Folder keys are internal vocabulary. The page is public, so it shows readable
# names; the raw folder stays available as a tooltip for operating the thing.
CAT_LABEL = {
    "action_games": "Action Games",
    "adult_puzzle_apps": "Adult Puzzles",
    "art_apps": "Art",
    "card_games_apps": "Card Games",
    "classroom_tools": "Classroom Tools",
    "Content Creation Apps/adult_apps": "Content Creation · Adults",
    "Content Creation Apps/kid_apps": "Content Creation · Kids",
    "Content Creation Apps/teen_apps": "Content Creation · Teens",
    "Cooking Games": "Cooking Games",
    "Crafts": "Crafts",
    "custom_apps": "Custom Apps",
    "data_visualization_apps": "Data & Visualisation",
    "dj_music_apps": "DJ & Music",
    "Educational Apps": "Educational",
    "fashion_apps": "Fashion",
    "health_productivity_apps": "Health & Productivity",
    "Inspirational": "Inspirational",
    "kids_apps": "Kids Games",
    "music_apps": "Music",
    "music_game_apps": "Music Games",
    "Music Production": "Music Production",
    "party_apps": "Party Games",
    "Shooting Games": "Shooting Games",
    "sports_games_apps": "Sports Games",
    "table_games_apps": "Table Games",
    "therapy_apps": "Therapy & Wellbeing",
}


def catlabel(key):
    if key in CAT_LABEL:
        return CAT_LABEL[key]
    # Fallback so a folder added later still reads sensibly.
    tail = key.split("/")[-1].replace("_apps", "").replace("_", " ")
    return tail.title()

# routine safeName -> registry category key (matches Rebuild-Registry.ps1 output)
ROUTINE_CAT = {
    "Adult-puzzles": "adult_puzzle_apps", "Action-games-generator": "action_games",
    "Card-games": "card_games_apps", "Therapy-app-maker": "therapy_apps",
    "Party-games": "party_apps", "Table-games-prompt": "table_games_apps",
    "Music-app-developer": "music_apps", "Classroom-apps": "classroom_tools",
    "Kids-content-creation": "Content Creation Apps/kid_apps",
    "Shooting-games": "Shooting Games", "Kids-game-developer": "kids_apps",
    "Music-games-generator": "music_game_apps",
    "Teen-content-creation": "Content Creation Apps/teen_apps",
    "Adult-content-creation": "Content Creation Apps/adult_apps",
    "Cooking-app": "Cooking Games", "Crafts-apps-generator": "Crafts",
}

# ---------- registry ----------
rows = []
for line in (REG / "ALL-CONCEPTS.tsv").read_text(encoding="utf-8").splitlines():
    if line.startswith("#") or not line.strip():
        continue
    p = line.split("\t")
    if len(p) >= 4:
        rows.append({"date": p[0], "cat": p[1], "slug": p[2], "concept": p[3]})

undated = [r for r in rows if r["date"] == "-"]
counts = collections.Counter(r["cat"] for r in rows)

months = collections.Counter(r["date"][:7] for r in rows if r["date"] != "-")

missing = [l for l in (REG / "_MISSING.txt").read_text(encoding="utf-8").splitlines()
           if l and not l.startswith("#")]

# ---------- schedule + last-run health ----------
manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))

# Which routines were ACTUALLY rescheduled? Derive it from the pre-change manifest
# backup rather than guessing from log times -- a manual test run or a weekly
# catch-up run otherwise looks like a reschedule.
prev = {}
baks = sorted(MANIFEST.parent.glob("manifest.json.bak-*"))
if baks:
    for e in json.loads(baks[-1].read_text(encoding="utf-8-sig")):
        prev[e["safeName"]] = e["localAt"]
MOVED = {m["safeName"]: prev.get(m["safeName"])
         for m in manifest
         if prev.get(m["safeName"]) and prev[m["safeName"]] != m["localAt"]}

START_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}\s+=== START")
# The START line records the run's turn budget. A run launched with a non-standard
# budget was a hand test, not a scheduled run -- it must not count as routine health.
BUDGET_RE = re.compile(r"max-turns (\d+)")
# 40 = the old wrapper default, 60 = the current one. Anything else was a hand test.
STD_TURNS = {40, 60}
DONE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}\s+=== DONE .*?elapsed=(\d+)s")

routines = []
for m in manifest:
    name = m["safeName"]
    log = LOGS / f"{name}.log"
    out = LOGS / f"{name}.out.txt"
    last_date = last_time = None
    elapsed = None
    state = "unknown"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        # Take the LAST run block only, and read date, time and outcome all from it,
        # so the timestamp and the status can never come from different runs.
        starts = [i for i, l in enumerate(lines) if START_RE.match(l)]
        # Walk back to the most recent run that used the standard turn budget.
        scheduled = []
        for i in starts:
            b = BUDGET_RE.search(lines[i])
            if (not b) or int(b.group(1)) in STD_TURNS:
                scheduled.append(i)
        starts = scheduled
        if starts:
            i = starts[-1]
            s = START_RE.match(lines[i])
            last_date, last_time = s.group(1), s.group(2)
            # Stop at the next START so elapsed/status belong to THIS run only --
            # otherwise a later hand-test's DONE line leaks its elapsed in here.
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if START_RE.match(lines[j]):
                    end = j
                    break
            block = "\n".join(lines[i:end])
            for l in lines[i:end]:
                d = DONE_RE.match(l)
                if d:
                    elapsed = int(d.group(3))
            if "Reached max turns" in block:
                state = "max-turns"
            elif "session limit" in block:
                state = "session-limit"
            elif "degraded=" in block:
                state = "degraded"
            elif "=== DONE" in block:
                state = "ok"
            elif "TIMEOUT" in block:
                state = "timeout"
            else:
                state = "running"

    # A routine moved to a new time has not yet run there -- never show that as a
    # failure. "Pending" only until it actually runs at the new hour.
    moved_from = MOVED.get(name)
    rescheduled = bool(moved_from and not (last_time and last_time[:2] == m["localAt"][:2]))

    routines.append({
        "name": name,
        "label": m["name"],
        "at": m["localAt"],
        "trigger": m["triggerType"],
        "dow": m.get("localDow"),
        "cat": ROUTINE_CAT.get(name),
        "catLabel": catlabel(ROUTINE_CAT[name]) if name in ROUTINE_CAT else None,
        "kind": "generator" if name in ROUTINE_CAT else "review",
        "lastDate": last_date,
        "lastTime": last_time,
        "elapsed": elapsed,
        "state": "pending-new-time" if rescheduled else state,
        "movedFrom": moved_from,
    })

routines.sort(key=lambda r: r["at"])

# ---------- overlap ----------
STOP = set("""the a an and or of to in on for with is it at by from game games app apps lab
studio builder maker play player time mode kit box pro plus mini super new my your one two
three challenge quiz simulator generator tool and""".split())


def toks(slug):
    return {t for t in re.split(r"[-_]", slug.lower()) if len(t) > 3 and t not in STOP}


# exact slug in >1 category (these are all dj pollution -- reported as such)
by_slug = collections.defaultdict(set)
for r in rows:
    by_slug[r["slug"]].add(r["cat"])
cross = {s: sorted(c) for s, c in by_slug.items() if len(c) > 1}
cross_dj = {s: c for s, c in cross.items() if any(QUARANTINE in x for x in c)}

# genuine signal: near-duplicates WITHIN one real category (2+ shared significant tokens)
near = []
bycat = collections.defaultdict(list)
for r in rows:
    if r["cat"] != QUARANTINE:
        bycat[r["cat"]].append(r)
for cat, items in bycat.items():
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            shared = toks(items[i]["slug"]) & toks(items[j]["slug"])
            if len(shared) >= 2:
                near.append({
                    "cat": cat, "catLabel": catlabel(cat), "shared": sorted(shared),
                    "a": items[i]["slug"], "aDate": items[i]["date"],
                    "b": items[j]["slug"], "bDate": items[j]["date"],
                    "sameDay": items[i]["date"] == items[j]["date"],
                })
near.sort(key=lambda x: (not x["sameDay"], x["cat"]))

real_counts = {k: v for k, v in counts.items() if k != QUARANTINE}

data = {
    "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "totalApps": len(rows),
    "undated": len(undated),
    "realApps": sum(real_counts.values()),
    "quarantine": {"cat": QUARANTINE, "label": catlabel(QUARANTINE),
                   "count": counts.get(QUARANTINE, 0), "crossSlugs": len(cross_dj)},
    "categories": sorted(({"name": k, "label": catlabel(k), "count": v}
                          for k, v in real_counts.items()),
                         key=lambda x: -x["count"]),
    "months": sorted(months.items()),
    "missingHeaders": len(missing),
    "routines": routines,
    "near": near[:12],
    "nearTotal": len(near),
    "nearSameDay": sum(1 for n in near if n["sameDay"]),
    "crossTotal": len(cross),
    "crossDj": len(cross_dj),
}

out = HERE / "factory.json"
out.write_text(json.dumps(data, indent=1), encoding="utf-8")

print("total rows        :", data["totalApps"], f"(undated: {data['undated']})")
print("real apps         :", data["realApps"], "across", len(data["categories"]), "categories")
print("quarantined       :", data["quarantine"]["count"], f"({data['quarantine']['crossSlugs']} cross-category slugs)")
print("cross-cat slugs   :", data["crossTotal"], "of which involve dj:", data["crossDj"])
print("near-dupes in real:", data["nearTotal"], "same-day:", data["nearSameDay"])
print("months            :", data["months"])
print("routines          :", len(routines))
for r in routines:
    print(f"   {r['at']}  {r['name']:<26} {r['state']:<16} last={r['lastDate']} {r['lastTime']}")
