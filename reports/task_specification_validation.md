# Task-specification check: post-hoc validation

**Read these caveats first.**

1. POST-HOC and IN-SAMPLE: the rules were designed after seeing the A6 cause taxonomy (wrapper object, free-text required argument, near-duplicate tools, other) and are scored on the same items. These numbers are not out-of-sample performance.
2. The label is open-labeller DISAGREEMENT on required arguments: a noisy proxy for underspecification, not ground truth. A disputed item can be well specified (a labeller error) and an agreed item can be underspecified (shared bias).
3. The control set is stratum-matched, not a random sample, and the 50/50 class balance is by construction. Precision does not transfer to a real prevalence of underspecified tasks; recall and specificity are the transferable quantities.
4. Structural confound: every disputed item has at least one required argument (disagreement on required arguments needs one), while a share of controls has none. Argument-based findings cannot fire on those controls, which inflates specificity and precision. The `restricted_to_items_with_ge1_required_arg` table removes this confound and is the one to read.
5. Possible circularity: the `near_duplicate_tool` field is a boolean that matches a threshold of about 0.70 on `max_cosine_to_other_tool`, a cosine similarity between the gold tool and the most similar other tool in the same catalog; the `primary_cause` and `all_causes` fields are present for disputed items only. The tool-pair near-duplicate findings here use name edit distance and description token overlap on the same catalogs, so the near-duplicate result is not independent of how that field was derived. How `primary_cause` was assigned was not inspected beyond the field values.
6. No launch claim: nothing here gates, scores or changes a published number. The check is opt-in, ADVISORY only.

Zero-LLM, aggregate-only: no model or network call; counts only.

- rule_commit (thresholds fixed): `849e9c482f60ffcddc050202d91381c3ef01362c`
- rule file sha256 at run: `4438ae298e8b21e2ec82d356e26800759e920b3665b3f7c482c6bf055e853add`
- head at run: `e378b17008c2e7d0a1e7907c667fc5e364f3f322` (working tree dirty: False)
- post-validation rule changes: none
- items: 1506 (753 disputed, 753 control; 514 controls have zero required arguments)

## Validation: all items

| finding | TP | FP | FN | TN | precision | recall | specificity |
|---|---|---|---|---|---|---|---|
| task_spec_unstated_required_arg | 279 | 33 | 474 | 720 | 0.894 [0.855, 0.924] (279/312) | 0.371 [0.337, 0.406] (279/753) | 0.956 [0.939, 0.969] (720/753) |
| task_spec_free_text_required_arg | 439 | 170 | 314 | 583 | 0.721 [0.684, 0.755] (439/609) | 0.583 [0.547, 0.618] (439/753) | 0.774 [0.743, 0.803] (583/753) |
| task_spec_wrapper_object_arg | 150 | 0 | 603 | 753 | 1.000 [0.975, 1.000] (150/150) | 0.199 [0.172, 0.229] (150/753) | 1.000 [0.995, 1.000] (753/753) |
| task_spec_near_duplicate_name | 94 | 18 | 659 | 735 | 0.839 [0.760, 0.896] (94/112) | 0.125 [0.103, 0.150] (94/753) | 0.976 [0.963, 0.985] (735/753) |
| task_spec_near_duplicate_description | 196 | 84 | 557 | 669 | 0.700 [0.644, 0.751] (196/280) | 0.260 [0.230, 0.293] (196/753) | 0.888 [0.864, 0.909] (669/753) |
| near_duplicate_name_or_description | 287 | 95 | 466 | 658 | 0.751 [0.706, 0.792] (287/382) | 0.381 [0.347, 0.416] (287/753) | 0.874 [0.848, 0.896] (658/753) |
| any_finding | 669 | 246 | 84 | 507 | 0.731 [0.701, 0.759] (669/915) | 0.888 [0.864, 0.909] (669/753) | 0.673 [0.639, 0.706] (507/753) |

## Validation: items with at least one required argument (confound removed)

753 positive, 239 negative.

| finding | TP | FP | FN | TN | precision | recall | specificity |
|---|---|---|---|---|---|---|---|
| task_spec_unstated_required_arg | 279 | 33 | 474 | 206 | 0.894 [0.855, 0.924] (279/312) | 0.371 [0.337, 0.406] (279/753) | 0.862 [0.812, 0.900] (206/239) |
| task_spec_free_text_required_arg | 439 | 170 | 314 | 69 | 0.721 [0.684, 0.755] (439/609) | 0.583 [0.547, 0.618] (439/753) | 0.289 [0.235, 0.349] (69/239) |
| task_spec_wrapper_object_arg | 150 | 0 | 603 | 239 | 1.000 [0.975, 1.000] (150/150) | 0.199 [0.172, 0.229] (150/753) | 1.000 [0.984, 1.000] (239/239) |
| task_spec_near_duplicate_name | 94 | 3 | 659 | 236 | 0.969 [0.913, 0.989] (94/97) | 0.125 [0.103, 0.150] (94/753) | 0.987 [0.964, 0.996] (236/239) |
| task_spec_near_duplicate_description | 196 | 55 | 557 | 184 | 0.781 [0.726, 0.828] (196/251) | 0.260 [0.230, 0.293] (196/753) | 0.770 [0.712, 0.819] (184/239) |
| near_duplicate_name_or_description | 287 | 56 | 466 | 183 | 0.837 [0.794, 0.872] (287/343) | 0.381 [0.347, 0.416] (287/753) | 0.766 [0.708, 0.815] (183/239) |
| any_finding | 669 | 207 | 84 | 32 | 0.764 [0.734, 0.791] (669/876) | 0.888 [0.864, 0.909] (669/753) | 0.134 [0.096, 0.183] (32/239) |

## Recall within disputed items, by `primary_cause`

| primary_cause | n | task_spec_unstated_required_arg | task_spec_free_text_required_arg | task_spec_wrapper_object_arg | task_spec_near_duplicate_name | task_spec_near_duplicate_description | near_duplicate_name_or_description | any_finding |
|---|---|---|---|---|---|---|---|---|
| enum_or_case_difference | 32 | 0.531 [0.364, 0.691] (17/32) | 1.000 [0.893, 1.000] (32/32) | 0.000 [0.000, 0.107] (0/32) | 0.094 [0.032, 0.242] (3/32) | 0.219 [0.110, 0.388] (7/32) | 0.312 [0.180, 0.486] (10/32) | 1.000 [0.893, 1.000] (32/32) |
| free_text_paraphrase | 331 | 0.468 [0.415, 0.522] (155/331) | 0.816 [0.770, 0.854] (270/331) | 0.051 [0.032, 0.081] (17/331) | 0.154 [0.119, 0.197] (51/331) | 0.100 [0.072, 0.137] (33/331) | 0.254 [0.210, 0.303] (84/331) | 0.912 [0.877, 0.938] (302/331) |
| list_order_or_membership | 8 | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) | 0.000 [0.000, 0.324] (0/8) |
| missing_required_arg | 154 | 0.656 [0.578, 0.726] (101/154) | 0.552 [0.473, 0.628] (85/154) | 0.143 [0.096, 0.207] (22/154) | 0.240 [0.180, 0.314] (37/154) | 0.279 [0.214, 0.355] (43/154) | 0.519 [0.441, 0.597] (80/154) | 0.877 [0.815, 0.920] (135/154) |
| nested_object_difference | 9 | 0.111 [0.020, 0.435] (1/9) | 0.111 [0.020, 0.435] (1/9) | 0.778 [0.453, 0.937] (7/9) | 0.111 [0.020, 0.435] (1/9) | 0.889 [0.565, 0.980] (8/9) | 0.889 [0.565, 0.980] (8/9) | 1.000 [0.701, 1.000] (9/9) |
| numeric_formatting | 14 | 0.000 [0.000, 0.215] (0/14) | 1.000 [0.785, 1.000] (14/14) | 0.000 [0.000, 0.215] (0/14) | 0.000 [0.000, 0.215] (0/14) | 0.000 [0.000, 0.215] (0/14) | 0.000 [0.000, 0.215] (0/14) | 1.000 [0.785, 1.000] (14/14) |
| value_type_or_shape_mismatch | 111 | 0.045 [0.019, 0.101] (5/111) | 0.333 [0.253, 0.425] (37/111) | 0.414 [0.327, 0.507] (46/111) | 0.018 [0.005, 0.063] (2/111) | 0.216 [0.150, 0.302] (24/111) | 0.216 [0.150, 0.302] (24/111) | 0.775 [0.689, 0.843] (86/111) |
| wrapper_object_flattening | 94 | 0.000 [0.000, 0.039] (0/94) | 0.000 [0.000, 0.039] (0/94) | 0.617 [0.516, 0.709] (58/94) | 0.000 [0.000, 0.039] (0/94) | 0.862 [0.778, 0.917] (81/94) | 0.862 [0.778, 0.917] (81/94) | 0.968 [0.910, 0.989] (91/94) |

## Recall within disputed items, by pilot

| pilot | n | task_spec_unstated_required_arg | task_spec_free_text_required_arg | task_spec_wrapper_object_arg | task_spec_near_duplicate_name | task_spec_near_duplicate_description | near_duplicate_name_or_description | any_finding |
|---|---|---|---|---|---|---|---|---|
| A5 | 247 | 0.093 [0.063, 0.136] (23/247) | 0.385 [0.326, 0.447] (95/247) | 0.429 [0.369, 0.491] (106/247) | 0.012 [0.004, 0.035] (3/247) | 0.462 [0.400, 0.524] (114/247) | 0.462 [0.400, 0.524] (114/247) | 0.964 [0.932, 0.981] (238/247) |
| A6 | 506 | 0.506 [0.462, 0.549] (256/506) | 0.680 [0.638, 0.719] (344/506) | 0.087 [0.065, 0.115] (44/506) | 0.180 [0.149, 0.216] (91/506) | 0.162 [0.133, 0.197] (82/506) | 0.342 [0.302, 0.384] (173/506) | 0.852 [0.818, 0.880] (431/506) |

## Recall within disputed items, by number of required arguments

| n required | n | task_spec_unstated_required_arg | task_spec_free_text_required_arg | task_spec_wrapper_object_arg | task_spec_near_duplicate_name | task_spec_near_duplicate_description | near_duplicate_name_or_description | any_finding |
|---|---|---|---|---|---|---|---|---|
| 1 | 422 | 0.159 [0.127, 0.197] (67/422) | 0.502 [0.455, 0.550] (212/422) | 0.227 [0.190, 0.270] (96/422) | 0.073 [0.052, 0.102] (31/422) | 0.315 [0.273, 0.361] (133/422) | 0.382 [0.336, 0.429] (161/422) | 0.865 [0.829, 0.894] (365/422) |
| 2 | 154 | 0.500 [0.422, 0.578] (77/154) | 0.727 [0.652, 0.791] (112/154) | 0.097 [0.060, 0.154] (15/154) | 0.208 [0.151, 0.279] (32/154) | 0.065 [0.036, 0.115] (10/154) | 0.273 [0.209, 0.348] (42/154) | 0.890 [0.830, 0.930] (137/154) |
| 3+ | 177 | 0.763 [0.695, 0.819] (135/177) | 0.650 [0.577, 0.716] (115/177) | 0.220 [0.166, 0.287] (39/177) | 0.175 [0.126, 0.238] (31/177) | 0.299 [0.237, 0.371] (53/177) | 0.475 [0.402, 0.548] (84/177) | 0.944 [0.899, 0.969] (167/177) |

## Recall within disputed items, by the `near_duplicate_tool` field

| near_duplicate_tool | n | task_spec_unstated_required_arg | task_spec_free_text_required_arg | task_spec_wrapper_object_arg | task_spec_near_duplicate_name | task_spec_near_duplicate_description | near_duplicate_name_or_description | any_finding |
|---|---|---|---|---|---|---|---|---|
| flag_false | 700 | 0.379 [0.343, 0.415] (265/700) | 0.584 [0.547, 0.620] (409/700) | 0.194 [0.167, 0.225] (136/700) | 0.134 [0.111, 0.162] (94/700) | 0.204 [0.176, 0.236] (143/700) | 0.334 [0.300, 0.370] (234/700) | 0.880 [0.854, 0.902] (616/700) |
| flag_true | 53 | 0.264 [0.164, 0.396] (14/53) | 0.566 [0.433, 0.690] (30/53) | 0.264 [0.164, 0.396] (14/53) | 0.000 [0.000, 0.068] (0/53) | 1.000 [0.932, 1.000] (53/53) | 1.000 [0.932, 1.000] (53/53) | 1.000 [0.932, 1.000] (53/53) |

## Trivial baselines on the same labels

| predictor | TP | FP | FN | TN | precision | recall | specificity |
|---|---|---|---|---|---|---|---|
| has at least one required argument | 753 | 239 | 0 | 514 | 0.759 [0.731, 0.785] (753/992) | 1.000 [0.995, 1.000] (753/753) | 0.683 [0.649, 0.715] (514/753) |
| `near_duplicate_tool` field | 53 | 54 | 700 | 699 | 0.495 [0.402, 0.589] (53/107) | 0.070 [0.054, 0.091] (53/753) | 0.928 [0.908, 0.945] (699/753) |

`near_duplicate_tool` field vs `max_cosine_to_other_tool`: lowest cosine with flag true 0.7026, highest with flag false 0.6956.

## Prevalence on the repo's committed task corpora

Share of tasks on which each finding fires (no label; nothing here says a flagged task is wrong).

| corpus | n | task_spec_unstated_required_arg | task_spec_free_text_required_arg | task_spec_wrapper_object_arg | task_spec_near_duplicate_name | task_spec_near_duplicate_description | near_duplicate_name_or_description | any_finding |
|---|---|---|---|---|---|---|---|---|
| argument_degradation_253 | 253 | 0.866 [0.818, 0.902] (219/253) | 0.874 [0.827, 0.909] (221/253) | 0.000 [0.000, 0.015] (0/253) | 0.000 [0.000, 0.015] (0/253) | 0.000 [0.000, 0.015] (0/253) | 0.000 [0.000, 0.015] (0/253) | 0.972 [0.944, 0.987] (246/253) |
| predictive_validity_44_tool_sets | 1136 | 0.441 [0.412, 0.470] (501/1136) | 0.671 [0.643, 0.697] (762/1136) | 0.021 [0.014, 0.031] (24/1136) | 0.074 [0.060, 0.091] (84/1136) | 0.082 [0.067, 0.099] (93/1136) | 0.138 [0.119, 0.159] (157/1136) | 0.773 [0.748, 0.796] (878/1136) |
