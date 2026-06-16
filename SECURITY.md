# Security Policy

## Supported versions

The latest stable release (Docker tag `:latest`) receives security fixes.
Prereleases (`:dev`) are best-effort and may change without notice.

## Reporting a vulnerability

**Please do not open public issues for security problems.**

Use GitHub's private vulnerability reporting:
**Security → Report a vulnerability** on this repository
(https://github.com/orel-mor/Whitelistarr/security/advisories/new).

Include where possible:
- affected version / image tag,
- a description and impact,
- steps to reproduce or a proof of concept.

You'll get an acknowledgement as soon as possible, and a fix or mitigation will
be coordinated privately before any public disclosure.

## Scope notes

This service holds API tokens for Plex, Radarr/Sonarr, Seerr and Tautulli, and
(when the web UI is enabled) encrypts them at rest with `PAL_SECRET_KEY`. The UI
has **no built-in authentication** — run it behind a reverse proxy or on a
trusted network. See the README "Web UI" section.
