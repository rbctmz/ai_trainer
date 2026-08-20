# ExecPlan: immediate post-workout feedback

## Goal

After a completed activity is ingested and has a stable plan match, show the
athlete the existing two-field feedback form immediately: completion, session
RPE (1–10), and quality (1–5). The next-day prompt remains a fallback for a
session that was not rated after sync.

## Safety boundary

- This slice changes prompt eligibility/presentation only.
- It does not change activity TSS, provider TSS, the active plan, weekly
  budgets, reconciliation, or match assignments.
- An ambiguous or unstable match never receives a feedback form.
- No delay score is calculated and no automatic calibration is enabled.

## Provider ratings

Intervals.icu exposes provider-side `icu_rpe` and `feel` fields, but provider
scales are not assumed to be identical to AI Trainer scales. A later adapter
may map a documented provider value with explicit provenance; an unknown or
ambiguous scale must remain raw and require athlete confirmation. This slice
does not silently prefill or convert those values.

## Acceptance criteria

1. A same-day completed, stably matched activity can produce a `ready` prompt
   after local sync/reconciliation.
2. The immediate prompt takes precedence over an older fallback prompt.
3. An in-progress activity remains ineligible.
4. An ambiguous/unmatched activity remains `pending_match` or otherwise
   ineligible.
5. If no immediate response is saved, the existing following-day prompt still
   works unchanged.
6. Existing durable fact storage remains append-only and is not consumed by
   TSS/planning in this slice.

## Verification

- Targeted smoke tests for current-day prompt composition and fallback.
- Contributor-safe pytest, Ruff, and web lint/build.
