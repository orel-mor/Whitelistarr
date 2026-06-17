<p align="center">
  <img src="assets/logo.svg" alt="Whitelistarr" width="360">
</p>

<h1 align="center">Whitelistarr</h1>

[![Release](https://github.com/orel-mor/Whitelistarr/actions/workflows/release.yml/badge.svg)](https://github.com/orel-mor/Whitelistarr/actions/workflows/release.yml)
[![CodeQL](https://github.com/orel-mor/Whitelistarr/actions/workflows/codeql.yml/badge.svg)](https://github.com/orel-mor/Whitelistarr/actions/workflows/codeql.yml)
[![Latest release](https://img.shields.io/github/v/release/orel-mor/Whitelistarr?include_prereleases&sort=semver)](https://github.com/orel-mor/Whitelistarr/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/orelmor/whitelistarr)](https://hub.docker.com/r/orelmor/whitelistarr)
[![Image size](https://img.shields.io/docker/image-size/orelmor/whitelistarr/latest)](https://hub.docker.com/r/orelmor/whitelistarr)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Whitelistarr mirrors **Sonarr/Radarr tags to Plex labels**, so a restricted Plex
share can be whitelisted automatically — no second library, no labeling titles by
hand. It can also send **Apprise notifications** for watch milestones and stale,
unwatched content.

It is a lightweight, self-hosted service that does one thing well: keep Plex
labels in sync with your \*arr tags, in real time. Configure it declaratively
through environment variables, or interactively through the built-in web UI —
including a guided first-run setup and **Sign in with Plex**.

Whitelistarr is a focused reimplementation of
[plex-requester-collections](https://github.com/manybothans/plex-requester-collections).

Images are published to **`orelmor/whitelistarr`** (Docker Hub) and
**`ghcr.io/orel-mor/whitelistarr`** (GHCR), multi-arch for `linux/amd64` and
`linux/arm64`.

## Features

- **Tag-to-label sync** — an explicit `TAG_LABEL_MAP` controls which \*arr tags
  become which Plex labels. Unmapped tags are ignored.
- **Managed-label safety** — only ever adds or removes the labels in your map.
  Manual labels (e.g. `favorite`) are never touched.
- **Real-time and reconciled** — label on a Plex or Seerr webhook the moment an
  item lands, with a periodic sweep as a safety net for missed events and manual
  edits.
- **GUID-agnostic matching** — matches Plex items on any of tmdb / tvdb / imdb,
  so it works regardless of which agent your library uses.
- **Watch & stale notifications** — optional Apprise alerts when a requester
  finishes watching, or when requested content goes stale and unwatched.
- **Web UI** — an optional, built-in interface on the same port: a first-run
  setup wizard with Sign in with Plex, a status dashboard (job schedule, recent
  activity, live connection health), and a full settings editor. Changes apply
  live, with secrets encrypted at rest.
- **Dry-run mode** — `DRY_RUN=true` logs every intended change without touching
  Plex or sending notifications.
- **Reversible** — a one-shot `REVERSE=true` run strips every managed label and
  exits.

## How it works

```
Seerr request ──► Radarr / Sonarr (requester tag)
                          │
   Seerr "Media Available" webhook ──► Whitelistarr ──► Plex label
                          │                      ▲
                          └──── periodic reconcile sweep ────┘
                                              │
              Tautulli watch history ──► Apprise notifications
```

1. **Event-driven labeling.** A Seerr *Media Available* webhook (or a Plex
   *library.new* webhook) fires when an item lands on Plex. Whitelistarr reads the
   title's tags from Radarr/Sonarr, maps them to Plex labels, finds the Plex item
   by GUID, and reconciles its labels.
2. **Reconcile sweep.** On a schedule it re-syncs every item in the configured
   Plex sections, catching manual tag edits, missed webhooks, and removals.
3. **Watch / stale notifications.** On a schedule it cross-references Seerr
   requests with Tautulli history and notifies via Apprise. It never writes back
   to Radarr/Sonarr — notifications only.

## Getting started

You don't need to clone the repository — the image is prebuilt. Create a
`docker-compose.yml` and run `docker compose up -d`.

The example below is a complete declarative setup. If you prefer, set only
`PAL_SECRET_KEY` and `FEATURE_UI`, start the container, and configure everything
else in the web UI — including **Sign in with Plex**, which fills in your Plex URL
and token for you.

```yaml
services:
  whitelistarr:
    image: orelmor/whitelistarr:latest
    container_name: whitelistarr
    restart: unless-stopped
    ports:
      - "8000:8000" # webhook receiver + /health (and the web UI)
    volumes:
      - ./data:/data # persists the notification-dedup database and UI config
    environment:
      # --- Required to start ---
      # Encrypts the UI config at rest. Generate once (see "Web UI" below).
      PAL_SECRET_KEY: "paste-a-fernet-key-here"
      FEATURE_UI: "true" # serve the web UI at http://host:8000/

      # --- Core (or configure these in the UI; "Sign in with Plex" fills the first two) ---
      PLEX_URL: "http://plex:32400" # Plex Pass required for label-based share filtering
      PLEX_TOKEN: "your-plex-token"
      RADARR_URL: "http://radarr:7878"
      RADARR_API_KEY: "your-radarr-key"
      SONARR_URL: "http://sonarr:8989"
      SONARR_API_KEY: "your-sonarr-key"
      # <arr-tag>:<plex-label>,... — unmapped tags are ignored
      TAG_LABEL_MAP: "kids:kids-allowed,family:shared"

      # --- Schedules (cron) ---
      SWEEP_CRON: "0 * * * *" # reconcile sweep — hourly
      WATCH_SCAN_CRON: "0 3 * * *" # watch/stale scan — daily at 03:00

      # --- Notifications (optional; remove this block to disable) ---
      FEATURE_NOTIFY: "true"
      APPRISE_URLS: "discord://webhook_id/webhook_token" # comma-separated
      SEERR_URL: "http://seerr:5055"
      SEERR_API_KEY: "your-seerr-key"
      TAUTULLI_URL: "http://tautulli:8181"
      TAUTULLI_API_KEY: "your-tautulli-key"

      # --- Container ---
      TZ: "UTC"
      PUID: "1000"
      PGID: "1000"
```

```bash
docker compose pull
docker compose up -d
docker compose logs -f
curl http://localhost:8000/health   # -> {"status":"ok"}
```

For a cautious first run, add `DRY_RUN: "true"` to the environment and watch the
logs: you'll see the labels it *would* add or remove and the notifications it
*would* send, without touching Plex. Remove it once the output looks correct.

If Seerr runs on the same Docker network, drop the `ports:` mapping and point
Seerr at `http://whitelistarr:8000` instead of the host.

## Triggering immediate labeling

Only one trigger is required — the periodic sweep is always a safety net. Choose
whichever fits your setup:

### Option A — Plex webhook (recommended; no Seerr config)

Plex fires `library.new` the instant it adds an item, making it the most accurate
"on addition" trigger. It also labels **manually added** content, not just Seerr
requests. Requires Plex Pass (server owner).

In **Plex → Settings → Webhooks → Add Webhook**, set the URL to
`http://whitelistarr:8000/webhook/plex` (or
`http://<docker-host>:8000/webhook/plex`). If you set `WEBHOOK_SECRET`, append
`?token=YOUR_SECRET`.

### Option B — Seerr webhook

In **Seerr → Settings → Notifications → Webhook**:

- **Webhook URL:** `http://whitelistarr:8000/webhook/seerr` (or
  `http://<docker-host>:8000/webhook/seerr`). With `WEBHOOK_SECRET`, append
  `?token=YOUR_SECRET`.
- **Notification types:** enable **Media Available** (others are ignored).
- Keep the default JSON payload — the app reads `media.media_type`, `media.tmdbId`
  and `media.tvdbId`.
- Click **Test** (test pings are accepted and ignored), then **Save**.

### Option C — no webhook

Leave `FEATURE_SWEEP=true` and set a tighter `SWEEP_CRON` (for example
`*/5 * * * *`, every 5 minutes). The reconcile sweep then picks up new items
within that window — simplest to operate, at the cost of a little latency.

## Restricting a shared user to the label

This is the step that actually gates access (requires Plex Pass on your account):

1. **Plex → Settings → Users & Sharing → (the shared user) → Restrictions.**
2. Set the restriction **Profile** to **None** (required to edit label filters).
3. Under **Allow only items with these labels**, add the whitelist label you
   mapped in `TAG_LABEL_MAP` (for example `kids-allowed`).
4. Save. That user now sees only items carrying that label — which Whitelistarr
   maintains automatically.

## Web UI

With `FEATURE_UI=true` and a `PAL_SECRET_KEY` set, a web UI is served at
`http://<host>:8000/` (the same port as the webhooks). It's a small single-page
app (vendored [Alpine.js](https://alpinejs.dev/) — no build step) with three
screens:

- **Setup wizard** (first run, when nothing is configured yet): sign in with
  Plex, connect Radarr/Sonarr with live connection tests, set your tag → label
  map, done. It hands off to the Status screen.
- **Status**: job schedule with next-run times, recent sweep/scan activity, live
  per-service connection health, and the actions (run sweep, send test
  notification, run reverse).
- **Settings**: every setting grouped, with **Core** shown and **Advanced**
  behind a toggle. Schedules use preset chips (Hourly / Every 6h / Daily / …) or
  a custom cron expression.

Details:

- **Sign in with Plex.** Instead of pasting a token, use the sign-in flow: it
  opens plex.tv, you authorize, then pick your server from the detected list —
  Whitelistarr fills in both the Plex URL and token for you.
- **First run** seeds the config from your environment variables. After that the
  **saved config is the source of truth** and the environment becomes a fallback.
- **Secrets** (tokens and API keys) are stored **encrypted** with
  `PAL_SECRET_KEY`. Generate one once:
  ```bash
  openssl rand -base64 32 | tr '+/' '-_'
  # or: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **Changes apply live** — saving rebuilds the running clients and scheduler in
  place, no container restart. The exception is the bootstrap settings
  (`PAL_SECRET_KEY`, `CONFIG_PATH`, `STATE_DB_PATH`, `FEATURE_UI`, `WEBHOOK_HOST`,
  `WEBHOOK_PORT`); changing one shows a "restart to apply" banner for that field.
  If a save can't connect (e.g. a bad Plex token), the previous config keeps
  running and the UI shows the error.
- **No built-in authentication.** The UI can edit secrets, so keep it behind a
  reverse proxy or on a trusted network. Secrets are never returned to the browser
  in plaintext, and the config file is encrypted at rest. Mutating `/api` requests
  from a foreign origin are rejected (a basic cross-origin guard), but that is not
  a substitute for putting auth in front. Set `FEATURE_UI=false` to disable the UI.

If `FEATURE_UI=true` but `PAL_SECRET_KEY` is unset, the UI is disabled and the app
runs from environment variables.

## Notifications

Choose which events notify via `NOTIFY_ON`:

- **`labeled`** — items were whitelisted or un-whitelisted. Sent as two titled
  messages (**Label Added** / **Label Removed**), grouped by media type, listing
  every affected item. Deduplicated per item and label. Requires only
  `APPRISE_URLS`.
- **`watched`** — the requester watched an item past `WATCHED_PERCENT` (default
  85%). Requires Tautulli and `FEATURE_NOTIFY=true`.
- **`stale`** — an item is older than `STALE_AFTER_DAYS` and unwatched for
  `UNWATCHED_AFTER_DAYS`. Requires Tautulli and `FEATURE_NOTIFY=true`.

With `DRY_RUN=true`, notifications are logged but not sent. To confirm your
channels work, use the **Send test notification** button in the web UI's Actions
panel — it sends one real test message (ignoring `DRY_RUN`). The startup log also
reports how many Apprise channels loaded, e.g. `Notifications: 2/2 Apprise
channel(s) loaded`.

## Removing all labels

To strip the managed label(s) from your whole library (for example before
uninstalling), run once with `REVERSE=true`. It removes only the labels in your
`TAG_LABEL_MAP` (manual labels are untouched), then exits without starting the
webhook or scheduler. Dry-run it first:

```bash
docker run --rm --env-file .env -e REVERSE=true -e DRY_RUN=true orelmor/whitelistarr:latest
# happy with the log? run it for real:
docker run --rm --env-file .env -e REVERSE=true orelmor/whitelistarr:latest
```

## Configuration reference

Settings come in three tiers. **Bootstrap** is read from the environment only and
needs a restart to change. **Core** + **Advanced** can be set in the env (for a
declarative deploy) or in the web UI, where they apply live.

**Bootstrap (env-only, restart-required)**

| Variable | Default | Description |
|---|---|---|
| `PAL_SECRET_KEY` | — | Fernet key; required when the UI is on (encrypts secrets at rest) |
| `FEATURE_UI` | `true` | Serve the config web UI at `/` (same port) |
| `CONFIG_PATH` | `/data/config.json` | Where the UI persists config |
| `STATE_DB_PATH` | `/data/state.db` | SQLite dedup database path |
| `WEBHOOK_HOST` / `WEBHOOK_PORT` | `0.0.0.0` / `8000` | Webhook bind address |

**Core**

| Variable | Default | Description |
|---|---|---|
| `PLEX_URL` / `PLEX_TOKEN` | — | Plex server and auth token (or use "Sign in with Plex" in the UI) |
| `RADARR_URL` / `RADARR_API_KEY` | — | Radarr connection |
| `SONARR_URL` / `SONARR_API_KEY` | — | Sonarr connection |
| `TAG_LABEL_MAP` | — | `tag:label,tag:label` — which \*arr tags become which Plex labels |
| `SWEEP_CRON` | `0 * * * *` | Sweep schedule (5-field cron); hourly by default |
| `WATCH_SCAN_CRON` | `0 3 * * *` | Watch-history scan schedule (cron); daily 3am |
| `FEATURE_NOTIFY` | `false` | Enable watched/stale notifications |
| `SEERR_URL` / `SEERR_API_KEY` | — | Seerr connection (`OVERSEERR_*` also accepted) |
| `TAUTULLI_URL` / `TAUTULLI_API_KEY` | — | Tautulli (required if `FEATURE_NOTIFY=true`) |
| `APPRISE_URLS` | — | CSV of [Apprise URLs](https://github.com/caronc/apprise/wiki) |
| `NOTIFY_ON` | `watched,stale` | Events to notify on: `labeled`, `watched`, `stale` |

> The legacy `SWEEP_INTERVAL_MINUTES` / `WATCH_SCAN_INTERVAL_MINUTES` are still
> accepted and auto-migrated to the matching `*_CRON` value on load.

**Advanced overrides** (sane defaults; rarely changed)

| Variable | Default | Description |
|---|---|---|
| `PLEX_SECTIONS` | *(all)* | CSV of movie/show section names to process |
| `PLEX_DEVICE_NAME` | `Whitelistarr` | Device name shown in Plex → Settings → Devices |
| `PLEX_CLIENT_ID` | *(generated)* | Stable client id; auto-generated and persisted on first run |
| `LABEL_REMOVAL` | `reconcile` | `reconcile` (add + remove) or `add-only` |
| `FEATURE_WEBHOOK` | `true` | Run the Seerr webhook receiver |
| `FEATURE_SWEEP` | `true` | Run the periodic reconcile sweep |
| `WATCHED_PERCENT` | `85` | Percent watched that counts as "finished" |
| `STALE_AFTER_DAYS` | `180` | Age before an item can be "stale" |
| `UNWATCHED_AFTER_DAYS` | `90` | No-watch window for "stale" |
| `WEBHOOK_PATH` | `/webhook/seerr` | Seerr webhook route |
| `PLEX_WEBHOOK_PATH` | `/webhook/plex` | Plex webhook route (Plex Pass) |
| `WEBHOOK_SECRET` | — | Optional `?token=` shared secret |
| `DRY_RUN` | `false` | Log intended changes without applying them |
| `REVERSE` | `false` | One-shot: remove all managed labels from every item, then exit |
| `LOG_LEVEL` | `info` | Logging level |
| `TZ` | `UTC` | Container timezone |
| `PUID` / `PGID` | `1000` / `1000` | User/group the container drops to (starts as root, fixes `/data` ownership, then runs unprivileged) |

## Development

```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows; use "source .venv/bin/activate" on Unix
pip install -e ".[dev]"
pytest
ruff check .
```

The codebase is test-driven. Pure logic (config parsing, label reconcile, GUID
matching, watched/stale rules) is unit-tested; HTTP clients are tested against
mocked responses with `respx`; Plex is tested via a fake video object — tests
never touch a real server. For a local container build, the repository ships a
`docker-compose.yml` with a `build:` section (`docker compose up --build`).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching model, commit
conventions, and release process.

## Releases and CI

The project is **trunk-based**: `main` is the single permanent branch, and
releases are automated with
[python-semantic-release](https://python-semantic-release.readthedocs.io/), driven
by [Conventional Commits](https://www.conventionalcommits.org/):

- A squash-merge to **`main`** cuts a stable release with a GitHub Release and
  changelog, and publishes a multi-arch image tagged `:latest` and `:X.Y.Z`.
- Commit type drives the version bump: `feat:` → minor, `fix:` → patch, `feat!:`
  or `BREAKING CHANGE:` → major. `docs:` / `chore:` / `test:` produce no release.
- To stage a risky change first, push an on-demand **`beta`** branch: it cuts
  prereleases (`vX.Y.Z-beta.N`) and publishes `:beta`. Merge it into `main` and
  delete it when done.
- Image builds run only when the commits warrant a release.

Pull requests additionally run tests, lint, CodeQL analysis, a dependency audit,
and a Trivy image scan. See [`.github/workflows/`](.github/workflows/) for the
full pipeline.

## Limitations

- Movies and TV shows only.
- TV "fully watched" is approximate (a percent threshold); movies are exact.
- GUID matching depends on correct Plex agent metadata; unmatched items are logged
  during the sweep.
- Seerr → Radarr/Sonarr requester tagging must already be enabled.

## License

[MIT](LICENSE)
