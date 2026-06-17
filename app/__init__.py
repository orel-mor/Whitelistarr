"""Whitelistarr: sync Sonarr/Radarr tags to Plex labels and notify on watch milestones."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("whitelistarr")
except PackageNotFoundError:  # running from source without an install
    __version__ = "0.0.0+unknown"
