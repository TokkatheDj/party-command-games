#!/usr/bin/env python3
"""add_to_arcade.py - put apps you've played on the public Games Arcade, in one step (13 Oct 2026).

On 13 Oct nine new apps went onto the Arcade by hand: commit them, add a tile to BOTH
catalogs (index.html at the repo root, all-games-hub.html here), fix the game count in
two READMEs, push, then wait for GitHub Pages and check the live site. This does all
of that, and refuses an app the nightly check (new_app_check.py) found broken or never
checked - you play it, the checker plays it, then it goes up.

    python add_to_arcade.py --waiting        every app new_app_check.py has waiting and passed
    python add_to_arcade.py kids_apps/x.html party_apps/y.html
    python add_to_arcade.py x.html --name "Pup Dash" --emoji "🐶" --section kids
    --dry      show what would change, touch nothing
    --no-push  commit, but don't push or check the live site

Section comes from the folder (party_apps -> Party Games, most others -> Kids Games);
the tile name from the page <title>, cut short. Exit 0 only when every app is live.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FOLDER = os.path.basename(HERE)                       # "cowork apps"
HUBS = [os.path.join(REPO, "index.html"), os.path.join(HERE, "all-games-hub.html")]
README = os.path.join(REPO, "README.md")
PROFILE = os.path.join(REPO, "portfolio-profile", "README.md")
STATE = os.path.join(HERE, "test_reports", "new-apps.json")
LIVE = "https://tokkathedj.github.io/party-command-games/"
# Section keys in the catalog (28 Oct 2026 regroup): classics, party (Game Night), carnival, kids (Little Kids),
# learn, create (Art & Music), action, math (worksheets). A kids app about counting or letters belongs in
# learn - move its line there by hand; the folder can't tell.
SECTIONS = ["classics", "party", "carnival", "kids", "learn", "create", "action", "math"]
SECTION_OF = {"party_apps": "party", "kids_apps": "kids", "action_games": "action", "Action Games": "action",
              "art_apps": "create", "music_apps": "create", "music_game_apps": "create", "educational_apps": "learn",
              "Educational Apps": "learn", "table_games_apps": "party", "card_games_apps": "party"}
EMOJI = [("puzzle", "🧩"), ("draw", "✏️"), ("doodle", "✏️"), ("paint", "🖌️"), ("color", "🎨"),
         ("pup", "🐶"), ("dog", "🐶"), ("cat", "🐱"), ("dragon", "🐉"), ("bingo", "🙋"), ("word", "🔠"),
         ("music", "🎵"), ("beat", "🥁"), ("math", "🔢"), ("count", "🔢"), ("race", "🏁"), ("run", "🏃"),
         ("space", "🚀"), ("monster", "👾"), ("critter", "🐭"), ("arena", "💥"), ("card", "🃏"),
         ("trivia", "❓"), ("quiz", "❓"), ("memory", "🧠"), ("dance", "🕺")]
GIT = ["git", "-C", REPO]


def git(*args, check=True):
    r = subprocess.run(GIT + list(args), capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        sys.exit("git %s failed: %s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return r.stdout


def tile_name(rel):
    m = re.search(r"<title>([^<]*)</title>", open(os.path.join(HERE, rel), encoding="utf-8").read(), re.I)
    t = (m.group(1) if m else os.path.basename(rel)).strip()
    t = re.split(r"\s+[–—|-]\s+", t)[0].rstrip("!").strip()
    if len(t) > 20 and ":" in t:
        t = t.split(":")[0].strip()
    return t[:24]


def emoji_for(rel, name):
    k = (rel + " " + name).lower()
    return next((e for w, e in EMOJI if w in k), "🎮")


# Family names that must never reach the public Arcade, one per line. The list lives OUTSIDE
# this public repo - a copy in here would publish the very names it protects. 27 Oct 2026: a
# game's title-screen credit put a child's name on a public page.
PRIVATE_NAMES = r"C:\Users\Lance\Amigo\private-names.txt"


def private_names_in(text, path=None):
    """The listed names that appear in text as whole words; None if there is no list here."""
    try:
        names = [l.strip() for l in open(path or PRIVATE_NAMES, encoding="utf-8")
                 if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        return None
    return sorted(n for n in set(names) if re.search(r"\b%s\b" % re.escape(n), text, re.I))


# A kids app whose file name says it teaches something goes in Learn & Play, not Little Kids
# (28 Oct 2026: the regroup had to move 13 of them by hand).
LEARN_WORDS = re.compile(r"math|count|number|add|subtract|letter|abc|alphabet|spell|phonic|rhym|read|"
                         r"measur|shape|pattern|science|sink-or-float|weather|coin|money|clock|tell-time|"
                         r"sudoku|fraction|vowel|sight-word|gear", re.I)


def section_for(rel):
    """The Arcade section an app's folder belongs to, or None if the folder has none
    (the VR folders, review-kit, ... - not Arcade games, or not placed yet)."""
    rel = rel.replace("\\", "/")
    sec = SECTION_OF.get(rel.split("/")[0])
    if sec == "kids" and LEARN_WORDS.search(rel.split("/")[-1]):
        return "learn"
    return sec


def waiting_ready(checked):
    """(placeable, unplaced) among the apps the nightly check has waiting and passed.
    --waiting adds only the placeable ones: on 16 Oct an Action Games app made the
    whole SHIP IT step stop on 'which section?' before adding anything."""
    ready = [k for k, v in sorted(checked.items())
             if v.get("ok") and not v.get("a11y") and v.get("waiting", True) and v.get("public", True)]
    return [k for k in ready if section_for(k)], [k for k in ready if not section_for(k)]


def section_block(hub, key):
    """(start, end) of the games list of SECTIONS entry `key` - end is the index of its '    ],'."""
    m = re.search(r"key: '%s'.*?games: \[\r?\n" % key, hub, re.S)
    if not m:
        sys.exit("no section '%s' in the catalog" % key)
    end = hub.index("    ],", m.end())
    return m.end(), end


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # emoji on a cp1252 console
    except AttributeError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("apps", nargs="*")
    ap.add_argument("--waiting", action="store_true")
    ap.add_argument("--name"); ap.add_argument("--emoji"); ap.add_argument("--section", choices=SECTIONS)
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()

    try:
        checked = json.load(open(STATE, encoding="utf-8")).get("apps", {})
    except (OSError, ValueError):
        checked = {}
    apps = [x.replace("\\", "/").split(FOLDER + "/")[-1] for x in a.apps]
    if a.waiting:
        # public apps waiting to be committed - not the private ones the check also plays
        # (and not ones failing the accessibility scan - the Arcade is kept clean), and only
        # those whose folder has a section; the rest are named and left for a --section call
        placeable, unplaced = waiting_ready(checked)
        apps += placeable
        for k in unplaced:
            print("not added: %s - its folder has no Arcade section; add it with --section party or --section kids" % k)
    apps = list(dict.fromkeys(apps))
    if not apps:
        sys.exit("nothing to add - no apps given, and nothing waiting that passed the nightly check")
    if (a.name or a.emoji) and len(apps) > 1:
        sys.exit("--name / --emoji are for one app at a time")

    hubs = {h: open(h, encoding="utf-8", newline="").read() for h in HUBS}
    plan = []
    for rel in apps:
        full = os.path.join(HERE, rel)
        if not os.path.isfile(full):
            sys.exit("%s: no such file" % rel)
        found = private_names_in(open(full, encoding="utf-8", errors="replace").read() + " " + (a.name or ""))
        if found is None:
            print("note: no family-names list at %s - not checked for names" % PRIVATE_NAMES)
        elif found:   # the count only: this output lands in logs
            sys.exit("%s: has %d family name(s) in it - they stay off the public Arcade; take them out first"
                     % (rel, len(found)))
        if subprocess.run(GIT + ["check-ignore", "-q", os.path.join(FOLDER, rel)]).returncode == 0:
            sys.exit("%s: its folder is private (gitignored) - publishing it needs an exception in .gitignore; "
                     "see the action_games/* lines there" % rel)
        tracked = bool(git("ls-files", os.path.join(FOLDER, rel)).strip())
        changed = bool(git("status", "--porcelain", "--", os.path.join(FOLDER, rel)).strip())
        if (changed or not tracked) and not (rel in checked and checked[rel].get("ok")):
            why = "the nightly check found problems" if rel in checked else "the nightly check hasn't played it yet"
            sys.exit("%s: %s - run python new_app_check.py first, or fix it" % (rel, why))
        if rel in checked and checked[rel].get("a11y"):
            sys.exit("%s: fails the accessibility scan the Arcade is held to (%s) - fix it, then let the "
                     "nightly check play it again" % (rel, "; ".join(checked[rel]["a11y"][:2])))
        src = "/".join(p.replace(" ", "%20") for p in rel.split("/"))
        sec = a.section or section_for(rel)
        if not sec:
            sys.exit("%s: which section? add --section party or --section kids" % rel)
        name = a.name or tile_name(rel)
        plan.append({"rel": rel, "src": src, "section": sec, "name": name, "emoji": a.emoji or emoji_for(rel, name),
                     "already": all(("src: '%s'" % src) in s for s in hubs.values())})

    stamp = time.strftime("%d %b %Y").lstrip("0")
    for h, s in hubs.items():
        nl = "\r\n" if "\r\n" in s else "\n"
        ids = set(re.findall(r"\{ id: '([^']+)'", s))
        for p in plan:
            if ("src: '%s'" % p["src"]) in s:
                continue
            base = p["section"] + "-" + re.sub(r"[^a-z0-9]+", "", p["name"].lower())[:12]
            gid, n = base, 2
            while gid in ids:
                gid, n = "%s%d" % (base, n), n + 1
            ids.add(gid)
            line = "      { id: %-17s name: %-20s emoji: '%s', type: 'plain', src: '%s' }, // added %s%s" % (
                "'%s'," % gid, "'%s'," % p["name"].replace("'", "\\'"), p["emoji"], p["src"], stamp, nl)
            _, end = section_block(s, p["section"])
            s = s[:end] + line + s[end:]
        hubs[h] = s
    registry = re.search(r"const SECTIONS = \[(.*?)\n\];", hubs[HUBS[0]], re.S).group(1)
    total = len(re.findall(r"\{ id: '", registry))
    # the README counts each section too, and the weekly health check compares them (13 Oct)
    per = {k: len(re.findall(r"\{ id: '%s" % k, registry)) for k in ("party-", "kids-")}

    for p in plan:
        print("%-55s %s %-20s %s%s" % (p["rel"], p["emoji"], p["name"], p["section"], "  (already listed)" if p["already"] else ""))
    print("the Arcade will have %d games" % total)
    if a.dry:
        return 0

    for h, s in hubs.items():
        open(h, "w", encoding="utf-8", newline="").write(s)
    counted = []
    for path, pat, fmt, n in ((README, r"\*\*\d+ games\*\*", "**%d games**", total),
                              (README, r"Party Games \(\d+\)", "Party Games (%d)", per["party-"]),
                              (README, r"Kids Games \(\d+\)", "Kids Games (%d)", per["kids-"]),
                              (PROFILE, r"^\d+ party, carnival", "%d party, carnival", total)):
        if os.path.isfile(path):
            t = open(path, encoding="utf-8", newline="").read()
            t2 = re.sub(pat, fmt % n, t, count=1, flags=re.M)
            if t2 != t:
                open(path, "w", encoding="utf-8", newline="").write(t2)
                if path not in counted:
                    counted.append(path)

    git("add", "--", *[os.path.join(FOLDER, p["rel"]) for p in plan], *HUBS, *[c for c in counted if c == README])
    committed = subprocess.run(GIT + ["diff", "--cached", "--quiet"]).returncode != 0   # something staged
    if committed:
        names = ", ".join(p["name"] for p in plan)
        git("commit", "-q", "-m", "Arcade: add %s (%d games)\n\nadd_to_arcade.py - played, and passed the nightly check.\n\n"
            "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" % (names, total))
    if PROFILE in counted:
        prof = os.path.dirname(PROFILE)
        subprocess.run(["git", "-C", prof, "commit", "-q", "-am", "Games Arcade is %d games now" % total], check=True)
    if a.no_push:
        print("committed, not pushed" if committed else "nothing new to commit")
        return 0
    git("push", "-q")
    if PROFILE in counted:
        subprocess.run(["git", "-C", os.path.dirname(PROFILE), "push", "-q"], check=True)

    # GitHub Pages takes a minute or two
    want = ["src: '%s'" % p["src"] for p in plan]
    for i in range(36):
        try:
            page = urllib.request.urlopen(LIVE + "?v=%d%d" % (time.time(), i), timeout=15).read().decode("utf-8", "replace")
            if all(w in page for w in want):
                bad = []
                for p in plan:
                    try:
                        urllib.request.urlopen(LIVE + FOLDER.replace(" ", "%20") + "/" + p["src"], timeout=15).read(64)
                    except Exception as e:
                        bad.append("%s (%s)" % (p["rel"], e))
                if bad:
                    sys.exit("listed, but these don't load on the live site: " + "; ".join(bad))
                print("live: all %d on %s" % (len(plan), LIVE))
                return 0
        except Exception:
            pass
        time.sleep(10)
    sys.exit("pushed, but the live Arcade didn't show them within 6 minutes - check %s" % LIVE)


if __name__ == "__main__":
    sys.exit(main())
