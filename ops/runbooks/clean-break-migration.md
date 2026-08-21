# Clean-break migration: agentgauge-judge (expense-tracker-498014) → agentgauge-prod-260813

Target billing account: `01285B-91E4CB-70AD7E`. Separate project from expense-tracker per the
approved plan (co-tenancy avoidance). GPU-quota-gated the same way AetherArt is — do not treat
this as part of the "easy batch"; file its quota request alongside AetherArt's, first.

## 0. Prerequisites — the actual gating step

```
gcloud projects create agentgauge-prod-260813 --name="AgentGauge Judge"
gcloud billing projects link agentgauge-prod-260813 --billing-account=01285B-91E4CB-70AD7E
```
File the `nvidia_l4_gpu_allocation_no_zonal_redundancy` (region `us-central1`) quota request
against this project immediately once it exists — same quota metric as AetherArt, separate
request because it's a separate project. Enable `run.googleapis.com`.

## 1. Model weights — regenerate, don't migrate

`gs://agentgauge-judge-models-expense-tracker` holds the pulled Ollama model weights. No need to
copy this bucket — it's fully regenerable:
```
gcloud storage buckets create gs://agentgauge-judge-models-agentgauge-prod \
  --project=agentgauge-prod-260813 --location=us-central1
```
Model gets populated on first pull once the service is deployed (or pre-warm with a one-off
`ollama pull llama3.1:8b` against the new service before considering it ready).

**CRITICAL — do not change the model.** Per `agentgauge/CLAUDE.md`: the judge must remain exactly
`llama3.1:8b` — all rubric calibration (error_legibility, description_quality, discoverability)
is pinned to this exact model and changing it invalidates score comparability across every past
eval run.

## 2. Deploy from the existing manifest

`scripts/agentgauge-judge-service.yaml` is the deployment source of truth — stock `ollama/ollama`
image, GCS-fuse-mounted model bucket, private (IAM-auth only), scale-to-zero, max 1 instance,
NVIDIA L4, 32Gi RAM. Update only:
- `metadata.namespace` → new project number (get via `gcloud projects describe agentgauge-prod-260813 --format="value(projectNumber)"`)
- `spec.template.spec.serviceAccountName` → `<new-project-number>-compute@developer.gserviceaccount.com`
- `volumes[0].csi.volumeAttributes.bucketName` → `agentgauge-judge-models-agentgauge-prod`

```
gcloud run services replace scripts/agentgauge-judge-service.yaml --project=agentgauge-prod-260813 --region=us-central1
gcloud run services add-iam-policy-binding agentgauge-judge --project=agentgauge-prod-260813 \
  --region=us-central1 --member=user:gaurav.gandhi1129@gmail.com --role=roles/run.invoker
```

## 3. Update the one real reference — no application code changes needed

Confirmed 2026-08-13: `agentgauge`'s `OllamaProvider` never hardcodes the judge's Cloud Run URL —
it connects via `BASE_URL = http://localhost:11434`, which callers reach by running:
```
gcloud run services proxy agentgauge-judge --port=11434 --region=us-central1 --project=agentgauge-prod-260813
```
The only edit needed is updating `--project=expense-tracker-498014` → `--project=agentgauge-prod-260813`
in `agentgauge/CLAUDE.md`'s documented command and in any operational scripts that reference the
old project flag explicitly (grep the repo for `expense-tracker-498014` to find all of them —
don't rely on memory of which scripts reference it).

## 4. Verify before cutover

Real `/api/generate` call through the proxy against `llama3.1:8b` (same verification technique
used for the original in-place check), confirming actual GPU inference works — not just that the
proxy connects.
