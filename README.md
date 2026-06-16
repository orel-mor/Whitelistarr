# Whitelistarr

[![Release](https://github.com/orel-mor/Whitelistarr/actions/workflows/release.yml/badge.svg)](https://github.com/orel-mor/Whitelistarr/actions/workflows/release.yml)
[![Latest release](https://img.shields.io/github/v/release/orel-mor/Whitelistarr?include_prereleases&sort=semver)](https://github.com/orel-mor/Whitelistarr/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/orelmor/whitelistarr)](https://hub.docker.com/r/orelmor/whitelistarr)
[![Image size](https://img.shields.io/docker/image-size/orelmor/whitelistarr/latest)](https://hub.docker.com/r/orelmor/whitelistarr)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Formerly `Plex-Auto-Labels`.** Images moved to **`orelmor/whitelistarr`** —
> the old `orelmor/plex-auto-labels` image is frozen but still pullable. Update
> your `image:` line to keep getting releases.

Automatically turn **Sonarr/Radarr tags into Plex labels** so you can give a
restricted user (e.g. a child account) access to a hand-curated, whitelisted
subset of a *shared* library — without splitting your media into a second
library or manually labeling every title. Also sends **Apprise notifications**
when a requester finishes watching something or when requested content goes
stale and unwatched.

It is a lean, env-var-only re-build of
[plex-requester-collections](https://github.com/manybothans/plex-requester-collections),
tailored to one job: keeping a Plex label in sync with an *arr tag, immediately.

Docker images: **`orelmor/whitelistarr`** (Docker Hub) and
**`ghcr.io/orel-mor/whitelistarr`** (GHCR). Multi-arch: `linux/amd64` + `linux/arm64`.

## Why this exists

Plex (with a **Plex Pass on the server owner**) lets you restrict a shared
library so a user only sees items carrying a specific **label**. That's the clean
way to whitelist content for a kid on an account you don't fully control — but
doing it by hand for every new title is tedious.

Seerr (formerly Overseerr) already tags Radarr/Sonarr items by requester. This
app reads those tags and mirrors the ones you care about onto Plex as labels, so
the whitelist maintains itself.

## How it works

```
Seerr request ──► Radarr/Sonarr (requester tag)
                          │
   Seerr "Media Available" webhook ──► Whitelistarr ──► Plex label
                          │                     ▲
                          └── periodic reconcile sweep ┘
                                                  │
                Tautulli watch history ──► Apprise notifications
```

1. **Event-driven labeling.** Seerr fires a *Media Available* webhook when a
   requested item lands on Plex. The app reads that title's tags from
   Radarr/Sonarr, maps the configured tags to Plex labels, finds the Plex item by
   its GUID (tmdb/tvdb/imdb — whichever your agent uses), and reconciles labels.
2. **Reconcile sweep.** On a schedule it re-syncs every item in your Plex
   sections, catching manual tag edits, missed webhooks and removals.
3. **Watch/stale notifications.** On a schedule it cross-references Seerr requests
   with Tautulli history and notifies via Apprise when the requester finishes
   watching, or when an item is old and still unwatched. (It never writes this
   back to Radarr/Sonarr — notifications only.)

**Key behaviors:** explicit tag→label map (`TAG_LABEL_MAP`, unmapped tags
ignored); managed-label safety (only ever touches labels in your map — manual
labels like `favorite` are never altered); true sync (`reconcile` adds *and*
removes; `add-only` never removes); and `DRY_RUN` to log intended changes
without applying them.

## Run with Docker Compose

No need to clone the repo — pull the prebuilt image. Create a `docker-compose.yml`
with everything wired up (this enables **all** capabilities, including
watched/stale notifications):

```yaml
services:
  whitelistarr:
    image: orelmor/whitelistarr:latest
    container_name: whitelistarr
    restart: unless-stopped
    ports:
      - "8000:8000"            # Seerr webhook receiver (+ /health)
    volumes:
      - ./data:/data           # persists the notification-dedup database
    environment:
      # --- Plex (server owner; Plex Pass required for label-based share filtering) ---
      PLEX_URL: "http://plex:32400"
      PLEX_TOKEN: "your-plex-token"
      PLEX_SECTIONS: "Movies,TV Shows"      # empty = all movie/show sections

      # --- Radarr / Sonarr ---
      RADARR_URL: "http://radarr:7878"
      RADARR_API_KEY: "your-radarr-key"
      SONARR_URL: "http://sonarr:8989"
      SONARR_API_KEY: "your-sonarr-key"

      # --- Seerr (legacy OVERSEERR_URL / OVERSEERR_API_KEY also accepted) ---
      SEERR_URL: "http://seerr:5055"
      SEERR_API_KEY: "your-seerr-key"

      # --- The core mapping: arr tag -> Plex label (unmapped tags ignored) ---
      TAG_LABEL_MAP: "niece-ok:kids-allowed,sister:shared"
      LABEL_REMOVAL: "reconcile"            # reconcile (add+remove) | add-only

      # --- Labeling features ---
      FEATURE_WEBHOOK: "true"
      FEATURE_SWEEP: "true"
      SWEEP_INTERVAL_MINUTES: "60"

      # --- Watched / stale notifications (Tautulli + Apprise) ---
      FEATURE_NOTIFY: "true"
      TAUTULLI_URL: "http://tautulli:8181"
      TAUTULLI_API_KEY: "your-tautulli-key"
      APPRISE_URLS: "discord://webhook_id/webhook_token"   # comma-separated
      NOTIFY_ON: "watched,stale"
      WATCHED_PERCENT: "85"
      STALE_AFTER_DAYS: "180"
      UNWATCHED_AFTER_DAYS: "90"
      WATCH_SCAN_INTERVAL_MINUTES: "360"

      # --- Web UI (served at http://host:8000/, same port) ---
      FEATURE_UI: "true"
      PAL_SECRET_KEY: "paste-a-fernet-key-here"   # see "Web UI" section to generate
      CONFIG_PATH: "/data/config.json"

      # --- Server / ops ---
      WEBHOOK_PATH: "/webhook/seerr"        # Seerr webhook route
      PLEX_WEBHOOK_PATH: "/webhook/plex"    # Plex webhook route (no Seerr config needed)
      WEBHOOK_SECRET: ""                    # if set, webhook URL needs ?token=THIS
      DRY_RUN: "false"                      # set true for a safe first run
      LOG_LEVEL: "info"
      TZ: "UTC"
      PUID: "1000"                          # match your host user if ./data perms bite
      PGID: "1000"
```

Then:

```bash
docker compose pull
docker compose up -d
docker compose logs -f
curl http://localhost:8000/health      # -> {"status":"ok"}
```

> **First run:** set `DRY_RUN: "true"` and watch the logs — you'll see the labels
> it *would* add/remove and the notifications it *would* send, without touching
> Plex. Flip to `"false"` when it looks right.

If Seerr runs on the same Docker network you can drop the `ports:` mapping and
point Seerr at `http://whitelistarr:8000` instead of the host.

## Web UI

With `FEATURE_UI=true` and a `PAL_SECRET_KEY` set, a config UI is served at
`http://<host>:8000/` (same port as the webhooks). It lets you view and edit **every**
setting in a grouped, dependency-aware form, plus an **Actions** panel (send test
notification, run sweep now, run reverse).

- **First run** seeds the config from your env vars. After that the **saved config is
  the source of truth** (env becomes a fallback) — manage everything from the browser.
- **Secrets** (tokens/API keys) are stored **encrypted** with `PAL_SECRET_KEY`. Generate
  one once — with OpenSSL (no Python needed):
  ```bash
  openssl rand -base64 32 | tr '+/' '-_'
  ```
  (or `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`)
- **Changes apply on restart** — saving shows a "restart to apply" banner.
- **No built-in auth.** The UI can edit secrets, so keep it behind your reverse proxy or
  a trusted network. (Secrets are never sent back to the browser in plaintext, and the
  data file is encrypted at rest.) Set `FEATURE_UI=false` to disable it.

If `FEATURE_UI=true` but `PAL_SECRET_KEY` is unset, the UI is disabled and the app runs
from env vars as before.

## Triggering immediate labeling

You only need **one** trigger (the periodic sweep is always a safety net). Pick either:

### Option A — Plex webhook (no Seerr config; recommended)

Plex fires `library.new` the instant it adds an item, so this is the most
accurate "on addition" trigger — and it also labels **manually-added** content,
not just Seerr requests. Requires Plex Pass (server owner).

In **Plex → Settings → Webhooks → Add Webhook**:

- **URL:** `http://whitelistarr:8000/webhook/plex` (or
  `http://<docker-host>:8000/webhook/plex`). If you set `WEBHOOK_SECRET`, append
  `?token=YOUR_SECRET`.

That's it — Plex posts a `library.new` event, the app fetches the item by its
ratingKey (resolving episodes up to their show) and reconciles labels.

### Option B — Seerr webhook

In **Seerr → Settings → Notifications → Webhook**:

- **Webhook URL:** `http://whitelistarr:8000/webhook/seerr` (or
  `http://<docker-host>:8000/webhook/seerr`). If you set `WEBHOOK_SECRET`, append
  `?token=YOUR_SECRET`.
- **Notification types:** enable **Media Available** (others are ignored).
- Keep the default JSON payload — the app reads `media.media_type`,
  `media.tmdbId` and `media.tvdbId` from it.
- Click **Test** (test pings are accepted and ignored), then **Save**.

### Option C — no webhook at all

Leave `FEATURE_SWEEP=true` and lower `SWEEP_INTERVAL_MINUTES` (e.g. to `5`). The
reconcile sweep then picks up new items within that window — simplest to operate,
at the cost of a little latency.

## Restrict your sister's share to the label (Plex)

This is the part that actually gates access (requires Plex Pass on your account):

1. **Plex → Settings → Users & Sharing → (the shared user) → Restrictions.**
2. Set the restriction **Profile** to **None** (required to edit label filters).
3. Under **Allow only items with these labels**, add the whitelist label you
   mapped in `TAG_LABEL_MAP` (e.g. `kids-allowed`).
4. Save. That user now sees only items carrying that label — which this app
   maintains automatically.

## Notifications (what fires, and testing them)

Pick which events notify via `NOTIFY_ON`:
- **labeled** — a ping when items are whitelisted **or un-whitelisted**. Sent as two
  separate, titled messages: **Label Added** (green) and **Label Removed** (orange).
  Each is grouped by media type (**Movies** / **TV Shows**) with the label shown as
  `inline code` and **every** affected item listed (no truncation). On **Discord**
  this renders as a clean color-coded embed; **Telegram** gets the same content as
  organized text. Deduped per item+label (add told once; a later removal then re-add
  announces again). Only needs `APPRISE_URLS` (no Tautulli). Add `labeled` to
  `NOTIFY_ON` to enable.
- **watched** — the requester watched an item past `WATCHED_PERCENT` (default 85%). Needs Tautulli + `FEATURE_NOTIFY=true`.
- **stale** — an item is older than `STALE_AFTER_DAYS` and unwatched for `UNWATCHED_AFTER_DAYS`. Needs Tautulli + `FEATURE_NOTIFY=true`.

With `DRY_RUN=true`, notifications are logged but **not sent**. So an empty inbox for
watched/stale usually just means nothing crossed those thresholds yet.

To confirm your channels actually work, set `NOTIFY_TEST_ON_START=true` — the app
sends one real test message at startup (this one ignores `DRY_RUN`). The startup
log also reports how many Apprise channels loaded, e.g.
`Notifications: 2/2 Apprise channel(s) loaded` (a lower number means a URL was
rejected).

## Undo — remove all labels

To strip the managed label(s) from your whole library (e.g. before uninstalling),
run once with `REVERSE=true`. It removes only the labels in your `TAG_LABEL_MAP`
(manual labels are untouched), then exits without starting the webhook/scheduler.
Dry-run it first:

```bash
docker run --rm --env-file .env -e REVERSE=true -e DRY_RUN=true orelmor/whitelistarr:latest
# happy with the log? run it for real:
docker run --rm --env-file .env -e REVERSE=true orelmor/whitelistarr:latest
```

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `PLEX_URL` / `PLEX_TOKEN` | — | Plex server + auth token |
| `PLEX_SECTIONS` | *(all)* | CSV of movie/show section names to process |
| `PLEX_DEVICE_NAME` | `Whitelistarr` | Device name shown in Plex → Settings → Devices |
| `PLEX_CLIENT_ID` | `whitelistarr` | Stable client id (avoids a new Plex device per restart) |
| `RADARR_URL` / `RADARR_API_KEY` | — | Radarr connection |
| `SONARR_URL` / `SONARR_API_KEY` | — | Sonarr connection |
| `SEERR_URL` / `SEERR_API_KEY` | — | Seerr connection (`OVERSEERR_*` also accepted) |
| `TAUTULLI_URL` / `TAUTULLI_API_KEY` | — | Tautulli (required if `FEATURE_NOTIFY=true`) |
| `TAG_LABEL_MAP` | — | `tag:label,tag:label` — which *arr tags become which Plex labels |
| `LABEL_REMOVAL` | `reconcile` | `reconcile` (add+remove) or `add-only` |
| `FEATURE_WEBHOOK` | `true` | Run the Seerr webhook receiver |
| `FEATURE_SWEEP` | `true` | Run the periodic reconcile sweep |
| `SWEEP_INTERVAL_MINUTES` | `60` | Sweep cadence |
| `FEATURE_NOTIFY` | `false` | Enable watched/stale notifications |
| `WATCH_SCAN_INTERVAL_MINUTES` | `360` | Watch-history scan cadence |
| `APPRISE_URLS` | — | CSV of [Apprise URLs](https://github.com/caronc/apprise/wiki) |
| `NOTIFY_ON` | `watched,stale` | Events to notify on: `labeled`, `watched`, `stale` |
| `NOTIFY_TEST_ON_START` | `false` | Send one real test notification at startup (ignores `DRY_RUN`) |
| `WATCHED_PERCENT` | `85` | % watched that counts as "finished" |
| `STALE_AFTER_DAYS` | `180` | Age before an item can be "stale" |
| `UNWATCHED_AFTER_DAYS` | `90` | No-watch window for "stale" |
| `FEATURE_UI` | `true` | Serve the config web UI at `/` (same port) |
| `PAL_SECRET_KEY` | — | Fernet key; required when UI on (encrypts secrets at rest) |
| `CONFIG_PATH` | `/data/config.json` | Where the UI persists config |
| `WEBHOOK_HOST` / `WEBHOOK_PORT` | `0.0.0.0` / `8000` | Webhook bind address |
| `WEBHOOK_PATH` | `/webhook/seerr` | Seerr webhook route |
| `PLEX_WEBHOOK_PATH` | `/webhook/plex` | Plex webhook route (Plex Pass) |
| `WEBHOOK_SECRET` | — | Optional `?token=` shared secret |
| `DRY_RUN` | `false` | Log intended changes without applying |
| `REVERSE` | `false` | One-shot: remove all managed labels from every item, then exit |
| `LOG_LEVEL` | `info` | Logging level |
| `STATE_DB_PATH` | `/data/state.db` | SQLite dedup DB path |
| `TZ` | `UTC` | Container timezone |
| `PUID` / `PGID` | `1000` / `1000` | User/group the container drops to (it starts as root, fixes `/data` ownership, then runs unprivileged). Set to your host user if the bind-mounted `./data` isn't writable. |

## Releases & CI (maintainer)

Releases are automated with [python-semantic-release](https://python-semantic-release.readthedocs.io/)
driven by [Conventional Commits](https://www.conventionalcommits.org/):

- Push/merge to **`dev`** → prerelease (`vX.Y.Z-dev.N`) + multi-arch image tagged
  `:dev` and `:X.Y.Z-dev.N` on Docker Hub + GHCR.
- Merge to **`main`** → stable release + GitHub Release/changelog + image tagged
  `:latest` and `:X.Y.Z`.
- Commit prefixes drive the bump: `feat:` → minor, `fix:` → patch, `feat!:` /
  `BREAKING CHANGE:` → major. `docs:`/`chore:`/`test:` → no release.
- Builds only run when the commits warrant a release (no version, no build).

The legacy manual flow below still works for local/emergency builds:

The repo's `docker-compose.yml` has both `image:` and `build:`, so:

```bash
docker compose build                         # builds orelmor/whitelistarr:latest
docker login                                 # as the orelmor Docker Hub user
docker compose push                          # publishes to Docker Hub

# Or directly, with an explicit version tag:
docker build -t orelmor/whitelistarr:latest -t orelmor/whitelistarr:0.1.0 .
docker push orelmor/whitelistarr:latest
docker push orelmor/whitelistarr:0.1.0
```

## Development

```bash
python -m venv .venv
. .venv/Scripts/activate      # Windows;  source .venv/bin/activate on Unix
pip install -e ".[dev]"
pytest
```

The codebase is test-driven (`tests/`). Pure logic (config parsing, label
reconcile, GUID matching, watched/stale rules) is unit-tested; HTTP clients are
tested against mocked responses (`respx`); Plex is tested via a fake video object.

## Limitations

- Movies and TV shows only.
- TV "fully watched" is approximate (a percent threshold); movies are exact.
- GUID matching depends on correct Plex agent metadata; unmatched items are
  logged during the sweep.
- Seerr→Radarr/Sonarr requester tagging must already be enabled.
