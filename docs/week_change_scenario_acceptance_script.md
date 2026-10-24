# Week-change scenario — comparative acceptance script

Issue [#719](https://github.com/rbctmz/ai_trainer/issues/719). Prepared
2026-10-24 as a Spec / Architecture Owner artifact at the human owner's
request. Inputs: [competitive overview](../research/intervals_apps_competitive_overview.md)
(cut 2026-10-20, PR #718), [AI Trainer product profile](../research/ai_trainer_product_profile.md)
(2026-10-20, HEAD `fda0c83`), and the 2026-10-24 owner discussion. This
document records a decision and a manual acceptance script; it is not an
implementation plan and opens no implementation slices by itself.

## Owner decision (2026-10-24)

1. **Priority 1** — finish one complete week-change scenario on the primary
   product path: a missed key workout → a proposed week change → human
   confirmation → delivery → rollback. Closing the user-visible
   delivery-status/reconciliation gap is part of this priority.
2. **Priority 2** — only after Priority 1, validate event-style proactivity:
   noticing a missed session or a recovery/plan conflict and proposing one
   concrete action at the right time.
3. **Non-goals for now** — expanding the workout catalog, AI models, and
   channels.

The decision narrows focus per the 2026-10 research; it does not reopen
accepted planning scopes (#677 S-series) and sets no deadlines.

## Why this scenario (evidence)

**Observed:** Paceform publicly shows week changes with an explicit
Apply/Keep step; TriCoach AI shows approve-week with A/B/C priorities;
TrainerAI runs a Telegram-first proactive loop (writes first, missed-session
checks, weekly review). "AI composes and adapts the plan" and even an
approval button are therefore table stakes, not differentiators.

**Observed:** in the AI Trainer tree the loop machinery already exists —
RecoveryReplan v2 (keep/downgrade/transfer D+1…D+3), preview/confirm with
fingerprint freshness checks, the constraint ledger, append-only checkpoints
and rollback — but the surfaces where this loop lives («Решения»,
«Восстановление», shadow Today) are reachable only behind
`NEXT_PUBLIC_SHOW_DEV_TOOLS`. Today the advantage is invisible to a normal
user.

**Inferred:** the defensible positioning is a *verifiable plan lifecycle* —
saved proposals, stale-confirm protection, explainable diffs, append-only
rollback, honest delivery status — reachable on the primary path.

**Verified by:** the product profile and the competitive overview cited
above. Comparative uniqueness of the whole combination is *not* proven
without running the same script against shortlist competitors; that run is
the cheap falsifier (below).

## Scenario script (identical for every product)

Run black-box, as a user, on each product's primary path. Record per step:
what the user sees, what is saved, what is reversible, with
Observed/Inferred markers. Where a platform makes a step impossible, record
`n/a` = "not confirmed", never "absent".

Prerequisites: a confirmed plan containing one key session this week; a
connected delivery target (for AI Trainer: Intervals.icu calendar delivery).

| # | Step | Observable to check |
| --- | --- | --- |
| S1 | Miss the key workout (no fact by end of day, or mark unavailable) | The miss is noticed without the user assembling a report; plan-fact state reflects it |
| S2 | A week change is proposed | The proposal explains what changes, why (evidence), what stays protected (protected dates / constraint ledger), and the impact on the rest of the week |
| S3 | The proposal is saved before confirmation | It survives a reload/restart and is never applied silently |
| S4 | Confirmation with a freshness guard | Changing the underlying state between preview and confirm rejects the stale confirmation with an explanation |
| S5 | Delivery | The change reaches the delivery target; delivery status is visible; re-send works after a failure; the difference between "written to the calendar/API" and "confirmed on the device" is stated honestly |
| S6 | Rollback | The change can be undone; history is preserved; re-confirmation works after undo |

## Acceptance criteria — "scenario is finished" for AI Trainer

- **A1:** the whole S1–S6 loop is passable on the primary web path without
  `NEXT_PUBLIC_SHOW_DEV_TOOLS`.
- **A2:** every step has a user-visible result and a plain-language
  explanation (diff, protected items, why).
- **A3:** proposals are persisted (S3); the stale-guard is active (S4);
  rollback works and is recorded (S6).
- **A4:** delivery status is visible and honest; re-send after a forced
  failure succeeds (S5). The delivery-status/reconciliation debt recorded in
  the product profile is closed at the user-visible level.
- **A5:** per-step evidence is recorded under the repository evidence
  discipline (`Observed` / `Inferred` / `Verified by`).

## Competitor runs

Products: Paceform (web/PWA; closest full loop), TriCoach AI (PWA; triathlon
A/B/C), TrainerAI (Telegram-first). Run S1–S6 identically; note the platform
per step. Author claims found in announcements are recorded as `medium`
confidence until the run reproduces them (for example, any statement about
what does or does not reach a watch is verified in S5, not assumed).

Caveats fixed in advance:

- This run intentionally crosses the research boundary of "no paid
  onboarding": 2–3 competitor subscriptions are a small budget the owner
  accepts for this test.
- Comparison is fair by scenario, not by platform (PWA vs web vs Telegram).
- Results prove observable product behavior only — not coaching quality,
  adoption, or market share.

**Falsifier:** if a competitor passes S1–S6 with a visibly better user
experience (not mere parity), the "verifiable plan lifecycle" positioning
claim must be revisited before further investment.

## Non-goals

- Judging the quality of coaching decisions (only observability and
  explainability of changes are in scope).
- Market sizing or adoption claims from announcement counts.
- Expanding the catalog, models, or channels — explicitly deprioritized by
  the owner decision above.

## Related material

- Research: [overview](../research/intervals_apps_competitive_overview.md),
  [new announcements](../research/intervals_apps_new_2026q3.md),
  [registry](../research/intervals_apps_2026_10_registry.json),
  [methodology](../research/comparison_methodology.md).
- Implemented machinery cited from the profile:
  `api/recovery_replan_loop.py`, `api/planning_service.py`,
  `services/planning_cycles.py`,
  [planning S1 acceptance](planning_preview_confirm_acceptance.md).
- Follow-on work (Priority 2) gets its own issue after the A1–A5 run is
  recorded; implementation slices get their own specs per
  [the development workflow](AI_Feature_Development_Workflow.md).
