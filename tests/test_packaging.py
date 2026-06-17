"""Guards that the web UI's static assets actually ship in the built package.

The Docker image installs Whitelistarr non-editably, so any static file that
isn't covered by package-data 404s at runtime. These tests fail fast if the
allowlist drifts from disk or the recursive glob regresses.
"""

import tomllib
from pathlib import Path

from app.webui import _STATIC_NAMES, STATIC_DIR

ROOT = Path(__file__).resolve().parents[1]


def test_all_allowlisted_static_files_exist():
    for name in _STATIC_NAMES:
        assert (STATIC_DIR / name).is_file(), f"missing packaged static file: {name}"


def test_package_data_ships_static_subfolders():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["app"]
    # A recursive glob is required, or files under static/js, static/css,
    # static/vendor never make it into the wheel.
    assert any("**" in g for g in globs), globs
