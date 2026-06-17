"""Run the JS pure-helper tests via Node's built-in test runner.

Keeps the frontend's pure logic under test without adding a JS toolchain. Skips
cleanly where Node isn't installed (the Python suite stays the source of truth).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_helpers_pass():
    test_files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.js"))
    assert test_files, "no JS test files found"
    result = subprocess.run(
        ["node", "--test", *test_files],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
