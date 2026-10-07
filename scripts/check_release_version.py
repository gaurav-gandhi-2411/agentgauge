"""Refuse a release whose version sources disagree, or whose version is already on PyPI.

agentgauge-harness keeps its version in three places that nothing derives from each other
(``pyproject.toml`` ``[project].version``, ``agentgauge/__init__.py`` ``__version__``, and
``uv.lock``'s self-referential entry for the project), plus the git tag that triggers the release.
RELEASING.md step 1 lists the drift as a known failure of the sibling repos; this makes it a
blocking check in ``release.yml`` instead of a sentence in a document.

Checks (any failure exits 1 and names every disagreement):
  * pyproject version == ``__version__`` == the project's entry in ``uv.lock``;
  * with ``--tag vX.Y.Z``: the tag (leading ``v`` stripped) == that version;
  * with ``--pypi``: the version is NOT already published (a duplicate upload cannot succeed, and
    finding out at the publish step is later than needed).
Anything it cannot determine (file unreadable, version line not found, PyPI unreachable) is exit 2,
never a pass: a guard that skips on error is the failure it exists to prevent.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

PACKAGE = "agentgauge-harness"
_INIT_VERSION = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$', re.M)


class CannotDetermine(RuntimeError):
    """A version source could not be read: reported as exit 2, never treated as agreement."""


def pyproject_version(root: Path) -> str:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise CannotDetermine(f"pyproject.toml [project].version: {exc!r}") from exc


def init_version(root: Path) -> str:
    try:
        text = (root / "agentgauge" / "__init__.py").read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotDetermine(f"agentgauge/__init__.py: {exc!r}") from exc
    m = _INIT_VERSION.search(text)
    if not m:
        raise CannotDetermine('agentgauge/__init__.py: no `__version__ = "..."` line')
    return m[1]


def lock_version(root: Path) -> str:
    try:
        data = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CannotDetermine(f"uv.lock: {exc!r}") from exc
    found = [p["version"] for p in data.get("package", []) if p.get("name") == PACKAGE]
    if len(found) != 1:
        raise CannotDetermine(f"uv.lock: expected one `{PACKAGE}` entry, found {len(found)}")
    return str(found[0])


def pypi_has(version: str) -> bool:
    """True if PyPI already serves this version. Any other outcome than a clean 200/404 raises."""
    url = f"https://pypi.org/pypi/{PACKAGE}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=20):  # noqa: S310 -- fixed https URL
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise CannotDetermine(f"PyPI answered HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CannotDetermine(f"PyPI unreachable ({exc!r})") from exc


def check(
    root: Path,
    tag: str | None = None,
    pypi: Callable[[str], bool] | None = None,
) -> list[str]:
    """Every problem found; empty means the release may proceed. Raises CannotDetermine."""
    problems: list[str] = []
    versions = {
        "pyproject.toml": pyproject_version(root),
        "agentgauge/__init__.py": init_version(root),
        "uv.lock": lock_version(root),
    }
    if len(set(versions.values())) != 1:
        problems.append(
            "version sources disagree: "
            + ", ".join(f"{k}={v}" for k, v in versions.items())
            + " (RELEASING.md step 1: bump all of them, run `uv sync`)"
        )
    version = versions["pyproject.toml"]
    if tag is not None:
        if not re.fullmatch(r"v\d[^\s]*", tag):
            problems.append(f"tag {tag!r} is not of the form vX.Y.Z")
        elif tag[1:] != version:
            problems.append(f"tag {tag} does not match the package version {version}")
    if pypi is not None and pypi(version):
        problems.append(f"{PACKAGE} {version} is already on PyPI; bump the version")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--tag", help="the release tag (vX.Y.Z); omit on a dry run with no tag")
    ap.add_argument("--pypi", action="store_true", help="also refuse a version already on PyPI")
    args = ap.parse_args(argv)
    try:
        problems = check(args.root, args.tag, pypi_has if args.pypi else None)
    except CannotDetermine as exc:
        print(f"::error::cannot determine the release version state: {exc}")
        return 2
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    print(
        f"release version OK: {pyproject_version(args.root)}"
        + (f" (tag {args.tag})" if args.tag else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
