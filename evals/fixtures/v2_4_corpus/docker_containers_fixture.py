from __future__ import annotations

# Docker Engine API call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion pilot (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py) and to the
# github_issues/stripe_payments/gcal fixtures in this same directory, modeled
# on Docker's real Engine API instead of an invented industrial-sensor domain.
#
# 4 tools, all constrained — 5 tasks each = 20 tasks.
# Constraint mix (see docker_containers_NOTES.md for full provenance):
#   FORMAT : create_container (image, "name:tag" shape)
#            tag_image (tag, Docker tag-name shape)
#   ENUM   : create_container (restart_policy, Docker's real RestartPolicy.Name
#            values)
#            create_network (driver, a subset of Docker's real built-in
#            network drivers)
#   RANGE  : stop_container (timeout_seconds, graceful-shutdown grace period
#            in seconds)
#
# create_container carries TWO constraints per task (format on `image` + enum
# on `restart_policy`), mirroring stripe_payments_fixture.py's create_charge
# (range + enum on one tool).
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must
# NOT contain the literal enum value (e.g. "on-failure", "overlay"), the
# literal format shape (e.g. an actual "name:tag" string or tag token), or a
# literal timeout number. The agent must derive the correct value from the
# tool's SCHEMA/description (fixed variant) or fail correctly (bad variant),
# not from a literal value quoted in the task text.
#
# See docker_containers_NOTES.md for provenance of the real Docker Engine API
# fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_container (format on `image`, "name:tag" shape; enum on
    # `restart_policy`, Docker's real RestartPolicy.Name values) — 5 tasks
    Task(
        "create_container",
        "Launch a container for a lightweight Redis cache that should keep automatically "
        "restarting no matter what happens to it, even after repeated failures.",
    ),
    Task(
        "create_container",
        "Spin up a one-off container to run a quick data-migration script — once it exits, "
        "Docker shouldn't try to bring it back up under any circumstances.",
    ),
    Task(
        "create_container",
        "Start a container running a background worker that should only be relaunched "
        "automatically if it crashes with an error, but should stay stopped if it finishes "
        "its job normally.",
    ),
    Task(
        "create_container",
        "Bring up a container for a production web server that should keep coming back "
        "automatically after crashes or host reboots, but should stay down if an operator "
        "deliberately stops it.",
    ),
    Task(
        "create_container",
        "Start a container for an internal monitoring agent that must always be running, "
        "immediately restarting itself after any exit, without exception.",
    ),
    # stop_container (range on `timeout_seconds`, graceful-shutdown grace
    # period) — 5 tasks
    Task(
        "stop_container",
        "Immediately shut down the container running the crashed test script — don't wait "
        "around for it to clean up, just force it to stop right away.",
    ),
    Task(
        "stop_container",
        "Stop the container in a hurry, but still give it just the briefest moment to close "
        "its open network connections cleanly.",
    ),
    Task(
        "stop_container",
        "Stop the container using a normal, unhurried shutdown — nothing urgent, just let it "
        "wind down the way Docker typically would.",
    ),
    Task(
        "stop_container",
        "Stop this container carefully — it's mid-way through processing a long batch job, "
        "so give it plenty of extra time to finish up before being force-killed.",
    ),
    Task(
        "stop_container",
        "Stop the database container very cautiously — let it fully flush and close all of "
        "its open transactions, even if that takes several minutes.",
    ),
    # create_network (enum on `driver`, subset of Docker's real built-in
    # network drivers) — 5 tasks
    Task(
        "create_network",
        "Set up a private network for a group of containers running together on this one "
        "machine, isolated from the outside world by default.",
    ),
    Task(
        "create_network",
        "Create a network configuration where the container shares the host machine's own "
        "network stack directly, with no isolation layer in between.",
    ),
    Task(
        "create_network",
        "Set up a network that lets services running on different physical Docker hosts in a "
        "cluster talk to each other.",
    ),
    Task(
        "create_network",
        "Create a network setup that completely disables any networking for the container — "
        "it shouldn't be able to reach anything at all.",
    ),
    Task(
        "create_network",
        "Set up another simple, isolated network for a small set of related containers on a "
        "single server, similar to Docker's usual default networking mode.",
    ),
    # tag_image (format on `tag`, Docker tag-name shape) — 5 tasks
    Task(
        "tag_image",
        "Mark the image that was just built for the checkout-service as the version that's "
        "about to be promoted to production.",
    ),
    Task(
        "tag_image",
        "Give the nightly build of the analytics-pipeline image a tag so the QA team knows "
        "it's ready for testing.",
    ),
    Task(
        "tag_image",
        "Tag the current build of the payment-gateway image so it's clearly identified as "
        "this quarter's stable release.",
    ),
    Task(
        "tag_image",
        "Tag the freshly built recommendation-engine image so it's marked as the newest "
        "development snapshot.",
    ),
    Task(
        "tag_image",
        "Give the latest build of the user-auth-service image a tag indicating it's ready "
        "for staging validation.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
#
# Format constraints on `image` / `tag`: no gold value — any value matching
# the pattern counts, mirroring create_issue/add_assignee in
# github_issues_fixture.py.
# Enum constraints: gold_value is the specific expected enum member.
# Range constraint on `timeout_seconds`: a distinct window per task, derived
# from the task's implied urgency (never a literal number in the task text),
# mirroring create_charge's shared range in stripe_payments_fixture.py — here
# the windows vary per task instead of being shared, since urgency (not a
# fixed business amount) is what each task encodes.
_IMAGE_FORMAT = Constraint(
    "image", "format", pattern=r"[A-Za-z0-9][A-Za-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*"
)
_TAG_FORMAT = Constraint("tag", "format", pattern=r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")

TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_container — format: image ("name:tag") + enum: restart_policy
    (
        "create_container",
        "Launch a container for a lightweight Redis cache that should keep automatically "
        "restarting no matter what happens to it, even after repeated failures.",
    ): [_IMAGE_FORMAT, Constraint("restart_policy", "enum", gold_value="always")],
    (
        "create_container",
        "Spin up a one-off container to run a quick data-migration script — once it exits, "
        "Docker shouldn't try to bring it back up under any circumstances.",
    ): [_IMAGE_FORMAT, Constraint("restart_policy", "enum", gold_value="no")],
    (
        "create_container",
        "Start a container running a background worker that should only be relaunched "
        "automatically if it crashes with an error, but should stay stopped if it finishes "
        "its job normally.",
    ): [_IMAGE_FORMAT, Constraint("restart_policy", "enum", gold_value="on-failure")],
    (
        "create_container",
        "Bring up a container for a production web server that should keep coming back "
        "automatically after crashes or host reboots, but should stay down if an operator "
        "deliberately stops it.",
    ): [_IMAGE_FORMAT, Constraint("restart_policy", "enum", gold_value="unless-stopped")],
    (
        "create_container",
        "Start a container for an internal monitoring agent that must always be running, "
        "immediately restarting itself after any exit, without exception.",
    ): [_IMAGE_FORMAT, Constraint("restart_policy", "enum", gold_value="always")],
    # stop_container — range: timeout_seconds (window varies with implied urgency)
    (
        "stop_container",
        "Immediately shut down the container running the crashed test script — don't wait "
        "around for it to clean up, just force it to stop right away.",
    ): [Constraint("timeout_seconds", "range", min_val=0, max_val=1)],
    (
        "stop_container",
        "Stop the container in a hurry, but still give it just the briefest moment to close "
        "its open network connections cleanly.",
    ): [Constraint("timeout_seconds", "range", min_val=2, max_val=5)],
    (
        "stop_container",
        "Stop the container using a normal, unhurried shutdown — nothing urgent, just let it "
        "wind down the way Docker typically would.",
    ): [Constraint("timeout_seconds", "range", min_val=8, max_val=12)],
    (
        "stop_container",
        "Stop this container carefully — it's mid-way through processing a long batch job, "
        "so give it plenty of extra time to finish up before being force-killed.",
    ): [Constraint("timeout_seconds", "range", min_val=60, max_val=180)],
    (
        "stop_container",
        "Stop the database container very cautiously — let it fully flush and close all of "
        "its open transactions, even if that takes several minutes.",
    ): [Constraint("timeout_seconds", "range", min_val=240, max_val=600)],
    # create_network — enum: driver
    (
        "create_network",
        "Set up a private network for a group of containers running together on this one "
        "machine, isolated from the outside world by default.",
    ): [Constraint("driver", "enum", gold_value="bridge")],
    (
        "create_network",
        "Create a network configuration where the container shares the host machine's own "
        "network stack directly, with no isolation layer in between.",
    ): [Constraint("driver", "enum", gold_value="host")],
    (
        "create_network",
        "Set up a network that lets services running on different physical Docker hosts in a "
        "cluster talk to each other.",
    ): [Constraint("driver", "enum", gold_value="overlay")],
    (
        "create_network",
        "Create a network setup that completely disables any networking for the container — "
        "it shouldn't be able to reach anything at all.",
    ): [Constraint("driver", "enum", gold_value="none")],
    (
        "create_network",
        "Set up another simple, isolated network for a small set of related containers on a "
        "single server, similar to Docker's usual default networking mode.",
    ): [Constraint("driver", "enum", gold_value="bridge")],
    # tag_image — format: tag (Docker tag-name shape)
    (
        "tag_image",
        "Mark the image that was just built for the checkout-service as the version that's "
        "about to be promoted to production.",
    ): [_TAG_FORMAT],
    (
        "tag_image",
        "Give the nightly build of the analytics-pipeline image a tag so the QA team knows "
        "it's ready for testing.",
    ): [_TAG_FORMAT],
    (
        "tag_image",
        "Tag the current build of the payment-gateway image so it's clearly identified as "
        "this quarter's stable release.",
    ): [_TAG_FORMAT],
    (
        "tag_image",
        "Tag the freshly built recommendation-engine image so it's marked as the newest "
        "development snapshot.",
    ): [_TAG_FORMAT],
    (
        "tag_image",
        "Give the latest build of the user-auth-service image a tag indicating it's ready "
        "for staging validation.",
    ): [_TAG_FORMAT],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_container", "stop_container", "create_network", "tag_image"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_container", "tag_image"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["create_container", "create_network"])
RANGE_TOOL_NAMES: frozenset[str] = frozenset(["stop_container"])

# Enum gold values referenced in tasks (for inferability tests — these should
# not appear verbatim in task text).
ENUM_GOLD_VALUES: list[str] = [
    "no",
    "always",
    "on-failure",
    "unless-stopped",
    "bridge",
    "host",
    "overlay",
    "none",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"[A-Za-z0-9][A-Za-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*",
    r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}",
    "redis:7-alpine",
    "v1.2.3",
]
