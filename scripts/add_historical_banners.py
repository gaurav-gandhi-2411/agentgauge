"""Prepend a one-line "Historical" banner to every report / paper source that still carries
numbers superseded by the 2026-10-11 re-measurement (per-trial seeds; see README).

The file list is explicit (below), not discovered, so a run is reproducible and reviewable. It was
produced by sweeping reports/*.md, docs/paper/**, docs/paper2/*.{md,tex} and docs/research/*.md
for these shapes of the old figures: 90.3% / 90.28 / 650 of 720 / 0.903, ICC 0.793, MDE 0.0848 /
0.085, MDE 0.0537 / 0.054, false alarm 13/2200 / 0.59% / 21.6%, 10/2200 / 0.45%, resid_sd 0.139,
sigma_task 0.3588 / 0.359, baseline 0.7749 / 0.775, variance shares 56.1% / 18.0%, and the pooled
"-13.3 to -28.9 pp" type_enum figure. Files matching only the phrase "fixed seed" in an unrelated
sense (diff-engine determinism, PRNG state) are not included.

Markdown files get a blockquote line; .tex files get a comment (so the compiled PDF, which is not
rebuilt here, is unchanged). Idempotent. Run: python scripts/add_historical_banners.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEXT = "Historical — numbers superseded; see README (re-measured 2026-10-11)."

FILES = [
    "docs/paper2/SUBMISSION.md",
    "docs/paper2/gaps.md",
    "docs/paper2/main.tex",
    "docs/paper2/provenance.md",
    "reports/capability_statement.md",
    "reports/v0_4_0_effect_size_reconciliation.md",
    "reports/v0_4_0_pre_publication_claim_audit.md",
    "reports/v0_4_0_release_verification.md",
    "reports/v0_4_0_task1_argument_degradation.md",
    "reports/v0_5_attribution_benchmark.md",
    "reports/v0_5_effect_size_sensitivity.md",
    "reports/v0_5_mde_discrepancy.md",
    "reports/v0_5_probe_power_fix.md",
    "reports/v0_5_scale_curve.md",
    "reports/v0_5_shapley_scaling_audit.md",
    "reports/v0_5_wave1_report.md",
    "reports/v2_1_cross_model_validation.md",
    "reports/v2_1_estimator_rebuild.md",
    "reports/v2_2_optimal_allocation.md",
    "reports/v2_2_task_a_reallocation.md",
    "reports/v2_2_task_b_causal_chain_multimodel.md",
    "reports/v2_3_task1_advisory_audit.md",
    "reports/v2_4_task1_blast_radius_audit.md",
    "reports/v2_4_task4_corpus_expansion.md",
    "reports/v2_5_task3_mde_completion.md",
    "reports/v2_product_readiness.md",
    "reports/v2_variance_structure.md",
]


def _banner(path: str) -> str:
    return f"% {TEXT}" if path.endswith(".tex") else f"> {TEXT}"


def apply(path: str, *, write: bool) -> str:
    """Return 'added', 'present' or 'missing'; write only when asked."""
    p = ROOT / path
    if not p.exists():
        return "missing"
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    if text.startswith(_banner(path)):
        return "present"
    nl = "\r\n" if "\r\n" in text else "\n"
    new = (
        f"{_banner(path)}{nl}{nl}" + text
        if not path.endswith(".tex")
        else _banner(path) + nl + text
    )
    if write:
        p.write_bytes(new.encode("utf-8"))
    return "added"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if any file lacks the banner")
    args = ap.parse_args()
    results = {f: apply(f, write=not args.check) for f in FILES}
    for f, r in results.items():
        print(f"{r:8s} {f}")
    bad = [f for f, r in results.items() if r == "missing" or (args.check and r != "present")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
