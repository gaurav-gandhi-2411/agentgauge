"""scripts/check_launch_claims.py: drafts must trace to committed sources, failing closed.

Runs against tiny synthetic trees (every failure constructed on purpose) and once against the real
tree for the working-tree-only claims. No network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_launch_claims", _ROOT / "scripts" / "check_launch_claims.py"
)
assert _spec and _spec.loader
clc = importlib.util.module_from_spec(_spec)
sys.modules["check_launch_claims"] = clc
_spec.loader.exec_module(clc)

DRAFT = "docs/launch/d.md"


def _tree(tmp_path: Path, draft: str, claims: list[dict], allowed: dict | None = None) -> Path:
    (tmp_path / "docs" / "launch").mkdir(parents=True)
    (tmp_path / "src.md").write_text("The MDE is 8.5 points\nat 80% power.\n", encoding="utf-8")
    (tmp_path / DRAFT).write_text(draft, encoding="utf-8")
    spec = {"drafts": [DRAFT], "claims": claims, "allowed_numbers": allowed or {}}
    (tmp_path / "docs" / "launch" / "claims.json").write_text(json.dumps(spec), encoding="utf-8")
    return tmp_path


def _claim(**kw: object) -> dict:
    base = {
        "id": "c1",
        "source": "src.md",
        "quote": "MDE is 8.5 points at 80% power",
        "numbers": ["8.5", "80"],
        "appears_in": {DRAFT: "the MDE is 8.5 points"},
    }
    base.update(kw)
    return base


def _run(root: Path) -> list[str]:
    errors, _, _ = clc.run(root, root / "docs" / "launch" / "claims.json")
    return errors


def test_valid_tree_passes(tmp_path: Path) -> None:
    root = _tree(tmp_path, "Here the MDE is 8.5 points at 80% power.\n", [_claim()])
    assert _run(root) == []


def test_quote_survives_line_wraps(tmp_path: Path) -> None:
    root = _tree(tmp_path, "the MDE is 8.5\npoints.\n", [_claim(numbers=["8.5"])])
    assert _run(root) == []


def test_missing_quote_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "the MDE is 8.5 points\n", [_claim(quote="MDE is 9.9 points")])
    assert any("quote not found" in e for e in _run(root))


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, "the MDE is 8.5 points\n", [_claim(source="nope.md")])
    assert any("source unavailable" in e for e in _run(root))


def test_missing_git_ref_fails_closed(tmp_path: Path) -> None:
    root = _tree(tmp_path, "the MDE is 8.5 points\n", [_claim(ref="origin/does-not-exist")])
    assert any("source unavailable" in e for e in _run(root))


def test_phrase_missing_from_draft_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "something else entirely\n", [_claim()])
    assert any("phrase not found" in e for e in _run(root))


def test_unvouched_number_in_prose_fails(tmp_path: Path) -> None:
    draft = "the MDE is 8.5 points and we saw 42 users.\n"
    root = _tree(tmp_path, draft, [_claim(numbers=["8.5"])])
    assert any("'42'" in e for e in _run(root))


def test_allowed_number_is_permitted(tmp_path: Path) -> None:
    draft = "the MDE is 8.5 points under Apache-2.0.\n"
    root = _tree(tmp_path, draft, [_claim(numbers=["8.5"])], {DRAFT: {"2.0": "licence"}})
    assert _run(root) == []


def test_number_not_in_quote_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, "the MDE is 8.5 points\n", [_claim(numbers=["8.5", "99"])])
    assert any("'99' is not in the claim's quote" in e for e in _run(root))


def test_absent_claim(tmp_path: Path) -> None:
    good = _claim(quote="OLLAMA", absent=True, numbers=[])
    ok = _tree(tmp_path, "the MDE is 8.5 points\n", [good], {DRAFT: {"8.5": "unclaimed here"}})
    assert _run(ok) == []
    bad = _claim(quote="MDE is 8.5", absent=True, numbers=[])
    (ok / "docs" / "launch" / "claims.json").write_text(
        json.dumps({"drafts": [DRAFT], "claims": [bad], "allowed_numbers": {DRAFT: {"8.5": "x"}}}),
        encoding="utf-8",
    )
    assert any("must be ABSENT" in e for e in _run(ok))


def test_broken_repo_link_fails(tmp_path: Path) -> None:
    draft = f"the MDE is 8.5 points ([x]({clc.REPO_URL}main/missing.md))\n"
    root = _tree(tmp_path, draft, [_claim(numbers=["8.5"])])
    assert any("does not resolve" in e for e in _run(root))


def test_good_repo_link_passes(tmp_path: Path) -> None:
    draft = f"the MDE is 8.5 points ([x]({clc.REPO_URL}main/src.md))\n"
    root = _tree(tmp_path, draft, [_claim(numbers=["8.5"])])
    assert _run(root) == []


def test_prose_numbers_ignores_banner_code_models_and_links() -> None:
    text = (
        "> banner 99\n`code 11` gemma2:9b llama3.1:8b [a](http://x/22) http://y/33\n"
        "    indented 44\nreal 5% and 1.57 and 13/20\n"
    )
    assert clc.prose_numbers(text) == {"5", "1.57", "13", "20"}


def test_real_launch_claims_are_well_formed() -> None:
    spec = json.loads((_ROOT / "docs" / "launch" / "claims.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in spec["claims"]]
    assert len(ids) == len(set(ids))
    assert all(c["appears_in"] and c["quote"] for c in spec["claims"])


def test_bare_url_good_and_broken() -> None:
    """Show HN / LinkedIn carry bare URLs (no markdown): they must be checked too."""
    ok = f"see {clc.REPO_URL}main/src.md for details.\n"
    errs = clc.check_links(_ROOT / "tests", {"d": ok})
    # tests/src.md does not exist, so a bare URL with trailing '.' must still be resolved and fail.
    assert any("does not resolve" in e and e.endswith("main/src.md") for e in errs)


def test_bare_url_in_tree_passes_and_missing_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, f"the MDE is 8.5 points\nSrc: {clc.REPO_URL}main/src.md\n", [_claim()])
    assert _run(root) == []
    (root / DRAFT).write_text(
        f"the MDE is 8.5 points\nSrc: {clc.REPO_URL}main/nope.md\n", encoding="utf-8"
    )
    assert any("does not resolve" in e for e in _run(root))


def test_unknown_branch_and_unsupported_url_forms_fail_closed(tmp_path: Path) -> None:
    unknown = f"the MDE is 8.5 points {clc.REPO_URL}some-branch/src.md\n"
    assert any("unknown branch" in e for e in clc.check_links(tmp_path, {"d": unknown}))
    tree_url = f"the MDE is 8.5 points {clc.REPO_ROOT}/tree/main/docs\n"
    assert any("unsupported repo URL form" in e for e in clc.check_links(tmp_path, {"d": tree_url}))
    root_only = f"code: {clc.REPO_ROOT}. And {clc.REPO_ROOT}\n"
    assert clc.check_links(tmp_path, {"d": root_only}) == []
    no_path = f"x {clc.REPO_URL}main/\n"
    assert any(
        "no file path" in e or "does not resolve" in e
        for e in clc.check_links(tmp_path, {"d": no_path})
    )


def test_commit_permalink_resolves_only_for_a_real_commit(tmp_path: Path) -> None:
    import subprocess

    (tmp_path / "f.md").write_text("hello\n", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S603, S607
    subprocess.run(["git", "add", "f.md"], cwd=tmp_path, check=True)  # noqa: S603, S607
    subprocess.run([*git, "commit", "-q", "-m", "x"], cwd=tmp_path, check=True)  # noqa: S603
    sha = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    good = f"[x]({clc.REPO_URL}{sha}/f.md)\n"
    assert clc.check_links(tmp_path, {"d": good}) == []
    missing_file = f"[x]({clc.REPO_URL}{sha}/g.md)\n"
    assert any("does not resolve" in e for e in clc.check_links(tmp_path, {"d": missing_file}))
    fake = f"[x]({clc.REPO_URL}{'0' * 40}/f.md)\n"
    assert any("does not resolve" in e for e in clc.check_links(tmp_path, {"d": fake}))
