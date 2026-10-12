# recalibration_seedfix

Re-measurement of the harness calibration with a **distinct sampler seed per (task, trial)**.

| File | What it is |
|---|---|
| `rows.ndjson` | Raw trial rows, one per trial: 5,535 rows, 44 tool sets (the same tool sets, tasks and trial count as `../predictive_validity/results_raw.json`). Includes `constructed_args`, `seed`, `selected_tool`, `constraint_satisfaction`. |
| `run_status.json` | Which tool sets completed (all 44), wall-clock cap (7.5 h, not hit). |
| `results.json`, `results.md` | `scripts/recalibration_analyze.py` output: old-vs-new variance structure, calibration constants, MDE, null false-alarm and abstention, with cluster-bootstrap / Wilson CIs. |
| `output_diversity.json` | `scripts/recalibration_output_diversity.py`: of the zero-variance groups, identical vs differing tool calls. |
| `zero_variance_audit.json` | `scripts/recalibration_zero_variance_audit.py`: the selected-tool-differs and arguments-differ groups, constraint coverage, a seeded sample of 10. |
| `decoding_temperature_check.json` | `scripts/verify_decoding_temperature.py`: logged request body, sampler control, 10 tasks x 10 seeds. |
| `MANIFEST.json` | sha256 of the analysis inputs and script. |

## How `rows.ndjson` was produced

```
.venv/Scripts/python.exe scripts/recalibration_collect.py --out <dir> --max-hours 7.5
```

- Code: `agentgauge.runner.run_tasks(..., trials=5, base_seed=42)` at commit `4c3ba84`
  (`trial_seed = sha256(base_seed, tool, description, trial_index)`), run from a git worktree pinned
  there so later edits could not affect it.
- Model: `gemma2:9b` (Ollama `ff02c3702f32`), Ollama 0.33.3, local RTX 3070 Laptop (8 GB), one machine.
  The adapter sends only `options.seed`; the Modelfile sets no temperature, so Ollama's runtime
  default sampler applies (verified above zero: `decoding_temperature_check.json`).
- Started 2026-10-11 (IST morning), finished 2026-10-11T09:32:18Z. About 2.4 s/trial for small
  catalogs, up to about 5 s/trial for large ones.
- Judge and `score_all` are not run (ground-truth loop only), unlike the original study.
- The original corpus was partly collected through a Cloud Run proxy (one record shows a 404 from
  `localhost:11435`); this one is entirely local. Backend differences between the two corpora are
  therefore possible and are not controlled.

## Reproduce

```
python scripts/recalibration_analyze.py --rows evals/fixtures/recalibration_seedfix/rows.ndjson \
  --old evals/fixtures/predictive_validity/results_raw.json --out <dir> --mde-sims 2000 --workers 4
python scripts/recalibration_output_diversity.py --check
python scripts/recalibration_zero_variance_audit.py --check
python scripts/render_readme_metrics.py --check
```

The analysis step needs no model and no GPU; the MDE grid takes about an hour on 4 CPU workers.
Re-collecting `rows.ndjson` needs the same local model and takes several hours; exact token-level
equality with this file is not guaranteed across Ollama builds.
