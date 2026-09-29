# Build My App

A one-page order form: a customer describes an app in one line, pays $10, and
Claude builds it as a single self-contained HTML file — previewed on the page,
downloadable, and (unless they opt out) published to its own Netlify link.

## How it works

- `index.html` — the order form. It records each order as a Netlify Form
  (`app-request`, for reconciling payments), then starts the build and polls
  for the result. The preview runs the generated app in a sandboxed frame with
  **no** access to this page.
- `netlify/functions/generate-background.mts` — `POST /api/generate`, a
  background function: checks the gates below, asks Claude for the app, and
  publishes it as a new Netlify site. Results go to the `build-requests` blob
  store under the build's id.
- `netlify/functions/status.mts` — `GET /api/status?id=…`, what the page polls.

## Protection (added 29 Sep 2026)

The builder spends Anthropic credit and creates Netlify sites, so nothing is
spent until a request passes all three:

1. **Order code.** After a customer pays, send them the current code. They
   type it on the form (capitals don't matter). Change it whenever you like.
2. **Daily limits.** At most `BUILD_DAILY_LIMIT` builds a day in total
   (default 10) and `BUILD_PERSON_LIMIT` per visitor (default 3), counted in
   the `build-limits` blob store.
3. **Clean input.** A build id is used once and never overwritten, and every
   field is cut to the form's own lengths.

With no order code set, the builder answers "Orders are paused" — it fails
closed, not open.

## Settings (Netlify → Site configuration → Environment variables)

| Variable | What it is |
|---|---|
| `BUILD_ORDER_CODE` | the code you give paying customers — **required** |
| `BUILD_DAILY_LIMIT` | builds per day, all customers (default 10) |
| `BUILD_PERSON_LIMIT` | builds per day, one visitor (default 3) |
| `ANTHROPIC_API_KEY` | the builder's Claude key |
| `NETLIFY_DEPLOY_TOKEN` | lets the builder create the customer's site |

## Deploying

This folder lives inside the `party-command-games` repo. Netlify only rebuilds
when something under `build-my-app/` changes (see `netlify.toml`). Set
`BUILD_ORDER_CODE` **before** deploying the protected version, or orders
will show as paused.
