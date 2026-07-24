# Stripe payments fixture — provenance notes

## Real Stripe operations modeled

This fixture pilots the v2.4 corpus-expansion effort with a real-API domain
(Stripe Payments) instead of the synthetic industrial-IoT domain used by the
existing `call_constraints_server` / `call_constraints_v2_server` fixtures.
Four tools, each modeled on a real Stripe API operation:

| Tool               | Real Stripe operation           | Constrained param(s)                         |
|---------------------|----------------------------------|-----------------------------------------------|
| `create_charge`      | `POST /v1/charges`               | `amount` (range, cents) + `currency` (enum)   |
| `create_refund`      | `POST /v1/refunds`               | `reason` (enum)                               |
| `update_subscription`| `POST /v1/subscriptions/{id}`    | `proration_behavior` (enum)                   |
| `create_customer`    | `POST /v1/customers`             | none (inert — no genuine constrained field)   |

`create_customer` is included in both servers as a realistic 4th operation
(a Stripe payments wrapper would obviously need to create customers before it
can charge them) but is deliberately **excluded** from `TASKS`/
`TASK_CONSTRAINTS`: none of its real fields (`email`, `name`, `description`)
have a genuine enum/format/range constraint worth testing, so forcing a task
onto it would either be inert (always trivially satisfied) or require
inventing a constraint Stripe doesn't actually have.

## Constraint semantics, and why they are genuine (not invented)

- `create_charge.currency`: Stripe's real API takes a lowercase three-letter
  ISO 4217 currency code. `usd`/`eur`/`gbp` are real, commonly used values.
- `create_charge.amount`: Stripe's real API takes the charge amount as an
  integer in the currency's smallest unit (cents for usd/eur, pence for gbp) —
  this is the actual, well-known Stripe convention, not an invented one. The
  fixture's shared range (1000-15000, i.e. $10.00-$150.00) is a fixture-authored
  band chosen to match the "standard monthly fee" framing used consistently
  across all 5 `create_charge` tasks; it is not a literal Stripe-enforced
  minimum/maximum. It is deliberately narrow enough that an agent which
  reports the bare dollar figure instead of converting to cents (e.g. writing
  `20` instead of `2000`) falls outside the range and fails — this is the
  actual signal the range constraint is designed to catch (unit confusion),
  mirroring the debounce-delay/watchdog-timeout range constraints in
  `evals/fixtures/ty2_tasks.py`.
- `create_refund.reason`: Stripe's real API accepts exactly
  `duplicate` / `fraudulent` / `requested_by_customer` for this field. These
  three values are used verbatim as gold values.
- `update_subscription.proration_behavior`: Stripe's real API accepts exactly
  `create_prorations` (default) / `none` / `always_invoice` for this field.
  These three values are used verbatim as gold values.

## Honesty about verification

This was written from the author's existing knowledge of the Stripe API
(field names, enum values, and the cents-based amount convention), **not**
copied from or cross-checked against a live fetch of Stripe's API reference —
this agent does not have live internet access in this session. The field
names and enum values above (`amount`, `currency`, `usd`/`eur`/`gbp`,
`charge_id`, `reason`, `duplicate`/`fraudulent`/`requested_by_customer`,
`subscription_id`, `proration_behavior`,
`create_prorations`/`none`/`always_invoice`, `customer_id`, `email`) are
believed accurate to the real Stripe API as of this agent's training data,
but have not been independently verified against Stripe's live documentation
in this session. All tool descriptions (the prose in
`examples/stripe_payments_server_fixed.py`) are this agent's own paraphrase,
written for this fixture — none of it is copied verbatim from Stripe's actual
API reference text.

## Task design

- 15 tasks total: 5 per constrained tool x 3 constrained tools
  (`create_charge`, `create_refund`, `update_subscription`).
- Anti-tautology: task text never states an enum value, a cents amount, or a
  currency code literally. `create_charge` tasks imply currency via a city
  name (e.g. "Berlin" -> `eur`, "Manchester" -> `gbp`, "Chicago" -> `usd`) and
  imply a consistent "standard monthly fee" amount tier via phrasing, never a
  number. `create_refund`/`update_subscription` tasks imply the correct enum
  member via a real-world scenario (e.g. "submitted twice" -> `duplicate`,
  "billed immediately for the prorated difference right now" ->
  `always_invoice`) without naming it.
