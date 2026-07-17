# RecoveryReplan v2: safely transfer a key session to D+1…D+3

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document is maintained in accordance with `.agent/PLANS.md` from the repository root. It implements Issue #209 on top of merged #206 (honest `sessions[]`, deterministic scheduler, edit-by-`session_id`, grouped bricks) and reuses RecoveryReplan v1 (deterministic keep/downgrade, idempotent proposal, checkpoint claim, confirm/reject/rollback).

## Purpose / Big Picture

Today, when low readiness collides with a key session, RecoveryReplan v1 can only keep the plan or downgrade today's session in place. The athlete's real question — "can I just do this workout the day after tomorrow?" — has no answer. After this change the agent contour builds, for each actionable conflict, up to three typed variants: `keep`, `downgrade_today` (unchanged v1), and the new `transfer_1_3d` — moving the conflicting key session ATOMICALLY to one deterministically chosen safe day among D+1…D+3, preserving its sport, role, stimulus, prescription steps, and TSS, with explicit lineage. When no safe date exists, no transfer is offered and every candidate date's rejection reasons are shown; the contour honestly stays on downgrade/keep.

The contour remains evidence-first and human-in-the-loop: the system detects the conflict and builds a preview against an exact `base_checkpoint_id`, but the plan changes only after explicit confirmation; persist appends a new checkpoint (`source=recovery_replan_transfer`); rollback appends a restored revision; nothing is delivered to the provider and no background auto-apply exists.

## How to see it working

Before: `python -m pytest tests/smoke/test_recovery_transfer.py -q` fails (module absent). After the core milestones the same command passes, and a scripted preview on a synthetic conflicted plan prints one atomic transfer to the chosen date with before/after sessions, safety evidence, and per-candidate rejection reasons — without touching the checkpoint or the provider.

## ASR / risk traceability (mandatory for architectural work)

- ASR-PERF-1 (Today < 2s): the candidate ranker is pure arithmetic over the already-loaded goal plan — no extra DB or provider calls on the Today path; the loop's fingerprint short-circuit from v1 is kept.
- ASR-REL-1 (no completed activity lost across replanning): transfers change identities by lineage (`replaces_session_id`, `transfer_group_id`); reconciliation and feedback read the NEW identity on the new date, and BDD 11 pins that a completed activity on the transferred date never attaches to the replaced session.
- ASR-REL-2 (data gap never crashes): `silence`/`data_gap` gate states short-circuit variant generation exactly as v1.
- ASR-MOD-3 (schema back-compat): all new plan fields are additive; checkpoints without them restore as empty; no DB migration.
- Risk register "contract tests for API routers": the confirm/reject/rollback flow reuses the v1 endpoints' contracts; new fields are covered by smoke contract tests before web wiring.

## Context and Orientation

`models/recovery_replan.py` builds the v1 downgrade variant from the worst gate conflict via the near-term editor rows. `api/recovery_replan_loop.py` runs the loop: fingerprints the readiness report against the active checkpoint, keeps one current proposal, and stores typed outcomes. `api/planning_service.py::apply_recovery_replan` / `rollback_recovery_replan` implement the fail-closed checkpoint claim (stale base → error, no mutation) and append-only rollback. From #206: `session_templates[i].sessions[]` are the executable truth with stable content-derived `session_id`s; `models/planning_near_term.py` edits one session by id (`_apply_targeted_session_edit`) and records `replaced_session_ids`; bricks are single composite occasions with ordered legs; `models/session_scheduler.py` owns the day/hours policies (`MAX_DAY_TSS_POLICY` ceiling, ≤2 occasions/day, hard-session spacing); protected dates and race overlays live on the goal plan.

## Design

A new pure module `models/recovery_transfer.py` owns two functions. `rank_transfer_candidates(goal_plan, conflict, *, today)` evaluates D+1, D+2, D+3 in fixed order and returns one row per candidate with machine-readable `eligible`, `rejected_reasons` (every failed guard listed, not just the first), before/after day sessions, hours and TSS deltas, and `rule_version="recovery-transfer-v1"`. The ranking order is fixed: availability/protection; hard-session collision; recovery spacing; hours/day ceilings without weekly TSS increase; minimal neighbour disruption; nearest date; ISO date tie-breaker. `build_transfer_variant(...)` takes the best eligible candidate and produces the typed `transfer_1_3d` variant: the conflicting `session_id` moves atomically (a composite brick moves as the whole parent with both ordered legs; moving one leg is impossible by construction because the transfer unit is the session, and a leg is not a session), the new session keeps sport/role/template family/steps/TSS with content-derived identity plus `replaces_session_id` and a shared `transfer_group_id`, and the source day is rebuilt without the moved session. Explicit bounded reduction is allowed only when the full stimulus does not fit the target day's ceilings, is named in the variant, and never lets weekly TSS increase. Neighbour changes on the target day appear as separate preview rows; silent removal is forbidden.

The loop composes the decision contract: `variants = [keep, downgrade_today?, transfer_1_3d?]`, recommends the first variant that passed all guards per the issue's precedence, and stays idempotent per readiness/proposal fingerprint with a single current proposal per conflicting session. Confirmation routes through the near-term editor (targeted `session_id` mode from #206) against the exact `base_checkpoint_id`; persist appends `source=recovery_replan_transfer`; rollback appends. Recovery curves (#176) stay shadow: they are not an input to ranking in this version (blocked on #195 anyway).

## Milestones

Milestone one pre-registers the contract RED. `tests/smoke/test_recovery_transfer.py` encodes the deterministic ranking gates and safety guards straight from the issue's BDD list: a safe D+2 yields one atomic transfer preserving stimulus/steps/TSS with lineage (BDD 1); a week where D+1 collides with quality, D+2 is protected, and D+3 is unavailable yields no transfer with three visible rejection reasons while downgrade/keep remain (BDD 2); a brick moves only whole (BDD 3); a two-occasion target day rejects (BDD 4); an oversized stimulus offers only a named bounded reduction and weekly TSS never increases (BDD 5); race microcycle and post-race protected days can never be targets (BDD 6); byte-determinism on identical inputs (BDD 12).

Milestone two implements `models/recovery_transfer.py` until milestone one is green: the ranker, then the variant builder on top of the #206 session primitives.

Milestone three integrates the three-variant decision contract into `api/recovery_replan_loop.py`: typed variants, recommendation precedence, fingerprint idempotence, one current proposal (BDD 10, 12 at loop level).

Milestone four wires confirm/reject/rollback: apply through the targeted near-term edit against the base checkpoint with the fail-closed stale guard (BDD 7), append-only persist with `source=recovery_replan_transfer` and auditable old/new ids (BDD 8), rollback as a new restored revision with a terminal proposal (BDD 9). No provider call anywhere on the path.

Milestone five proves the downstream identity handoff: reconciliation matches a completed activity on the transferred date to the NEW session identity, and post-workout feedback cannot attach to the replaced session (BDD 11).

Milestone six exposes the product surface: API payload with the three preview blocks (why we intervene / what changes / what is protected) and the Today/Decisions web rendering with explicit confirm/reject/evidence/rollback actions; no auto-apply, no push.

Milestone seven is the final vertical validation: full smoke, broad non-live, Next lint/build, a scripted end-to-end preview→confirm→rollback transcript on a synthetic conflict recorded in this document, and Outcomes & Retrospective.

## Decision Log

- Decision: the transfer unit is the session (`session_id`), and a brick is one composite session whose legs are not sessions — atomic brick transfer is therefore structural, not a special case. Rationale: #206 already made position non-identity and legs non-addressable as leaves in the editor. Date/Author: 2026-07-17 / Claude Code.

- Decision: every candidate date reports ALL failed guards, not the first. Rationale: the issue requires honest per-date explanations in the preview; a first-failure short-circuit would hide information the athlete needs to trust the refusal. Date/Author: 2026-07-17 / Claude Code.

- Decision: recovery curves (#176) are explicitly out of the ranking inputs in this version; the lookahead is hard-fixed at D+1…D+3. Rationale: issue text; #195 must land before curves can influence dates. Date/Author: 2026-07-17 / Greg (issue).

- Decision (pre-M2 review): rejection reasons are stable machine codes, not prose — the registry is `unavailable`, `protected`, `hard_collision`, `recovery_spacing`, `occasion_limit`, `day_tss_ceiling`, `weekly_hours_ceiling`, `cross_week_boundary`, each optionally with `details`; a candidate reports ALL failed codes. The UI never parses substrings. Date/Author: 2026-07-17 / Greg (review) + Claude Code.

- Decision (pre-M2 review): the transfer window is D+1…D+3 relative to the SOURCE session's date (the conflict date), never relative to today, never earlier than the source, and never in the past. A future-dated conflict transfers forward from its own date. Date/Author: 2026-07-17 / Claude Code (per review).

- Decision (pre-M2 review): cross-week transfer is FORBIDDEN in v1 (`cross_week_boundary`). Rationale: the weekly budget is the anchor invariant of #206; moving load across the week boundary either inflates the target week or demands explicit neighbour adjustments that contradict v1's minimal-intervention stance. A Friday-or-later conflict may therefore have no transfer candidates — the contour honestly stays on downgrade/keep. Widening to affected-window conservation is a separate future decision. Date/Author: 2026-07-17 / Claude Code (chosen from the review's three options).

- Decision (pre-M2 review): v1 is fail-closed WITHOUT bounded reduction — an oversized stimulus that does not fit the target day's ceilings rejects the candidate (`day_tss_ceiling`/`weekly_hours_ceiling`); `variant["reduction"]` is always absent in v1 and the named numeric reduction policy is deferred to its own slice. Neighbour sessions are never modified by a v1 transfer, so "minimal neighbour disruption" ranks by the number of existing occasions on the target day (an empty day beats an occupied one even if farther). Date/Author: 2026-07-17 / Claude Code (chosen from the review's two options).

- Decision (pre-M2 review): recovery spacing is evaluated on the POST-REMOVAL plan state: a hard transfer may not land adjacent (±1 day) to another hard day, but the source day no longer counts as hard because the session is leaving it. Spacing inputs come from the already-loaded plan sessions only — no DB or provider reads in the ranker. Date/Author: 2026-07-17 / Claude Code.

- Decision (pre-M2 review): a shared atomic primitive `models/session_transfer.py::apply_session_transfer` owns the actual move (clone plan → validate source id → remove source + insert the preserved structured session at the target → rebuild both day projections and weekly buckets → `ensure_session_identities(previous_goal_plan=...)` → verify invariants). The near-term editor is NOT the transfer mechanism: it cannot insert a preserved structured session on another date and rebuilds sessions from scalars, losing steps. Preview and confirm both call this one primitive, so the ranker's promise and the applied result cannot diverge. Date/Author: 2026-07-17 / Greg (review).

## Progress

- [x] (2026-07-17) Read Issue #209, RecoveryReplan v1 (`models/recovery_replan.py`, `api/recovery_replan_loop.py`, apply/rollback in `api/planning_service.py`), and the #206 primitives; created worktree branch `claude/issue-209-recovery-transfer` from `origin/main` (`030652e`).
- [ ] Milestone one: RED contract in `tests/smoke/test_recovery_transfer.py`.
- [ ] Milestone two: `models/recovery_transfer.py` ranker + variant builder green.
- [ ] Milestone three: three-variant decision contract in the loop.
- [ ] Milestone four: confirm/reject/rollback with stale guard and append-only checkpoints.
- [ ] Milestone five: reconciliation/feedback identity handoff.
- [ ] Milestone six: API + Today/Decisions web surface.
- [ ] Milestone seven: final validation, transcript, retrospective.

## Surprises & Discoveries

- (none yet)

## Outcomes & Retrospective

Pending implementation.

## Validation and Acceptance

Acceptance is the issue's twelve BDD criteria, encoded as tests before implementation. The standing commands: `python -m pytest tests/smoke/test_recovery_transfer.py -q` (focused), `python -m pytest tests/smoke -q`, `python -m pytest -m "not live and not debug" tests/ -q`, and `cd web && npm run lint && npm run build`. Nothing is delivered to Intervals.icu at any point; confirm/rollback operate only on local checkpoints.
