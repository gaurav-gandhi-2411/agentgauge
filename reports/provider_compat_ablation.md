# Provider-compat ablation probe (Vertex, post-hoc)

> **POST-HOC: design 3d5d6e6; the rejections were seen before the design.**

Aggregate-only: unit labels, construct names, counts and outcomes. No tool name, schema text, server identifier, limit value or per-catalog hash. Design (frozen): `docs/research/provider-compat-ablation-design.md` at commit 3d5d6e6.

## Verdict

**No limit isolated -> no rule change; documentation only.**

- Criterion 1 holds for `maxItems`: aggregate in U1-U4, boundary reproduced.
- Criterion 2 fails: no single static quantity separates all 63 accepted from all 67 rejected distinct requests, globally or within any unit.
- 13 candidate quantities were tested. The aggregate report does not contain them and they cannot be recomputed from it; the results are quoted from the independent recompute. Named: the maxItems count, the maxItems value sum, the flipping-construct counts, the numeric-constraint totals, the tool count and the request JSON size.
- Per the design, a limit is isolated only if all three criteria hold, so no lint check changes; the diagnosis table in `provider_compat_posthoc.md` is updated instead.
- This is not a finding that no limit exists. It is a finding that none of the candidates tested separates accepted from rejected requests.

## Totals

151 calls: 73 rejected, 67 accepted, 11 other (1 unresolved). Spend INR 39.77 of the INR 200 cap. Run complete: True.

## Units

| Unit | From | Tools | A0 (raw unit) | Flipping constructs (A1) |
|---|---|---|---|---|
| U1 | R3 | 2 | rejected | `enum`, `maxItems` |
| U2 | R4 | 4 | rejected | `maxItems`, `maximum` |
| U3 | R4 | 32 | rejected | `enum`, `maxItems` |
| U4 | R5 | 3 | rejected | `format`, `maxItems` |
| U5 | R5 | 10 | rejected | `maximum` |

## Phase A: reproduce and remove one construct at a time

Constructs present, each removed everywhere in turn; `flip` = unit became accepted.

| Unit | Constructs tested | Flip | No flip |
|---|---|---|---|
| U1 | 4 | `enum`, `maxItems` | `anyOf`, `minItems` |
| U2 | 9 | `maxItems`, `maximum` | `additionalProperties`, `enum`, `maxLength`, `minItems`, `minLength`, `minimum`, `pattern` |
| U3 | 14 | `enum`, `maxItems` | `additionalProperties`, `default`, `empty_schema`, `examples`, `maxLength`, `maximum`, `minItems`, `minLength`, `minimum`, `pattern`, `title`, `type_list` |
| U4 | 10 | `format`, `maxItems` | `$schema`, `enum`, `maxLength`, `maximum`, `minItems`, `minLength`, `minimum`, `pattern` |
| U5 | 11 | `maximum` | `$schema`, `additionalProperties`, `enum`, `format`, `maxItems`, `maxLength`, `minLength`, `minimum`, `pattern`, `propertyNames` |

## Phase B: additive reconstruction

N = instances of the construct; indices count in the fixed instance order; n = smallest prefix that was rejected, forward and reverse; singles = base plus only the threshold instance.

| Unit | Construct | N | Class | idx fwd/rev | n fwd/rev | Singles | Note |
|---|---|---|---|---|---|---|---|
| U1 | `enum` | 8 | aggregate | 1/4 | 2/4 | 1: accepted, 4: accepted |  |
| U1 | `maxItems` | 2 | aggregate | 1/0 | 2/2 | 0: accepted, 1: accepted |  |
| U2 | `maxItems` | 3 | aggregate | 2/0 | 3/3 | 0: accepted, 2: accepted |  |
| U2 | `maximum` | 7 | inconsistent | 2/6 | 3/1 | 2: accepted, 6: rejected |  |
| U3 | `enum` | 7 | aggregate | 5/1 | 6/6 | 1: accepted, 5: accepted |  |
| U3 | `maxItems` | 5 | aggregate | 1/0 | 2/5 | 0: accepted, 1: accepted |  |
| U4 | `format` | 3 | instance-critical | 2/2 | 3/1 | 2: rejected |  |
| U4 | `maxItems` | 2 | aggregate | 1/0 | 2/2 | 0: accepted, 1: accepted |  |
| U5 | `maximum` | 105 | aggregate | 25/77 | 26/28 | 25: accepted, 77: accepted |  |

U2 `maximum` = inconsistent: the forward threshold instance is accepted alone and the reverse threshold instance is rejected alone (measured once, second resume).

## Phase C: duplication test

Renamed copies of one accepted tool, 2 to 4. `copies_rejected_at: null` is NOT "accepted at all counts"; read the coverage column.

| Unit | Construct | Outcomes by copy count | copies_rejected_at | Coverage |
|---|---|---|---|---|
| U1 | `maxItems` | 2: accepted, 3: accepted, 4: accepted | - | complete to 4 copies, all accepted |
| U2 | `maxItems` | 2: accepted, 3: accepted, 4: accepted | - | complete to 4 copies, all accepted |
| U3 | `maxItems` | 2: accepted, 3: accepted, 4: accepted | - | complete to 4 copies, all accepted |
| U4 | `maxItems` | 2: other | - | untested (copy 2 unresolved) |
| U5 | `maximum` | 2: accepted, 3: accepted, 4: accepted | - | complete to 4 copies, all accepted |

## Phase D: magnitude

Every value of the construct set to 1, and every value doubled.

| Unit | Construct | All values = 1 | All values doubled |
|---|---|---|---|
| U1 | `maxItems` | accepted | rejected |
| U2 | `maxItems` | accepted | rejected |
| U3 | `maxItems` | rejected | rejected |
| U4 | `maxItems` | accepted | rejected |
| U5 | `maximum` | accepted | rejected |

## Phase S: stability

| Unit | A0 repeat | maxItems boundary (lower / upper) | Boundary reproduced |
|---|---|---|---|
| U1 | rejected | accepted / rejected | True |
| U2 | rejected | accepted / rejected | True |
| U3 | rejected | accepted / rejected | True |
| U4 | rejected | accepted / rejected | True |
| U5 | rejected | none | n/a |

## Caveats

- POST-HOC and in-sample: the 24 catalogs are the ones the rule was built from, one model (Flash), so there is no launch claim.
- Attribution is assumed, not shown: every HTTP 400 carries the same generic "Request contains an invalid argument." with no reason text.
- The class `aggregate` means "needs several instances together, no single instance responsible". It cannot tell an additive budget from a specific conjunction of instances. In U1 and U3, removing enum also flips while every maxItems is kept, so the rejection depends on the other content of the request.
- Phase C refutes the simple count-budget prediction in U1, U2, U3 and U5: renamed copies of one tool, up to 4, were accepted. By the independent recompute's instance counts (private; not derivable from this aggregate), those copies carried at least as many instances of the flipping construct as the rejected unit. Caveat: C requests are smaller than or comparable to the unit in size, so C does not test a request-level budget at the unit's scale.
- Phase C coverage: complete to 4 copies in U1, U2, U3 and U5; U4 untested (copy 2 unresolved after its one re-send). `copies_rejected_at: null` must not be read as "accepted at all counts".
- Phase D: setting every value to 1 made U1, U2, U4 and U5 accepted; doubling made all rejected. In U3, value 1 was still rejected. The value matters in 4 of 5 units, but not consistently.
- U4: format is instance-critical (one specific format instance is needed).
- U5 (R5, 10-tool unit): removing maxItems does NOT flip it; only removing `maximum` flips it (aggregate, N=105). There is no stability boundary for U5, so it is unreplicated.
- U2 `maximum` = inconsistent (search completed in the second resume): the forward threshold instance is accepted alone and the reverse threshold instance is rejected alone, so neither `aggregate` nor `instance-critical` applies. Measured once.
- Single samples: the stability phase repeats only A0 and the maxItems boundary; the enum, maximum and format boundaries were measured once.

## Unresolved calls

- U4, phase C: copy 2: other outcome

## Deviation from the frozen design

"frozen design specified no retries; 7 calls that failed transiently (3 read timeouts, 4 HTTP 429), logged at ₹0 and returning no result, were re-sent once on resume; a second resume, approved separately with a ₹5 cap, re-sent once the 3 calls that had failed transiently in the first resume (1 read timeout, 2 HTTP 429), also logged at ₹0, and made the planned calls that depend on them for the first time; no paid call was re-sent and no call was re-sent more than once."

Which results depend on a re-sent call (the report's unit-level flag is true for all 5; the precise form is):

| Unit | Re-sent calls touch |
|---|---|
| U1 | D (set-to-1) and S only; A/B do not depend |
| U2 | A0, so everything depends; the C 4-copy result and the B `maximum` search come from the second resume |
| U3 | S only |
| U4 | one A1 non-flipping construct, and the B maxItems single-instance check (its aggregate class depends on it) |
| U5 | one B search point below the observed boundary |

## Provenance

- Design commit: 3d5d6e6
- Plan sha256: `40669f1d723e3c4482c13e9b8fb10504cd240be6eebd8637bf13182b3b28249b`
- Private aggregate input sha256: `9b76bd83f5003a72110ed7880a0e242fe11e26ab402a98f2c0939f73b83f37f9`
- Git HEAD at run: `33ec49121e2229b947092b3a662d595a95b78893`
- Raw call rows stay in the private data directory.
