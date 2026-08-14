# Add a versioned scientific check for active training plans

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds. This document is maintained according to `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, the Planning overview shows a read-only “Научная проверка плана” section. It explains which evidence-backed planning checks pass, which need attention, and which cannot be judged because AI Trainer lacks athlete context. The check never changes sessions, sends workouts, or creates a planning checkpoint. A newly built plan stores the exact audit result and policy version; an older checkpoint is evaluated on read with the current policy and explicitly labelled as such.

The first policy is intentionally narrow. It checks six facts that the existing plan can support honestly: spacing between hard days, a bike-to-run brick in the event-specific Build/Peak period, taper volume shape, preservation of swim/bike/run frequency, swim specificity before race week, and short intensity in all three disciplines during race week. Strength training is not judged because the current planning profile has no strength-experience field. Adding that profile input and any automatic repair is outside this milestone.

## Progress

- [x] (2026-08-14 00:00Z) Read the architecture catalog, ADD analysis, planning workflow, planner pipeline, scheduler, workout catalog, planning overview contract, and current UI.
- [x] (2026-08-14 00:00Z) Re-checked the scientific basis in Blocks and fixed the first rule set and evidence references.
- [x] (2026-08-14 06:15Z) Added RED behavior tests for the pure audit, stored snapshot, legacy read fallback, and UI contract; the first run failed on the absent module and absent API/UI fields.
- [x] (2026-08-14 06:20Z) Implemented the pure versioned audit and attached a freshly calculated snapshot to every newly serialized planning checkpoint.
- [x] (2026-08-14 06:22Z) Projected stored/current audits through `/api/planning/overview` and rendered readable Russian cards in `web/app/planning/page.tsx`.
- [x] (2026-08-14 07:10Z) Corrected the taper comparison to use the pre-taper baseline plus both taper weeks, including a progressive-shape guard.
- [x] (2026-08-14 07:32Z) Completed self-review, 1733-test smoke regression, Python compilation, diff check, web lint/type check, and production build.
- [x] (2026-08-14 07:50Z) Addressed PR review edges: absent eligible phases now produce a data gap, while a covered zero-volume taper week produces an actionable warning.

## Surprises & Discoveries

- Observation: the weekly scheduler already spaces hard occasions and creates triathlon bricks in Build/Peak when feasible.
  Evidence: `models/session_scheduler.py` shares `HARD_SESSION_ROLES`, places long/quality sessions first with spacing, and marks eligible long-bike occasions as bricks. The first audit should inspect the resulting executable plan rather than duplicate scheduler policy.

- Observation: the persisted athlete profile has thresholds and weight but no age, strength history, open-water access, or equipment context.
  Evidence: `data/athlete_profile_store.py` contains FTP, weight, LTHR, running threshold pace, and swim threshold pace only. Strength/open-water rules would therefore guess applicability.

- Observation: the plan already stores catalog, selector, materializer, overlay, and scheduler decisions, but not a scientific-policy version.
  Evidence: `api/planning_service.py::build_plan` assembles the final `goal_plan` before checkpoint provenance and preview. That is the stable insertion point for an audit snapshot.

- Observation: the first four-rule prototype passed the real active plan even though the earlier evidence review found missing swim specificity and missing bike/swim race-week activation.
  Evidence: the local audit returned 4 passed / 0 attention. Inspecting the final sessions showed only recovery/endurance swims in Peak/Taper and only a run activation in race week. Two RED tests and two explicit rules were added before publication; the same plan now returns 4 passed / 2 attention.

- Observation: zero planned minutes and an uncovered week are different scientific states.
  Evidence: PR review exposed that date coverage must be checked independently from summed duration. An uncovered Build/Peak or taper window now yields `data_gap`; a represented week whose sessions were all removed yields `attention`.

## Decision Log

- Decision: Blocks is a curation source, not a runtime dependency of plan generation.
  Rationale: a network call would make a previously identical plan change when the external knowledge base changes, would threaten the ten-second planning-preview budget, and would make offline/self-hosted planning fragile. AI Trainer will freeze inspectable policy constants and evidence identifiers in code.
  Date/Author: 2026-08-14 / Codex.

- Decision: version one is audit-only and never repairs the plan.
  Rationale: this gives visible evidence and reveals false positives before scientific suggestions are allowed to create an approval-gated plan proposal.
  Date/Author: 2026-08-14 / Codex.

- Decision: new plans store the audit snapshot; legacy plans are checked on read without mutation and report `source=current_policy`.
  Rationale: new results remain reproducible while existing users receive the feature immediately. The overview reader preserves its no-write contract.
  Date/Author: 2026-08-14 / Codex.

- Decision: do not include strength or open-water availability in the scored result yet.
  Rationale: the current profile cannot distinguish “not planned” from “not applicable.” A scientific check must prefer a declared data gap over a confident but unsupported warning.
  Date/Author: 2026-08-14 / Codex.

- Decision: distinguish swim specificity and race-week activation from simple discipline frequency.
  Rationale: merely scheduling swim, bike, and run does not prove that event-specific work or taper intensity was retained. These are separate observable claims and produce separate recommendations.
  Date/Author: 2026-08-14 / Codex.

## Outcomes & Retrospective

The active-plan overview now exposes six deterministic, evidence-linked checks in Russian without changing a session. New planning checkpoints keep the exact result and policy version; older plans are evaluated without a write and are visibly labelled as checked with current rules. The real local triathlon plan reports four passed checks and two actionable warnings: missing race-specific swim work in Peak/Taper and missing short swim/bike intensity in race week. Its taper shape passes using the scientifically correct pre-taper baseline: 455 → 340 → 205 minutes, a progressive 55% reduction.

Validation completed on 2026-08-14: `python -m pytest tests/smoke -q` returned 1733 passed and one environment-only socket skip before review, with the complete suite repeated after the review corrections; `npm run lint`, `npm run build`, `python -m compileall -q models api`, and `git diff --check` all completed successfully. The `/planning` page was also checked against the local API with the real plan. No automatic repair was added. The next independent milestone is an approval-gated proposal that can turn selected findings into a future-only plan preview.

## Context and Orientation

`api/planning_service.py::build_plan` produces a deterministic weekly load, applies availability/readiness constraints, expands it through `models/session_scheduler.py`, materializes executable sessions from `models/workout_catalog.py`, stamps stable session identities, and saves an append-only planning checkpoint. `api/planning_service.py::active_plan_overview` reads that checkpoint for `web/app/planning/page.tsx`. The new pure module `models/plan_science_audit.py` will inspect only the completed `goal_plan`; it will not read SQLite, call Blocks, or contact a workout provider.

A finding has one of three statuses. `passed` means the plan contains enough data and meets the frozen policy. `attention` means the plan contains enough data and does not meet the policy. `data_gap` means the plan is too short, has no confirmed event, or lacks another required fact. Severity is independent: version one uses `warning` for an actionable issue and `info` for a data gap.

## Plan of Work

First add `tests/smoke/test_plan_science_audit.py`. The tests build small plan dictionaries rather than call the full planner, proving behavior without coupling to incidental scheduler output. Cover a compliant triathlon plan, adjacent hard days, missing Build/Peak brick, a final-week taper outside the accepted band, missing final-week discipline frequency, a short/rolling plan data gap, and input immutability.

Create `models/plan_science_audit.py` with `SCIENCE_POLICY_VERSION = "plan-science-v1"` and `audit_training_plan(goal_plan) -> dict[str, Any]`. It will normalize plan dates, leaf sessions, roles, phases, durations, and composite brick legs. The response contains `state`, `policy_version`, `source`, `summary`, and stable findings. Each rule embeds the relevant Blocks reference ID, evidence level, DOI, and a compact Russian explanation. No claim depends on an external call at runtime. The swim-specific rule accepts an explicit quality/activation role or a materialized marker such as race pace, open water, sighting, threshold, or VO2. The race-week activation rule independently requires a short intensity marker for swim, bike, and run.

In `api/planning_service.py::build_plan`, call the audit after session identity and final weekly projections, store the result as `science_audit`, and return it in the plan response. In `active_plan_overview`, return the stored snapshot. If the checkpoint predates this feature, calculate the result without saving it and set its source to `current_policy`.

Extend `web/lib/types.ts` with the additive audit contract. Add a `ScientificPlanAudit` component to `web/app/planning/page.tsx` after the weekly-target explanation. It shows a compact summary and one readable card per rule. Russian is primary; `TSS` remains because it is an existing product unit. Evidence references are shown as reference identifiers and evidence levels, not as raw implementation jargon.

Add ADR-0009 and register it in `docs/architecture/asr_catalog.md`. The ADR records why live Blocks calls do not belong in deterministic plan generation and why automatic changes remain a later approval-gated phase.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`, run the new RED suite:

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_plan_science_audit.py -q

After implementation, run:

    python -m pytest tests/smoke/test_plan_science_audit.py tests/smoke/test_planning_active_plan_overview.py tests/smoke/test_api_planning.py -q
    npm --prefix web run lint
    npm --prefix web run build
    python -m compileall models api
    git diff --check

## Validation and Acceptance

A compliant event-goal triathlon checkpoint returns six stable findings with no warnings. A plan with adjacent hard dates returns `attention` for spacing and names the affected dates. A plan without a Build/Peak bike-to-run brick returns an actionable warning. A two-week taper that does not progressively reduce volume to 40–60% below the pre-taper baseline returns a warning. A final week missing swim, bike, or run returns a frequency warning. A plan without a specific Peak/Taper swim or without short final-week intensity in each discipline receives separate actionable warnings. Rolling plans and insufficient horizons produce explicit data gaps rather than passing silently.

Opening `/planning` shows the audit inside the active-plan overview. Refreshing an old checkpoint must not create a new planning history row. Building the same plan inputs under the same policy produces the same audit apart from no timestamps, because the audit payload deliberately contains none.

## Idempotence and Recovery

The pure audit can be called repeatedly without writes. Adding `science_audit` is backward-compatible JSON in an existing append-only checkpoint payload, so no database migration is needed. If UI rendering fails, removing the single component restores the old reader while stored snapshots remain harmless. Automatic repair, profile changes, and provider delivery are explicitly excluded.

## Artifacts and Notes

Blocks evidence frozen for version one:

- `REF-107`, level A, DOI `10.1249/mss.0b013e31806010e0`: taper by reducing volume while retaining intensity and frequency.
- `REF-598`, level B, DOI `10.1123/japa.2015-0021`: masters athletes commonly benefit from roughly 48–72 hours between strenuous/eccentric sessions, with training status as an important limitation.
- `REF-655`, level A, DOI `10.1016/j.jsams.2022.07.006`: cycling impairs the subsequent run in a specific, trainable way; direct brick practice is warranted.
- `REF-536`, level B+, DOI `10.1007/s004210050087`: swimming taper evidence supports reduced volume while maintaining intensity and session frequency.
- `REF-538`, level A, DOI `10.2165/00007256-200232060-00001`: triathlon performance remains discipline-specific and must be trained in all three modalities.

## Interfaces and Dependencies

The new public Python interface is:

    SCIENCE_POLICY_VERSION: str
    def audit_training_plan(goal_plan: Mapping[str, Any], *, source: str = "stored") -> dict[str, Any]

The function uses only the Python standard library. The API adds `science_audit` to both plan-build and active-overview payloads. Existing fields and endpoint behavior remain unchanged.

Revision note (2026-08-14): Initial executable specification created after architecture and Blocks evidence review. Scope is deliberately audit-only so scientific-policy quality can be evaluated before any plan mutation is introduced. Later the same day, the rule set expanded from four to six after the real active plan exposed a false-comfort blind spot in swim specificity and race-week activation. Final review corrected taper volume from a week-to-week comparison to a progressive two-week reduction measured against the pre-taper baseline.
