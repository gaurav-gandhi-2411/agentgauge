"""scripts/check_launch_claims.py -- every factual claim and number in docs/launch/ drafts must
trace to a committed source.

`docs/launch/claims.json` lists claims. Each has a source file (working tree, or a git ref via
`git show` for files that only exist on an unmerged branch), a literal quote that must be found in
that source (whitespace-normalised), the numbers it vouches for, and the draft phrase(s) it backs.
Checks, all fail-closed (a missing file, ref, or quote is a failure, never a skip):

1. every claim's source exists and contains its quote (or, with "absent": true, does NOT);
2. every claim's draft phrase literally appears in the named draft;
3. every claimed number appears in the claim's quote;
4. every number in a draft's prose is vouched for by a claim for that draft, or is explicitly
   allowed with a reason (so an unsourced number cannot slip in);
5. every GitHub blob URL in a draft -- markdown `[t](url)` or a bare URL (Show HN and LinkedIn
   do not render markdown) -- resolves to a real file at the ref it names. A branch name, or a
   40-hex commit permalink (`blob/<sha>/path`), is accepted; any other repo URL form is a failure.

Usage: python scripts/check_launch_claims.py [--root DIR] [--claims PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = "https://github.com/gaurav-gandhi-2411/agentgauge"
REPO_URL = REPO_ROOT + "/blob/"
# Branch name (as it appears in a blob URL) -> git refs whose tree defines that URL's files.
# "main" links must resolve in the working tree or, post-merge, on the gw correction branch.
BRANCH_REFS: dict[str, list[str | None]] = {
    "main": [None, "origin/docs/gw-truncation-correction"],
    "fix/ollama-num-ctx": ["origin/fix/ollama-num-ctx"],
}

_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_MODEL_NAME = re.compile(r"\b[a-z][a-z0-9.-]*:\d+b\b")
_INLINE_CODE = re.compile(r"`[^`]*`")
_BARE_URL = re.compile(r"https?://\S+")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")
# Matches a blob URL wherever it appears: inside a markdown link target or bare in prose. The
# character class stops at whitespace, `)`, `]`, `>` and quotes; trailing sentence punctuation is
# stripped by the caller.
_BLOB_URL = re.compile(re.escape(REPO_URL) + r"[^\s)\]>\"']+")
# Any repo URL that is not the bare root and not a /blob/ URL (tree/raw/commit/...): the checker
# cannot verify those, so they fail closed instead of slipping through unchecked.
_OTHER_REPO_URL = re.compile(re.escape(REPO_ROOT) + r"/(?!blob/)[^\s)\]>\"']+")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


def norm(text: str) -> str:
    """Collapse all whitespace so quotes survive hard line-wraps in source and drafts."""
    return " ".join(text.split())


def read_source(root: Path, path: str, ref: str | None) -> str:
    """Return a file's text from the working tree (ref None) or `git show ref:path`.

    Raises FileNotFoundError on a missing file or ref so callers fail closed.
    """
    if ref is None:
        p = root / path
        if not p.is_file():
            raise FileNotFoundError(f"{path} (working tree)")
        return p.read_text(encoding="utf-8")
    proc = subprocess.run(  # noqa: S603 -- fixed argv, no shell
        ["git", "show", f"{ref}:{path}"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise FileNotFoundError(f"{path} at {ref}: {proc.stderr.strip()}")
    return proc.stdout


def prose_numbers(text: str) -> set[str]:
    """Numbers in a draft's prose: excludes banners, links, code, model names, URLs, comments."""
    keep = [
        ln
        for ln in text.splitlines()
        if not ln.lstrip().startswith((">", "<!--", "#", "**URL", "**Flair"))
        and not ln.startswith("    ")
    ]
    body = "\n".join(keep)
    for pat in (_LINK_TARGET, _INLINE_CODE, _BARE_URL, _MODEL_NAME):
        body = pat.sub(" ", body)
    return {m.group(0).rstrip(".,") for m in _NUMBER.finditer(body)}


def check_links(root: Path, drafts: dict[str, str]) -> list[str]:
    """Every repo blob URL (markdown or bare) must resolve at the ref its first segment names."""
    errors: list[str] = []
    for name, text in drafts.items():
        for m in _OTHER_REPO_URL.finditer(text):
            url = m.group(0).rstrip(".,;:")
            if url.rstrip("/") != REPO_ROOT:
                errors.append(f"{name}: unsupported repo URL form (only /blob/ is checked): {url}")
        for m in _BLOB_URL.finditer(text):
            url = m.group(0).rstrip(".,;:")
            rest = url[len(REPO_URL) :]
            match = next((b for b in BRANCH_REFS if rest.startswith(b + "/")), None)
            if match is not None:
                path = rest[len(match) + 1 :]
                refs: list[str | None] = BRANCH_REFS[match]
            else:
                head, _, path = rest.partition("/")
                if not _COMMIT_SHA.fullmatch(head):
                    errors.append(f"{name}: link to unknown branch: {url}")
                    continue
                refs = [head]
            if not path:
                errors.append(f"{name}: link has no file path: {url}")
                continue
            ok = False
            for ref in refs:
                try:
                    read_source(root, path, ref)
                    ok = True
                    break
                except FileNotFoundError:
                    continue
            if not ok:
                errors.append(f"{name}: link does not resolve: {url}")
    return errors


def run(root: Path, claims_path: Path) -> tuple[list[str], int, int]:
    """Run all checks. Returns (errors, claims_checked, numbers_checked)."""
    errors: list[str] = []
    spec = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = spec["claims"]
    allowed: dict[str, dict[str, str]] = spec.get("allowed_numbers", {})
    draft_names = spec["drafts"]
    drafts: dict[str, str] = {}
    for d in draft_names:
        try:
            drafts[d] = (root / d).read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"draft missing: {d} ({exc})")
    vouched: dict[str, set[str]] = {d: set() for d in drafts}
    n_numbers = 0
    for c in claims:
        cid = c["id"]
        try:
            src = norm(read_source(root, c["source"], c.get("ref")))
        except FileNotFoundError as exc:
            errors.append(f"{cid}: source unavailable: {exc}")
            continue
        quote = norm(c["quote"])
        found = quote in src
        if c.get("absent"):
            if found:
                errors.append(f"{cid}: quote must be ABSENT from {c['source']} but was found")
        elif not found:
            errors.append(f"{cid}: quote not found in {c['source']}: {quote!r}")
        for num in c.get("numbers", []):
            n_numbers += 1
            if num not in quote:
                errors.append(f"{cid}: number {num!r} is not in the claim's quote")
        for d, phrase in c["appears_in"].items():
            if d not in drafts:
                errors.append(f"{cid}: names unknown draft {d}")
            elif norm(phrase) not in norm(drafts[d]):
                errors.append(f"{cid}: phrase not found in {d}: {phrase!r}")
            else:
                vouched[d].update(c.get("numbers", []))
    for d, text in drafts.items():
        ok = vouched[d] | set(allowed.get(d, {}))
        for num in sorted(prose_numbers(text) - ok):
            errors.append(f"{d}: number {num!r} in prose has no claim and is not allowed")
    errors += check_links(root, drafts)
    return errors, len(claims), n_numbers


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit 0 only if every check passes."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--claims", type=Path, default=None)
    args = ap.parse_args(argv)
    claims_path = args.claims or args.root / "docs" / "launch" / "claims.json"
    try:
        errors, n_claims, n_nums = run(args.root, claims_path)
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot run check: {exc}")  # noqa: T201
        return 1
    for e in errors:
        print(f"FAIL: {e}")  # noqa: T201
    status = "OK" if not errors else "FAILED"
    print(  # noqa: T201
        f"check_launch_claims: {status} -- {n_claims} claims, {n_nums} numbers, "
        f"{len(errors)} failures"
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
