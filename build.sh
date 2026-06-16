#!/usr/bin/env bash
#
# Whitelistarr — build & publish
#
# Stamps the version into pyproject.toml + app/__init__.py, runs the test suite,
# builds the Docker image, smoke-tests it, tags both :<version> and :latest, and
# pushes both to Docker Hub.
#
# Usage:
#   ./build.sh [version] [--no-push]
# Examples:
#   ./build.sh 0.2.0
#   ./build.sh 0.2.0 --no-push
#   ./build.sh            # builds/pushes :latest only (no version stamp)
#
set -euo pipefail

VERSION="${1:-latest}"
NO_PUSH="${2:-}"
IMAGE_NAME="orelmor/whitelistarr"
START_TS=$(date +%s)

# ---------------------------------------------------------------------------
# Pretty, verbose logging
# ---------------------------------------------------------------------------
if [ -t 1 ]; then
  c_reset=$'\033[0m'; c_blue=$'\033[1;34m'; c_green=$'\033[1;32m'
  c_yellow=$'\033[1;33m'; c_red=$'\033[1;31m'; c_dim=$'\033[2m'
else
  c_reset=""; c_blue=""; c_green=""; c_yellow=""; c_red=""; c_dim=""
fi
log()  { printf "%s[%s]%s %s\n" "$c_dim" "$(date +%H:%M:%S)" "$c_reset" "$*"; }
step() { printf "\n%s━━ %s %s\n" "$c_blue" "$*" "$c_reset"; }
ok()   { printf "%s✅ %s%s\n" "$c_green" "$*" "$c_reset"; }
warn() { printf "%s⚠️  %s%s\n" "$c_yellow" "$*" "$c_reset"; }
die()  { printf "%s❌ %s%s\n" "$c_red" "$*" "$c_reset" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
step "Whitelistarr build"
log "Version : ${VERSION}"
log "Image   : ${IMAGE_NAME}"
log "Push    : $([ "$NO_PUSH" = "--no-push" ] && echo no || echo yes)"
log "Docker  : $(docker --version 2>/dev/null || echo 'NOT FOUND')"
log "PWD     : $(pwd)"

command -v docker >/dev/null 2>&1 || die "docker not found on PATH"
[ -f pyproject.toml ] || die "run this from the repo root (pyproject.toml not found)"

# ---------------------------------------------------------------------------
# Stamp version (LF-safe sed; skipped when VERSION=latest)
# ---------------------------------------------------------------------------
if [ "$VERSION" != "latest" ]; then
  step "Stamping version ${VERSION}"
  sed -i 's/^version = "[^"]*"/version = "'"$VERSION"'"/' pyproject.toml
  grep -q "^version = \"$VERSION\"" pyproject.toml || die "failed to update pyproject.toml"
  ok "pyproject.toml -> ${VERSION}"
  sed -i 's/^__version__ = "[^"]*"/__version__ = "'"$VERSION"'"/' app/__init__.py
  grep -q "^__version__ = \"$VERSION\"" app/__init__.py || die "failed to update app/__init__.py"
  ok "app/__init__.py -> ${VERSION}"
else
  warn "VERSION=latest: not stamping a version number"
fi

# ---------------------------------------------------------------------------
# Test suite (gate — abort the build if anything fails)
# ---------------------------------------------------------------------------
step "Running test suite"
if   [ -x .venv/Scripts/python.exe ]; then PY=".venv/Scripts/python.exe"
elif [ -x .venv/bin/python ];         then PY=".venv/bin/python"
else PY="python"; fi
log "Interpreter: ${PY}"
"$PY" -m pytest -q || die "tests failed — aborting build"
ok "All tests passed"

# ---------------------------------------------------------------------------
# Build image (tags both :version and :latest in one build)
# ---------------------------------------------------------------------------
step "Building Docker image"
BUILD_TAGS=(-t "${IMAGE_NAME}:latest")
if [ "$VERSION" != "latest" ]; then
  BUILD_TAGS+=(-t "${IMAGE_NAME}:${VERSION}")
fi
log "Tags: $(printf '%s ' "${BUILD_TAGS[@]}" | sed 's/-t //g')"
docker build "${BUILD_TAGS[@]}" . || die "docker build failed"
ok "Image built"

# ---------------------------------------------------------------------------
# Smoke test (import check — does not need live Plex/Seerr/etc.)
# ---------------------------------------------------------------------------
step "Smoke-testing image"
docker run --rm --entrypoint python "${IMAGE_NAME}:latest" -c \
  "import app.main, app.webhook, app.scheduler; from app import __version__; print('imports OK, version', __version__)" \
  || die "smoke test failed"
ok "Smoke test passed"

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------
if [ "$NO_PUSH" = "--no-push" ]; then
  warn "Skipping push (--no-push)"
  log "Push manually with:"
  [ "$VERSION" != "latest" ] && log "  docker push ${IMAGE_NAME}:${VERSION}"
  log "  docker push ${IMAGE_NAME}:latest"
else
  step "Pushing to Docker Hub"
  if [ "$VERSION" != "latest" ]; then
    log "Pushing ${IMAGE_NAME}:${VERSION} ..."
    docker push "${IMAGE_NAME}:${VERSION}" || die "push ${VERSION} failed (run 'docker login' first?)"
    ok "Pushed ${IMAGE_NAME}:${VERSION}"
  fi
  log "Pushing ${IMAGE_NAME}:latest ..."
  docker push "${IMAGE_NAME}:latest" || die "push latest failed (run 'docker login' first?)"
  ok "Pushed ${IMAGE_NAME}:latest"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
ELAPSED=$(( $(date +%s) - START_TS ))
step "Done in ${ELAPSED}s"
ok "Built ${IMAGE_NAME}:${VERSION}$([ "$VERSION" != "latest" ] && echo " + :latest")"
