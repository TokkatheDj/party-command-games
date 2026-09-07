# 📱 AppVerse

A local launcher for a few hundred self-contained HTML apps — games, classroom tools,
music toys, art, kids' stuff. One Python file serves the whole folder to any device on the
home network, so an app written on the desktop is playable on a phone seconds later.

No build step, no framework, no database. Every app is a single `.html` file that runs on
its own; AppVerse just finds them and puts a menu in front of them.

## Start it

```
Start-AppServer.ps1        (right-click → Run with PowerShell)
```

or directly:

```
py serve_apps.py
```

Then open `http://<this machine's LAN IP>:8080` on the phone or tablet. The server listens
on all interfaces, so any device on the same wifi can reach it. It is **http on the local
network only** — deliberately not exposed to the internet.

**Keep it that way.** There is no login, and the front page embeds the email addresses that
come in with build requests — so this server must never be reachable from outside the house.
Tailscale is the right answer for using it from elsewhere, and the plain tailnet IP on port
8080 needs no setup at all, because the server already listens on all interfaces.

There is now also a **`tailscale serve` route, deliberately**, added 6 Sep 2026:

```
https://<this-machine>.<your-tailnet>.ts.net:8444   ->   http://127.0.0.1:8080

# the real hostname is whatever `tailscale status` reports for this machine;
# it is kept out of this file because the repo is public
```

It exists because Chrome's "Always use secure connections" silently upgrades a plain-http
address to https and then fails, which made the launcher look dead on an Android tablet.
Serving it over the tailnet's real certificate sidesteps that on every device, with no
per-device setting to remember.

`serve` is **tailnet only** — your own signed-in devices, nothing public. `funnel` is the
one that publishes to the internet, and it must stay off. Check both, and read the labels
rather than the presence of a route:

```
tailscale serve status      # both routes should say "(tailnet only)"
tailscale funnel status     # must show nothing public
tailscale serve --https=8444 off     # to remove the AppVerse route
```

**This changes what the log can tell you.** Requests arriving through any such proxy are
logged with a client address of `127.0.0.1` rather than the device's own address, so traffic
through the 8444 route is indistinguishable from local traffic — you can no longer tell a
phone from a tablet by IP for those requests. Use the LAN or plain tailnet IP on 8080 when
you need per-device attribution.

That also blunts an alarm that used to be reliable: localhost hits were once proof of
internet exposure. They are now normal. What still means trouble is a burst of them carrying
a **scanner User-Agent** — probing `.env`, `wp-config.php`, `/actuator/env` — which is what
the September Funnel incident looked like. If you see that, check `funnel status` first.

Only one instance can hold the port; a second one exits cleanly rather than fighting for
it. To run a preview build beside the live server, give it another port:

```
APPVERSE_PORT=8081 py serve_apps.py
```

## The menu

The front page is about **what you use**, not about what is on disk.

| Section | What it shows |
|---|---|
| **★ Yours** | Your favorites — the apps you hearted |
| **🆕 New this week** | Anything modified in the last 7 days, so a new app is not born invisible |
| **▸ Browse all N by category** | The full category grid, one tap away |

This is the whole point of the design. The menu used to mirror the folder tree, which
meant a category holding 46 generated apps that had been opened *once* got exactly the
same tile as one where every app gets used. Most of the collection had never been opened,
rated or favorited, and the page was answering "what files exist" instead of "what do I
want to open right now".

Inside a category, apps rated 1–2 stars fold into a **`N apps you rated low`** drawer. A
favorite beats a low rating: if an app is hearted *and* rated low, it stays up top — you
hearted it on purpose.

**Nothing is ever deleted or hidden.** Demotion is presentation only, and global search
still finds every app in the collection, including ones that appear nowhere on the front
page.

### How the menu learns

Tap the heart to put an app on the front page. Tap the stars to push it down. That is the
entire mechanism — there is no separate settings screen, and the sorting reacts
immediately.

State lives in `.app_data.json` (favorites, ratings, opened, notes, playlists, removed).
That file is **gitignored** — it holds personal usage and, in the build-request records,
email addresses. It is the one file worth backing up; the apps themselves are just files.

## Other tabs

**Apps** and **Notes** sit in the header; **Reviews**, **Lists** and **Build** live behind
**⋯ More**. Notes stays top-level on purpose — it is the inbox where app build requests and
the daily AI check land, so it needs to be visible when something is waiting.

## Adding an app

Drop a self-contained `.html` file into the right category folder. That's it — the server
discovers it on the next page load and it shows up under **New this week**. See
`CLAUDE.md` for the folder map and the house rules for writing one.

Folders prefixed with `_` or `.` hold tooling and are skipped by discovery, so a template
or a dashboard scaffold never shows up as an app.

## The request log

Every request is appended to `_access.log` — timestamp, client address, request line, status
and User-Agent. The User-Agent is the useful part: it is what tells a phone apart from the
desktop browser, which answers "did my phone actually reach the server?" without guessing.

It rotates to `_access.log.1` at 2 MB and is **gitignored** — it records your IP addresses
and everything you opened. Writes are best-effort: a logging failure can never break a page
load. This matters more than it sounds, because the server normally runs from a scheduled
task under `pythonw` with no console, so before this file existed the request log went
nowhere at all.

## Testing

```
.\Run-Tests.ps1                        # all apps, iPhone + iPad viewports
.\Run-Tests.ps1 -Category kids         # one category
.\Run-Tests.ps1 -App "star catcher"    # one app
.\Run-Tests.ps1 -Install               # first-time Playwright setup
```

Reports open at `test_reports\index.html`.

## Scheduled tasks

| Task | What it does |
|---|---|
| `CoworkApp` | Starts the server at logon |
| `CoworkApps-DailyCheck` | Daily AI pass over the notes |
| `CoworkApps-PollutionCheck` | Watches for the generator writing into the wrong folders |
| `CoworkApps-DailyDJApp` | **Paused.** Built one DJ app per day |

The DJ generator is disabled, not deleted — it had produced 46 apps of which exactly one
had ever been opened, and that pile was most of what made the menu feel overwhelming.
Re-enable it with `Enable-ScheduledTask -TaskName 'CoworkApps-DailyDJApp'`.

## A note on the pile

A few hundred apps exist here and a majority have never been opened. That is fine — they
cost nothing but disk, and the menu no longer makes them your problem. If they are ever
worth clearing out, do it deliberately: **this folder has no recovery path**, and the
ratings in `.app_data.json` are the only record of which ones were any good.
