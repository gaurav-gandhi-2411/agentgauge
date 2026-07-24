# AgentGauge v2.2 — Task C: GCP teardown (post Task A + Task B completion)

Run only after Task A (`reports/v2_2_task_a_reallocation.md`) and Task B
(`reports/v2_2_task_b_causal_chain_multimodel.md`) both completed, per the
user's explicit reorder instruction. Project: `expense-tracker-498014`,
region `us-central1` throughout.

## Spend to date (final, before teardown)

Measured via Cloud Monitoring `run.googleapis.com/container/billable_instance_time`
for `agentgauge-agent` (not estimated): **71,916 seconds (19.98 hours)
billed, ≈$28.39 compute** (GPU $0.0001867/s + 8 vCPU × $0.000018/s + 32 GiB ×
$0.000002/s). Plus one Cloud Build (14 min, within the 120 free build-min/day
tier, $0.00) and ~15GB of now-deleted GCR image storage. **Well under the
$40 cap** stated in the reorder message.

## Actions taken

1. `gcloud run services delete agentgauge-agent --project=expense-tracker-498014
   --region=us-central1` — deleted.
2. `gcloud container images delete gcr.io/expense-tracker-498014/agentgauge-agent-baked@sha256:0c75468a...
   --force-delete-tags` — deleted (the `latest` tag and its one digest).

No buckets were deleted: none existed that were specific to
`agentgauge-agent`. The two GCS buckets present in the project
(`expense-tracker-498014_cloudbuild`, `run-sources-expense-tracker-498014-us-central1`)
are shared default staging buckets used by every Cloud Run/Cloud Build
deploy in the project (including the unrelated `expense-tracker` service) —
not created for or specific to this session's work, and deleting them would
risk breaking unrelated deployments. `agentgauge-judge-models-expense-tracker`
belongs to `agentgauge-judge` and was correctly left alone.

## Verification (commands + output, not assumed)

```
$ gcloud run services list --project=expense-tracker-498014 --region=us-central1
NAME              URL
agentgauge-judge  https://agentgauge-judge-6txxpjhu2a-uc.a.run.app
expense-tracker   https://expense-tracker-6txxpjhu2a-uc.a.run.app
```
`agentgauge-agent` is gone. `agentgauge-judge` remains, confirmed healthy
(`status.conditions[0].status` = `True`) — untouched, per instruction.
`expense-tracker` (unrelated to this project) also untouched.

```
$ gcloud container images list-tags gcr.io/expense-tracker-498014/agentgauge-agent-baked
Listed 0 items.
```
Zero tags/digests remain under the baked-image path.

```
$ gcloud run jobs list --project=expense-tracker-498014 --region=us-central1
(empty)
```
No Cloud Run jobs exist (nothing else to delete in that resource class).

```
$ gcloud artifacts docker images list us-central1-docker.pkg.dev/expense-tracker-498014/cloud-run-source-deploy
(only `expense-tracker` images, none related to agentgauge-agent)
```

**Result: zero billable resources remain for `agentgauge-agent`.** No
scale-to-zero instance is lingering, no image storage remains, no jobs
exist. `agentgauge-judge` (pre-existing, out of scope) continues running
normally, confirmed via a live health check, not assumed.
