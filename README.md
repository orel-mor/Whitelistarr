<p align="center">
  <img src="assets/logo.svg" alt="Whitelistarr" width="360">
</p>

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

A lightweight, self-hosted service that does one thing well, in real time.
Configure it declaratively through environment variables or interactively through
the built-in web UI (with a guided first-run setup and **Sign in with Plex**).

A focused reimplementation of
[plex-requester-collections](https://github.com/manybothans/plex-requester-collections).
Images publish multi-arch (`amd64`/`arm64`) to **`orelmor/whitelistarr`** (Docker
Hub) and **`ghcr.io/orel-mor/whitelistarr`** (GHCR).

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

1. **Reactive poll (default on).** Every `REACTIVE_INTERVAL_SECONDS` (60 by
   default) Whitelistarr does two cheap checks: it diffs the Radarr/Sonarr tag
   index to react to tag changes on existing titles within seconds, and it labels
   Plex *recently-added* items. This needs **no manual Plex webhook** (Plex
   webhooks require Plex Pass) — it's the zero-config path for both new media and
   tag edits.
2. **Event-driven labeling (optional).** A Seerr *Media Available* webhook (or a
   Plex *library.new* webhook) can also fire when an item lands on Plex.
   Whitelistarr reads the title's tags from Radarr/Sonarr, maps them to Plex
   labels, finds the Plex item by GUID, and reconciles its labels.
3. **Reconcile sweep.** On a schedule it re-syncs every item in the configured
   Plex sections — the safety net catching anything the reactive poll missed.
4. **Watch / stale notifications.** On a schedule it cross-references Seerr
   requests with Tautulli history and notifies via Apprise. It never writes back
   to Radarr/Sonarr — notifications only.

## Getting started

The image is prebuilt — no need to clone the repo. The only env var you must set
is `PAL_SECRET_KEY` (encrypts the saved config; generate one — see [Web UI](#web-ui)).
Everything else is configured in the web UI, served at `http://<host>:8000/`,
including **Sign in with Plex**, which fills in your Plex URL and token for you.

```yaml
services:
  whitelistarr:
    image: orelmor/whitelistarr:latest
    container_name: whitelistarr
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    environment:
      PAL_SECRET_KEY: "paste-a-fernet-key-here"
```

```bash
docker compose up -d
curl http://localhost:8000/health   # -> {"status":"ok"}
```

### Configuring via env instead of the UI

Prefer a fully declarative deploy? Add any of these to skip onboarding entirely —
the same settings the UI would write. See the
[configuration reference](#configuration-reference) for the full list.

```yaml
    environment:
      PAL_SECRET_KEY: "paste-a-fernet-key-here"
      PLEX_URL: "http://plex:32400"
      PLEX_TOKEN: "your-plex-token"
      RADARR_URL: "http://radarr:7878"
      RADARR_API_KEY: "your-radarr-key"
      SONARR_URL: "http://sonarr:8989"
      SONARR_API_KEY: "your-sonarr-key"
      TAG_LABEL_MAP: "kids:kids-allowed,family:shared" # <arr-tag>:<plex-label>
```

For a cautious first run, add `DRY_RUN: "true"`: the logs show every label and
notification it *would* apply, without touching Plex. If Seerr runs on the same
Docker network, drop the `ports:` mapping and point it at `http://whitelistarr:8000`.

## Triggering immediate labeling

By default the **reactive poll** (`FEATURE_REACTIVE=true`) handles everything: every
`REACTIVE_INTERVAL_SECONDS` (60s) it labels Plex recently-added items and diffs the
Radarr/Sonarr tag index to react to tag edits — including **manually added** content,
not just Seerr requests. No webhook, no Plex Pass. The periodic sweep is the safety
net. This is the recommended path.

The webhooks below are optional — only for push-instant (sub-second) labeling.
Append `?token=YOUR_SECRET` to either URL if you set `WEBHOOK_SECRET`.

- **Plex** (requires Plex Pass): in **Plex → Settings → Webhooks → Add Webhook**,
  set the URL to `http://whitelistarr:8000/webhook/plex`. Plex fires `library.new`
  the instant it adds an item.
- **Seerr**: in **Seerr → Settings → Notifications → Webhook**, set the URL to
  `http://whitelistarr:8000/webhook/seerr`, enable **Media Available** (others are
  ignored), keep the default JSON payload, then **Save**.

## Restricting a shared user to the label

This is the step that actually gates access (requires Plex Pass on your account):

1. **Plex → Settings → Users & Sharing → (the shared user) → Restrictions.**
2. Set the restriction **Profile** to **None** (required to edit label filters).
3. Under **Allow only items with these labels**, add the whitelist label you
   mapped in `TAG_LABEL_MAP` (for example `kids-allowed`).
4. Save. That user now sees only items carrying that label — which Whitelistarr
   maintains automatically.

## Web UI

The web UI is **on by default** — set a `PAL_SECRET_KEY` and it's served at
`http://<host>:8000/` (same port as the webhooks). Set `FEATURE_UI=false` to disable
it. It's a small single-page app (vendored [Alpine.js](https://alpinejs.dev/), no
build step) with four screens: a first-run **Setup wizard** (Sign in with Plex,
connect Radarr/Sonarr, set the tag → label map, and an optional notifications step
for Tautulli/Seerr/Apprise); a **Status** dashboard (job schedule, recent activity,
live connection health, and actions); a live **Logs** tail; and a **Settings** editor
split into **Core**, **Notifications** (toggle on/off), and **Advanced** sections.

**Generate a `PAL_SECRET_KEY`** (a Fernet key) once:

```bash
openssl rand -base64 32 | tr '+/' '-_'
# or: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- **Sign in with Plex.** Instead of pasting a token, the sign-in flow opens plex.tv,
  you authorize and pick your server, and Whitelistarr fills in the URL and token.
- **First run** seeds config from the environment; after that the **saved config is
  the source of truth** and the environment is a fallback.
- **Secrets** (tokens, API keys) are encrypted at rest with `PAL_SECRET_KEY` and
  never returned to the browser in plaintext. **Apprise URLs** are also encrypted at
  rest but *are* shown in the UI (one per line) so you can review and edit them.
- **Test connection** probes the values typed into the form, so you can verify a
  service before saving.
- **Changes apply live** (no restart), except the bootstrap settings
  (`PAL_SECRET_KEY`, `CONFIG_PATH`, `STATE_DB_PATH`, `FEATURE_UI`, `WEBHOOK_HOST`,
  `WEBHOOK_PORT`), which show a "restart to apply" banner.
- **No built-in auth.** The UI can edit secrets — keep it behind a reverse proxy or
  on a trusted network. A basic cross-origin guard rejects foreign-origin `/api`
  writes, but that's not a substitute for real auth.

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
| `FEATURE_REACTIVE` | `true` | Fast poll: react to arr tag changes + Plex recently-added (no Plex webhook needed) |
| `REACTIVE_INTERVAL_SECONDS` | `60` | How often the reactive poll runs |
| `SWEEP_CRON` | `0 * * * *` | Sweep schedule (5-field cron); hourly by default |
| `WATCH_SCAN_CRON` | `0 3 * * *` | Watch-history scan schedule (cron); daily 3am |
| `FEATURE_NOTIFY` | `false` | Enable watched/stale notifications |
| `SEERR_URL` / `SEERR_API_KEY` | — | Seerr connection (`OVERSEERR_*` also accepted) |
| `TAUTULLI_URL` / `TAUTULLI_API_KEY` | — | Tautulli (required if `FEATURE_NOTIFY=true`) |
| `APPRISE_URLS` | — | CSV of [Apprise URLs](https://github.com/caronc/apprise/wiki) |
| `NOTIFY_ON` | `labeled,watched,stale` | Events to notify on: `labeled`, `watched`, `stale` |

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
| `LOG_FILE` | `/data/whitelistarr.log` | Rolling log file path (empty disables it) |
| `LOG_FILE_LINES` | `10000` | Approx. lines kept in the log file before it rotates |
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

The project is **trunk-based**: `main` is the only long-lived branch. Feature
branches squash-merge into `main` (linear history), and every push builds the
bleeding-edge **`:dev`** image (amd64) for testing — no version, no release.

**Stable releases are cut on demand.** Run the **Release** workflow from the
Actions tab (`dry_run` on by default → previews the next version + notes;
`dry_run` off → ships).
[python-semantic-release](https://python-semantic-release.readthedocs.io/) then
tags the version from the [Conventional Commits](https://www.conventionalcommits.org/)
since the last tag, writes the changelog, and publishes the multi-arch `:latest`
and `:X.Y.Z` images. The commit type drives the bump (`feat:` → minor, `fix:` →
patch, `feat!:`/`BREAKING CHANGE:` → major; `docs:`/`chore:`/`test:` → none).

> Use `:latest` for stable, `:dev` to test the newest merged code.

Pull requests also run tests, lint, CodeQL, a dependency audit, and a Trivy image
scan. See [`.github/workflows/`](.github/workflows/) for the full pipeline.

## Limitations

- Movies and TV shows only.
- TV "fully watched" is approximate (a percent threshold); movies are exact.
- GUID matching depends on correct Plex agent metadata; unmatched items are logged
  during the sweep.
- Seerr → Radarr/Sonarr requester tagging must already be enabled.

## License

[MIT](LICENSE)
