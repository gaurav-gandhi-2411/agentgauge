# AWS S3 fixture — provenance notes

## Real AWS S3 API operations modeled

Four tools, each a simplified wrapper around a real AWS S3 API operation. All
four carry a genuine constrained parameter, so all four are used in
`TASKS`/`TASK_CONSTRAINTS` (no inert tool was needed for this domain).

| Tool                     | Modeled on real S3 API operation                                                                          |
|--------------------------|------------------------------------------------------------------------------------------------------------|
| `create_bucket`          | `CreateBucket` — creates a new bucket. Real params include `Bucket` and `CreateBucketConfiguration.LocationConstraint` (region); simplified here to flat `bucket`/`region` string params. |
| `put_object`             | `PutObject` — uploads an object into an existing bucket. Real params include `Bucket`, `Key`, `Body`, and an optional `StorageClass`; simplified here to the same four flat params. |
| `set_bucket_versioning`  | `PutBucketVersioning` — real param is `VersioningConfiguration.Status`; simplified here to a flat `status` string param. |
| `set_object_acl`         | `PutObjectAcl` — real param is a canned `ACL` value (or an explicit grant list, not modeled here); simplified to a flat `acl` string param. |

## Constraint provenance

- **`region` format** (`create_bucket`): AWS region codes follow the real
  shape `<geo>-<direction>-<number>` (e.g. `us-east-1`, `us-west-2`,
  `eu-west-1`, `eu-central-1`, `ap-southeast-2`). The regex used here
  (`[a-z]{2}-[a-z]+-\d`) is a simplification — it does not enumerate the
  actual finite set of AWS regions, only the general shape, matching the
  style of this repo's other format-constraint fixtures (e.g.
  `github_issues_fixture.py`'s simplified `owner/repo` and username
  patterns).
- **`bucket` format** (`put_object`): real S3 bucket names must be 3-63
  characters, contain only lowercase letters, digits, hyphens, and dots, and
  must start and end with a letter or digit. The regex used here
  (`[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]`) is a direct (not simplified) encoding
  of that real length/character-set rule, though it does not enforce S3's
  additional real-world restrictions (e.g. no adjacent dots, not formatted
  like an IP address).
- **`storage_class` enum** (`put_object`): `STANDARD`, `STANDARD_IA`,
  `GLACIER`, and `INTELLIGENT_TIERING` are real, commonly used S3 storage
  class values (the real API also has `REDUCED_REDUNDANCY`, `ONEZONE_IA`,
  `DEEP_ARCHIVE`, `GLACIER_IR`, and `OUTPOSTS`, omitted here to keep the enum
  small). The distinguishing real-world semantics used to write the tasks
  (STANDARD = frequent access; STANDARD_IA = infrequent but immediately
  retrievable; GLACIER = archival with an asynchronous retrieval delay;
  INTELLIGENT_TIERING = automatic tier movement for unpredictable access
  patterns) reflect AWS's actual documented behavior for these classes.
- **`status` enum** (`set_bucket_versioning`): `Enabled` and `Suspended` are
  the real, and only, two values S3 accepts for bucket versioning status.
  Note the real (and slightly counter-intuitive) S3 behavior encoded in the
  fixed-arm description: once a bucket's versioning has been `Enabled`, it
  can only be `Suspended`, never returned to a fully version-less state —
  this is a genuine S3 quirk, not an invented one.
- **`acl` enum** (`set_object_acl`): `private`, `public-read`,
  `public-read-write`, and `authenticated-read` are four of S3's real canned
  ACL values (the real API also has `aws-exec-read`, `bucket-owner-read`,
  and `bucket-owner-full-control`, omitted here to keep the enum small).

## Honesty about sourcing

This fixture was authored from the author's existing knowledge of the AWS S3
API (operation names, parameter names, storage-class semantics, versioning
behavior, and canned ACL values) — there was no live internet access
available to verify these against AWS's current published API reference at
authoring time. All descriptions and schema shapes are the author's own
paraphrase, not copied verbatim from any AWS document. The specific field
names, enum values, and the bucket-naming character-set/length rule are
believed accurate to the real S3 product as of recent memory, but were not
re-verified against a live source before committing. If a byte-exact match to
AWS's current API reference matters for downstream use, re-verify against
`https://docs.aws.amazon.com/AmazonS3/latest/API/` before relying on this
fixture for anything beyond fixture-internal self-consistency (which is fully
verified — see the import/lint checks in the corresponding commit).

## Task design

- 20 tasks total: 5 per constrained tool x 4 constrained tools
  (`create_bucket`, `put_object`, `set_bucket_versioning`, `set_object_acl`).
- `put_object` tasks carry TWO constraints each (a shared format constraint on
  `bucket` + a task-specific enum constraint on `storage_class`), mirroring
  `stripe_payments_fixture.py`'s dual-constraint `create_charge` design.
- Anti-tautology: task text never states a region code, a bucket name, a
  storage-class value, a versioning status, or an ACL value literally.
  `create_bucket` tasks imply a region via a city/geography reference (e.g.
  "Oregon" -> `us-west-2`-shaped, "Frankfurt" -> `eu-central-1`-shaped)
  without naming the code — since `region` is a format (not enum) constraint,
  any AWS-region-shaped string satisfies it, so the geography reference is
  flavor text rather than a strict gold target. `put_object` tasks imply the
  correct `storage_class` via a real-world access-pattern scenario (e.g.
  "need it back immediately, not after a wait" -> `STANDARD_IA`, "waiting a
  few hours for retrieval is perfectly acceptable" -> `GLACIER`) without
  naming it. `set_bucket_versioning` and `set_object_acl` tasks imply the
  correct enum member via scenario phrasing (e.g. "keeps a recoverable prior
  copy" -> `Enabled`, "no login required" -> `public-read`) without naming it.
