# Adherence-лента план vs факт: многонедельный тренд исполнения плана

This ExecPlan is a living document maintained per `.agent/PLANS.md`. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must stay current. It implements Issue #228.

## Purpose / Big Picture

The WoZ pilot's key trust finding (К2, 2026-07-13): the bottleneck is not forecast accuracy but adherence — the athlete matched plan≈fact roughly twice in 13 days and could not SEE that anywhere. All the analytics already exist (adherence classification, plan-actual reconciliation with a confirmation ledger, a read-only multi-week snapshot API in `services/reconciliation.py`), but no surface shows a TREND: today's `/today` shows only yesterday, `/planning` shows a one-week working table for confirming matches. After this change the athlete opens `/adherence` and sees a 4-week day-by-day ribbon (each day: planned vs actual TSS and a status — exact / substituted / major_deviation / missed / unplanned / rest) plus weekly aggregate cards (adherence buckets, missed key sessions, planned vs actual TSS, unplanned TSS), and `/today` carries a compact 7-day strip linking to the full ribbon. Everything is read-only and derived — no new analytics, no provider calls, no mutations.

## How to see it working

Before: `python -m pytest tests/smoke/test_adherence_ribbon.py -q` fails (module and endpoint absent). After the core milestones the same command passes; `GET /api/adherence?weeks=4` returns weekly and daily aggregates on a seeded plan+activities database; `cd web && npm run build` succeeds with the new `/adherence` page; the `/today` strip renders from the same payload shape.

## ASR / risk traceability

- ASR-PERF-1 (Today < 2s): the `/today` strip reuses the already-computed reconciliation path with `include_provider=False` — no live provider calls on render, pinned by a contract gate.
- ASR-REL-2 (data gap never crashes): `has_plan=false` and `data_quality` pass through; empty states render, not 500s.
- ASR-MOD-3 (no schema change): the ribbon is a pure derivation over `reconciliation_at` output + existing ledger; no DB migration, no new tables.
- Risk "duplicated business logic between surfaces": day/week aggregation lives in ONE pure module (`models/adherence_ribbon.py`); the API router and both web surfaces consume its output — the web never re-derives statuses.

## Context and Orientation

- `models/session_quality_forecast.py::classify_plan_adherence(planned, actual)` → `exact` (same sport, 80–120% TSS) / `substituted` (60–140%) / `major_deviation`; `None` when uncomparable.
- `models/plan_actual_reconciliation.py::build_reconciliation(...)` → `{rows: [...], unplanned_activities: [...], data_quality, rule_version, ...}`; each row carries `planned` (date/sport/role/tss/session_id), `match_status` (`matched`/`unmatched`/...), `adherence`, `actual_total_tss`, matched activities. The ledger (`plan_actual_matches`) already folds user confirmations in.
- `services/reconciliation.py::reconciliation_at(db, *, weeks≤12, as_of, include_provider)` — the canonical snapshot; `include_provider=False` skips Intervals.icu entirely.
- `api/routers/planning.py` hosts `/api/planning/reconciliation`; the new read-only router follows the same style. `web/app/today/page.tsx` has the Yesterday block to extend; `web/app/planning/page.tsx` keeps the confirmation workflow.
- Existing test patterns: `tests/smoke/test_planning_execution.py` and `test_plan_actual_reconciliation.py` seed a plan checkpoint + activities into a tmp `Database` and call service functions directly; the API layer is covered with FastAPI `TestClient`.

## Design

A new pure module `models/adherence_ribbon.py` owns `build_adherence_ribbon(reconciliation, *, as_of, weeks)`: input is the exact payload `reconciliation_at` returns; output is `{"has_plan", "weeks": [...], "days": [...], "rule_version", "data_quality"}`. Weeks are ISO Monday-aligned windows ending at `as_of`'s week. A day's status is derived in priority order: any matched row with the worst adherence of that day (`major_deviation` > `substituted` > `exact` — the worst honest label wins), else `missed` when a planned TSS>0 session is unmatched, else `unplanned` when only unplanned activities exist, else `rest`. A week aggregates: planned/matched session counts, per-bucket counters (missed = unmatched planned), `missed_key_sessions` (unmatched roles from the scheduler's hard set `{quality, long}` — imported from `models.session_scheduler.HARD_SESSION_ROLES`, not duplicated), planned vs actual TSS over matched rows, and unplanned TSS. The module never reads the DB and never calls providers — determinism gates pin byte-equal output on identical input.

The API router `api/routers/adherence.py` exposes `GET /api/adherence?weeks=4` (clamped to [1, 8]) calling `reconciliation_at(db, weeks=weeks, include_provider=False)` then `build_adherence_ribbon`; `has_plan=false` passes through with empty ribbon. The web adds `/adherence` (nav «План vs факт»): weekly aggregate cards on top, the day ribbon under them, each day linking to `/planning?focus=<date>` for match confirmation (read-only here). `/today` gains a compact 7-day strip consuming the same endpoint with `weeks=1`, linking to `/adherence`.

## Milestones

Milestone one pre-registers the contract RED in `tests/smoke/test_adherence_ribbon.py`: the pure module's day-status matrix (BDD 1–3, 6: exact/substituted/major_deviation days, missed planned session, unplanned-only day, rest day; worst-of-day rule; missed key sessions via the shared hard-role set; TSS sums reconcile with input rows; byte-determinism) and the API contract (weeks clamp, has_plan=false empty state, include_provider=False pinned — the gate monkeypatches the provider path and fails if touched).

Milestone two implements `models/adherence_ribbon.py` to green, then the router.

Milestone three wires the web: `/adherence` page + nav, `/today` strip; `npm run lint && npm run build`; source-contract smoke pins that the web consumes the API payload and never re-derives statuses.

Milestone four is validation: full smoke, broad non-live, a scripted acceptance transcript on a seeded database recorded here, retrospective. Live acceptance on a copy of the production DB only with explicit authorization.

## Decision Log

- Decision: the ribbon is a pure derivation over the EXISTING `reconciliation_at` snapshot with `include_provider=False`; no new analytics, no DB reads in the module, no provider calls on any render path. Rationale: trust surface must not create a second source of truth; ASR-PERF-1. Date/Author: 2026-07-19 / Claude Code.
- Decision: a day's status is the WORST honest label among its matched rows, and `missed` only applies to planned TSS>0 sessions. Rationale: a ribbon that averages away a major_deviation would soothe instead of inform — the same honesty principle as #205/#226 explicit reductions. Date/Author: 2026-07-19 / Claude Code.
- Decision: `weeks` ceiling is 8 (не 12): the ribbon is a trust surface, not an archive; longer windows belong to future analytics pages. Date/Author: 2026-07-19 / Claude Code.
- Decision: match confirmation stays on `/planning`; the ribbon links to it per-day. Rationale: one mutation surface per workflow — the ribbon stays read-only. Date/Author: 2026-07-19 / Claude Code.

## Progress

- [x] (2026-07-19) Read Issue #228 sources: `classify_plan_adherence`, `build_reconciliation` row shape, `reconciliation_at(include_provider=False)`, current `/today` Yesterday block and `/planning` reconciliation table; created worktree branch `claude/issue-228-adherence-ribbon` from `origin/main` (fd64a23).
- [ ] Milestone one: RED contract in `tests/smoke/test_adherence_ribbon.py`.
- [ ] Milestone two: `models/adherence_ribbon.py` + `api/routers/adherence.py` green.
- [ ] Milestone three: web `/adherence` + `/today` strip.
- [ ] Milestone four: validation, transcript, retrospective.

## Surprises & Discoveries

- (none yet)

## Outcomes & Retrospective

Pending implementation.

## Validation and Acceptance

Acceptance is the issue's six BDD criteria encoded as tests before implementation. Commands: `python -m pytest tests/smoke/test_adherence_ribbon.py -q`, `python -m pytest tests/smoke -q`, `python -m pytest -m "not live and not debug" tests/ -q`, `cd web && npm run lint && npm run build`. No provider calls anywhere on the path; live acceptance on a production-DB copy only with explicit authorization.
