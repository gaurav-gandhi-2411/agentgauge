"""The version agentgauge reports must be the version it is built and documented as.

``tests/test_check_release_version.py`` already proves ``pyproject.toml``, ``agentgauge/__init__.py`` and
``uv.lock`` agree on the real tree. This adds the two sources that file cannot see: the INSTALLED
metadata (which is what ``agentgauge --version`` and ``pip`` report, and what goes stale when an
editable install outlives a version bump) and ``CHANGELOG.md``'s newest release heading.

If the installed-metadata test fails right after bumping ``pyproject.toml`` locally, the venv's editable
install still carries the old version: run ``uv sync --extra dev`` (CI always syncs fresh).
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path

import agentgauge

_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_installed_metadata_and_dunder_version_equal_pyproject():
    expected = _pyproject_version()

    assert installed_version("agentgauge-harness") == expected, (
        "installed agentgauge-harness metadata differs from pyproject.toml: run `uv sync --extra dev`"
    )
    assert agentgauge.__version__ == expected


def test_changelogs_newest_release_heading_is_this_version():
    text = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[(\d[^\]\s]*)\]", text, re.M)

    assert m, "CHANGELOG.md has no `## [x.y.z]` release heading"
    assert m[1] == _pyproject_version(), (
        "CHANGELOG.md's newest release heading is not the version in pyproject.toml: "
        "a version bump needs its CHANGELOG entry (RELEASING.md)"
    )
