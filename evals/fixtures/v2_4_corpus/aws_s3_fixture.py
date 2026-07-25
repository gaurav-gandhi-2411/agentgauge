from __future__ import annotations

# AWS S3 call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion pilot (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py), modeled on AWS
# S3's real API instead of an invented industrial-sensor domain.
#
# 4 tools, all constrained — 5 tasks each = 20 tasks.
# Constraint mix (2 tools per type, plus one dual-constraint tool), mirroring
# ty2_tasks.py's "2 per type" design:
#   FORMAT : create_bucket (region, AWS region shape)
#            put_object (bucket, S3 bucket-naming shape)
#   ENUM   : put_object (storage_class, one of S3's real storage classes)
#            set_bucket_versioning (status, Enabled/Suspended)
#            set_object_acl (acl, one of S3's real canned ACLs)
#
# put_object tasks carry TWO constraints each (format on `bucket` + enum on
# `storage_class`), mirroring stripe_payments_fixture.py's create_charge design.
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "Enabled", "GLACIER", "private") or the
# literal format shape (e.g. an actual bucket name or region code string) that
# the agent is meant to construct. The agent must derive the correct value from
# the tool's SCHEMA/description (fixed variant) or fail correctly (bad variant),
# not from the task text.
#
# See aws_s3_NOTES.md for provenance of the real AWS S3 API fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_bucket (format constraint on `region`, AWS region shape) — 5 tasks
    Task(
        "create_bucket",
        "Create a new bucket to host static website assets for a company whose primary "
        "customers and infrastructure are based on the U.S. East Coast.",
    ),
    Task(
        "create_bucket",
        "Set up a bucket to store backups for a team whose servers all run out of AWS's "
        "data centers in Oregon.",
    ),
    Task(
        "create_bucket",
        "Create a bucket for a European customer's data-residency requirements, physically "
        "located in Ireland.",
    ),
    Task(
        "create_bucket",
        "Set up storage for an Australian subsidiary that wants its bucket to live in the "
        "Sydney AWS region.",
    ),
    Task(
        "create_bucket",
        "Create a bucket for a German logistics company that needs its data to physically "
        "reside in Frankfurt.",
    ),
    # put_object (format constraint on `bucket`, enum constraint on `storage_class`) — 5 tasks
    Task(
        "put_object",
        "Upload this week's live product-catalog images that the storefront app pulls on "
        "every page load.",
    ),
    Task(
        "put_object",
        "Save last quarter's finalized financial reports — the team almost never opens them, "
        "but on the rare occasion they do, they need it back immediately, not after a wait.",
    ),
    Task(
        "put_object",
        "Put away this year's raw sensor telemetry dump for long-term retention — it's "
        "extremely unlikely anyone will ever need to pull it back, and if they do, waiting a "
        "few hours for retrieval is perfectly acceptable.",
    ),
    Task(
        "put_object",
        "Store these new user-uploaded documents where we genuinely don't know yet how often "
        "they'll be accessed over time, and want the storage tier to adjust automatically as "
        "that pattern becomes clear.",
    ),
    Task(
        "put_object",
        "Upload today's freshly rendered video thumbnails that the app's homepage needs to "
        "load instantly for every visitor.",
    ),
    # set_bucket_versioning (enum constraint on `status`) — 5 tasks
    Task(
        "set_bucket_versioning",
        "Turn on version history for this bucket so we can recover from accidental "
        "overwrites or deletions going forward.",
    ),
    Task(
        "set_bucket_versioning",
        "Pause version tracking on this bucket — existing versions should stay, we just "
        "don't want new ones being created for every upload from now on.",
    ),
    Task(
        "set_bucket_versioning",
        "Make sure every future upload to this bucket keeps a recoverable prior copy, "
        "starting today.",
    ),
    Task(
        "set_bucket_versioning",
        "Stop creating new object versions on this compliance bucket going forward, without "
        "removing any of the versions it's already accumulated.",
    ),
    Task(
        "set_bucket_versioning",
        "Switch this bucket over to tracking every revision of an object so nothing gets "
        "silently lost on overwrite.",
    ),
    # set_object_acl (enum constraint on `acl`) — 5 tasks
    Task(
        "set_object_acl",
        "Lock this object down so only our own account can read it — nobody else, "
        "authenticated or not, should be able to open it.",
    ),
    Task(
        "set_object_acl",
        "Make this uploaded image publicly viewable by anyone on the internet without "
        "needing to log in, since it's going to be embedded on our public marketing site.",
    ),
    Task(
        "set_object_acl",
        "Let any AWS user with a login read this shared research dataset, but keep it away "
        "from completely anonymous internet visitors.",
    ),
    Task(
        "set_object_acl",
        "Set this object up as a public drop-box style file where any visitor can both read "
        "what's there and upload their own replacement, with no login required.",
    ),
    Task(
        "set_object_acl",
        "Restrict this internal HR document so nobody outside our own AWS account can view "
        "it at all.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
_BUCKET_FORMAT = Constraint("bucket", "format", pattern=r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")

TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_bucket — format: AWS region shape
    (
        "create_bucket",
        "Create a new bucket to host static website assets for a company whose primary "
        "customers and infrastructure are based on the U.S. East Coast.",
    ): [Constraint("region", "format", pattern=r"[a-z]{2}-[a-z]+-\d")],
    (
        "create_bucket",
        "Set up a bucket to store backups for a team whose servers all run out of AWS's "
        "data centers in Oregon.",
    ): [Constraint("region", "format", pattern=r"[a-z]{2}-[a-z]+-\d")],
    (
        "create_bucket",
        "Create a bucket for a European customer's data-residency requirements, physically "
        "located in Ireland.",
    ): [Constraint("region", "format", pattern=r"[a-z]{2}-[a-z]+-\d")],
    (
        "create_bucket",
        "Set up storage for an Australian subsidiary that wants its bucket to live in the "
        "Sydney AWS region.",
    ): [Constraint("region", "format", pattern=r"[a-z]{2}-[a-z]+-\d")],
    (
        "create_bucket",
        "Create a bucket for a German logistics company that needs its data to physically "
        "reside in Frankfurt.",
    ): [Constraint("region", "format", pattern=r"[a-z]{2}-[a-z]+-\d")],
    # put_object — format: S3 bucket-naming shape + enum: storage_class
    (
        "put_object",
        "Upload this week's live product-catalog images that the storefront app pulls on "
        "every page load.",
    ): [_BUCKET_FORMAT, Constraint("storage_class", "enum", gold_value="STANDARD")],
    (
        "put_object",
        "Save last quarter's finalized financial reports — the team almost never opens them, "
        "but on the rare occasion they do, they need it back immediately, not after a wait.",
    ): [_BUCKET_FORMAT, Constraint("storage_class", "enum", gold_value="STANDARD_IA")],
    (
        "put_object",
        "Put away this year's raw sensor telemetry dump for long-term retention — it's "
        "extremely unlikely anyone will ever need to pull it back, and if they do, waiting a "
        "few hours for retrieval is perfectly acceptable.",
    ): [_BUCKET_FORMAT, Constraint("storage_class", "enum", gold_value="GLACIER")],
    (
        "put_object",
        "Store these new user-uploaded documents where we genuinely don't know yet how often "
        "they'll be accessed over time, and want the storage tier to adjust automatically as "
        "that pattern becomes clear.",
    ): [_BUCKET_FORMAT, Constraint("storage_class", "enum", gold_value="INTELLIGENT_TIERING")],
    (
        "put_object",
        "Upload today's freshly rendered video thumbnails that the app's homepage needs to "
        "load instantly for every visitor.",
    ): [_BUCKET_FORMAT, Constraint("storage_class", "enum", gold_value="STANDARD")],
    # set_bucket_versioning — enum: status (Enabled/Suspended)
    (
        "set_bucket_versioning",
        "Turn on version history for this bucket so we can recover from accidental "
        "overwrites or deletions going forward.",
    ): [Constraint("status", "enum", gold_value="Enabled")],
    (
        "set_bucket_versioning",
        "Pause version tracking on this bucket — existing versions should stay, we just "
        "don't want new ones being created for every upload from now on.",
    ): [Constraint("status", "enum", gold_value="Suspended")],
    (
        "set_bucket_versioning",
        "Make sure every future upload to this bucket keeps a recoverable prior copy, "
        "starting today.",
    ): [Constraint("status", "enum", gold_value="Enabled")],
    (
        "set_bucket_versioning",
        "Stop creating new object versions on this compliance bucket going forward, without "
        "removing any of the versions it's already accumulated.",
    ): [Constraint("status", "enum", gold_value="Suspended")],
    (
        "set_bucket_versioning",
        "Switch this bucket over to tracking every revision of an object so nothing gets "
        "silently lost on overwrite.",
    ): [Constraint("status", "enum", gold_value="Enabled")],
    # set_object_acl — enum: acl (S3's real canned ACLs)
    (
        "set_object_acl",
        "Lock this object down so only our own account can read it — nobody else, "
        "authenticated or not, should be able to open it.",
    ): [Constraint("acl", "enum", gold_value="private")],
    (
        "set_object_acl",
        "Make this uploaded image publicly viewable by anyone on the internet without "
        "needing to log in, since it's going to be embedded on our public marketing site.",
    ): [Constraint("acl", "enum", gold_value="public-read")],
    (
        "set_object_acl",
        "Let any AWS user with a login read this shared research dataset, but keep it away "
        "from completely anonymous internet visitors.",
    ): [Constraint("acl", "enum", gold_value="authenticated-read")],
    (
        "set_object_acl",
        "Set this object up as a public drop-box style file where any visitor can both read "
        "what's there and upload their own replacement, with no login required.",
    ): [Constraint("acl", "enum", gold_value="public-read-write")],
    (
        "set_object_acl",
        "Restrict this internal HR document so nobody outside our own AWS account can view "
        "it at all.",
    ): [Constraint("acl", "enum", gold_value="private")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_bucket", "put_object", "set_bucket_versioning", "set_object_acl"]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_bucket", "put_object"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(
    ["put_object", "set_bucket_versioning", "set_object_acl"]
)

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "STANDARD",
    "STANDARD_IA",
    "GLACIER",
    "INTELLIGENT_TIERING",
    "Enabled",
    "Suspended",
    "private",
    "public-read",
    "public-read-write",
    "authenticated-read",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"[a-z]{2}-[a-z]+-\d",
    r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]",
    "us-east-1",
    "my-example-bucket",
]
