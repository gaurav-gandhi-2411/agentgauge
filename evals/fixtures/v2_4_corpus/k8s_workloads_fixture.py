from __future__ import annotations

# Kubernetes-workloads pre-registered tasks and constraints for the call-correctness
# oracle A/B (v2.4 corpus expansion, Task 4 — real-API domain pilot).
#
# 4 tools modeled on real Kubernetes API operations (see k8s_workloads_NOTES.md):
# create_pod, scale_deployment, set_pod_image_pull_policy, create_namespace. All 4
# are constrained — no inert tool was needed here.
#
# 20 tasks: 5 per tool x 4 tools.
# Constraint mix:
#   FORMAT + ENUM : create_pod (namespace, DNS-1123 label shape; restart_policy,
#                   one of Always/OnFailure/Never)
#   RANGE         : scale_deployment (replicas)
#   ENUM          : set_pod_image_pull_policy (pull_policy, one of
#                   Always/IfNotPresent/Never)
#   FORMAT        : create_namespace (name, DNS-1123 label shape)
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "Never", "IfNotPresent"), the literal format
# pattern, an already-valid DNS-1123 label string handed to the agent verbatim, or a
# literal replica count. The agent must derive the correct value from the tool's
# SCHEMA/description (fixed variant) or fail to do so (bad variant), not from the
# task text.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

# Shared DNS-1123 label pattern (Kubernetes' real naming rule for Namespace names and
# the namespace field on namespaced resources): lowercase alphanumeric characters or
# '-', starting and ending with an alphanumeric character. Format constraints carry no
# gold_value — any value matching the pattern counts, since the task text never
# specifies an exact namespace string.
_DNS_1123_LABEL_PATTERN = r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?"

TASKS: list[Task] = [
    # create_pod (format: namespace, DNS-1123 label; enum: restart_policy) — 5 tasks
    Task(
        "create_pod",
        "Launch a one-off database backup pod in the data-platform environment that "
        "should run once to completion and never be restarted, even if it ends up failing.",
    ),
    Task(
        "create_pod",
        "Deploy a log-processing pod in the observability environment that should only "
        "be restarted automatically if it crashes, but left alone once it finishes its "
        "work successfully.",
    ),
    Task(
        "create_pod",
        "Start a customer-facing web server pod in the production environment that must "
        "always come back up automatically no matter why or how it stops.",
    ),
    Task(
        "create_pod",
        "Spin up a nightly batch-reconciliation pod in the finance environment that "
        "should retry on a crash but not restart after completing its run normally.",
    ),
    Task(
        "create_pod",
        "Create a pod for an internal metrics-collection agent in the platform "
        "environment that needs to keep running indefinitely, restarting under any "
        "circumstance.",
    ),
    # scale_deployment (range: replicas) — 5 tasks
    Task(
        "scale_deployment",
        "Take the checkout-service deployment offline entirely without deleting it, so "
        "no pods are running until routine maintenance finishes.",
    ),
    Task(
        "scale_deployment",
        "Scale the reporting-dashboard deployment down to a single running copy for a "
        "quiet overnight window.",
    ),
    Task(
        "scale_deployment",
        "Scale up the recommendation-engine deployment to absorb a big holiday traffic "
        "surge, running many parallel copies at once.",
    ),
    Task(
        "scale_deployment",
        "Reduce the internal-tools deployment to just a couple of instances to save "
        "resources over the weekend.",
    ),
    Task(
        "scale_deployment",
        "Bring the payment-gateway deployment back to a modest, standard number of "
        "running copies after finishing an emergency scale-down.",
    ),
    # set_pod_image_pull_policy (enum: pull_policy) — 5 tasks
    Task(
        "set_pod_image_pull_policy",
        "Configure the container in the CI build-runner pod so it always fetches a "
        "fresh copy of the image from the registry before starting, even if a matching "
        "image already exists locally.",
    ),
    Task(
        "set_pod_image_pull_policy",
        "Set the pull behavior for the container in our internal-analytics pod so it "
        "only downloads the image if it isn't already cached on the node, avoiding "
        "unnecessary registry calls for a version-pinned image.",
    ),
    Task(
        "set_pod_image_pull_policy",
        "For the container in the local-dev pod that uses a manually pre-loaded image, "
        "make sure it never tries to reach out to any container registry to fetch it.",
    ),
    Task(
        "set_pod_image_pull_policy",
        "Update the container in the nightly-build pod so every restart re-pulls the "
        "very latest image instead of reusing whatever is already cached on the node.",
    ),
    Task(
        "set_pod_image_pull_policy",
        "Configure the container in the pod running on the air-gapped edge cluster to "
        "rely solely on whatever image is already present on the node, since the "
        "cluster has no network access to any registry.",
    ),
    # create_namespace (format: name, DNS-1123 label) — 5 tasks
    Task(
        "create_namespace",
        "Set up a brand-new namespace to isolate all resources for the machine-learning "
        "experimentation team.",
    ),
    Task(
        "create_namespace",
        "Create an isolated namespace so the QA team can run integration tests without "
        "touching any other environment.",
    ),
    Task(
        "create_namespace",
        "Provision a dedicated namespace for staging deployments of the checkout service.",
    ),
    Task(
        "create_namespace",
        "Create a new namespace to hold every resource for the upcoming customer-facing "
        "beta launch.",
    ),
    Task(
        "create_namespace",
        "Set up a namespace scoped specifically to the platform team's internal tooling "
        "and dashboards.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
# Range tasks: min_val <= replicas <= max_val, tuned to the qualitative scale implied
# by each task (e.g. "offline entirely" -> 0, "a single running copy" -> 1).
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_pod — format: namespace (DNS-1123 label) + enum: restart_policy
    (
        "create_pod",
        "Launch a one-off database backup pod in the data-platform environment that "
        "should run once to completion and never be restarted, even if it ends up failing.",
    ): [
        Constraint("namespace", "format", pattern=_DNS_1123_LABEL_PATTERN),
        Constraint("restart_policy", "enum", gold_value="Never"),
    ],
    (
        "create_pod",
        "Deploy a log-processing pod in the observability environment that should only "
        "be restarted automatically if it crashes, but left alone once it finishes its "
        "work successfully.",
    ): [
        Constraint("namespace", "format", pattern=_DNS_1123_LABEL_PATTERN),
        Constraint("restart_policy", "enum", gold_value="OnFailure"),
    ],
    (
        "create_pod",
        "Start a customer-facing web server pod in the production environment that must "
        "always come back up automatically no matter why or how it stops.",
    ): [
        Constraint("namespace", "format", pattern=_DNS_1123_LABEL_PATTERN),
        Constraint("restart_policy", "enum", gold_value="Always"),
    ],
    (
        "create_pod",
        "Spin up a nightly batch-reconciliation pod in the finance environment that "
        "should retry on a crash but not restart after completing its run normally.",
    ): [
        Constraint("namespace", "format", pattern=_DNS_1123_LABEL_PATTERN),
        Constraint("restart_policy", "enum", gold_value="OnFailure"),
    ],
    (
        "create_pod",
        "Create a pod for an internal metrics-collection agent in the platform "
        "environment that needs to keep running indefinitely, restarting under any "
        "circumstance.",
    ): [
        Constraint("namespace", "format", pattern=_DNS_1123_LABEL_PATTERN),
        Constraint("restart_policy", "enum", gold_value="Always"),
    ],
    # scale_deployment — range: replicas
    (
        "scale_deployment",
        "Take the checkout-service deployment offline entirely without deleting it, so "
        "no pods are running until routine maintenance finishes.",
    ): [Constraint("replicas", "range", min_val=0, max_val=0)],
    (
        "scale_deployment",
        "Scale the reporting-dashboard deployment down to a single running copy for a "
        "quiet overnight window.",
    ): [Constraint("replicas", "range", min_val=1, max_val=1)],
    (
        "scale_deployment",
        "Scale up the recommendation-engine deployment to absorb a big holiday traffic "
        "surge, running many parallel copies at once.",
    ): [Constraint("replicas", "range", min_val=10, max_val=50)],
    (
        "scale_deployment",
        "Reduce the internal-tools deployment to just a couple of instances to save "
        "resources over the weekend.",
    ): [Constraint("replicas", "range", min_val=2, max_val=3)],
    (
        "scale_deployment",
        "Bring the payment-gateway deployment back to a modest, standard number of "
        "running copies after finishing an emergency scale-down.",
    ): [Constraint("replicas", "range", min_val=3, max_val=6)],
    # set_pod_image_pull_policy — enum: pull_policy
    (
        "set_pod_image_pull_policy",
        "Configure the container in the CI build-runner pod so it always fetches a "
        "fresh copy of the image from the registry before starting, even if a matching "
        "image already exists locally.",
    ): [Constraint("pull_policy", "enum", gold_value="Always")],
    (
        "set_pod_image_pull_policy",
        "Set the pull behavior for the container in our internal-analytics pod so it "
        "only downloads the image if it isn't already cached on the node, avoiding "
        "unnecessary registry calls for a version-pinned image.",
    ): [Constraint("pull_policy", "enum", gold_value="IfNotPresent")],
    (
        "set_pod_image_pull_policy",
        "For the container in the local-dev pod that uses a manually pre-loaded image, "
        "make sure it never tries to reach out to any container registry to fetch it.",
    ): [Constraint("pull_policy", "enum", gold_value="Never")],
    (
        "set_pod_image_pull_policy",
        "Update the container in the nightly-build pod so every restart re-pulls the "
        "very latest image instead of reusing whatever is already cached on the node.",
    ): [Constraint("pull_policy", "enum", gold_value="Always")],
    (
        "set_pod_image_pull_policy",
        "Configure the container in the pod running on the air-gapped edge cluster to "
        "rely solely on whatever image is already present on the node, since the "
        "cluster has no network access to any registry.",
    ): [Constraint("pull_policy", "enum", gold_value="Never")],
    # create_namespace — format: name (DNS-1123 label)
    (
        "create_namespace",
        "Set up a brand-new namespace to isolate all resources for the machine-learning "
        "experimentation team.",
    ): [Constraint("name", "format", pattern=_DNS_1123_LABEL_PATTERN)],
    (
        "create_namespace",
        "Create an isolated namespace so the QA team can run integration tests without "
        "touching any other environment.",
    ): [Constraint("name", "format", pattern=_DNS_1123_LABEL_PATTERN)],
    (
        "create_namespace",
        "Provision a dedicated namespace for staging deployments of the checkout service.",
    ): [Constraint("name", "format", pattern=_DNS_1123_LABEL_PATTERN)],
    (
        "create_namespace",
        "Create a new namespace to hold every resource for the upcoming customer-facing "
        "beta launch.",
    ): [Constraint("name", "format", pattern=_DNS_1123_LABEL_PATTERN)],
    (
        "create_namespace",
        "Set up a namespace scoped specifically to the platform team's internal tooling "
        "and dashboards.",
    ): [Constraint("name", "format", pattern=_DNS_1123_LABEL_PATTERN)],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_pod", "scale_deployment", "set_pod_image_pull_policy", "create_namespace"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_pod", "create_namespace"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["create_pod", "set_pod_image_pull_policy"])
RANGE_TOOL_NAMES: frozenset[str] = frozenset(["scale_deployment"])

# Enum gold values referenced in tasks (for inferability tests).
ENUM_GOLD_VALUES: list[str] = [
    "Never",
    "OnFailure",
    "Always",
    "IfNotPresent",
]
# Format patterns (for inferability tests — these should not appear verbatim in task
# text, since format constraints carry no gold_value in this fixture).
FORMAT_PATTERNS_SAMPLE: list[str] = [
    _DNS_1123_LABEL_PATTERN,
    "ml-experiments",
    "qa-integration",
]
