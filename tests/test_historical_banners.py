"""The "Historical" banner stays on every report / paper source that quotes superseded numbers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "add_historical_banners.py"


def _load():  # noqa: ANN202 -- loads a script as a module
    spec = importlib.util.spec_from_file_location("add_historical_banners", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_listed_file_exists_and_carries_the_banner() -> None:
    mod = _load()
    results = {f: mod.apply(f, write=False) for f in mod.FILES}
    assert all(r == "present" for r in results.values()), {
        f: r for f, r in results.items() if r != "present"
    }


def test_banner_text_is_the_agreed_sentence() -> None:
    assert _load().TEXT == (
        "Historical \u2014 numbers superseded; see README (re-measured 2026-10-11)."
    )
