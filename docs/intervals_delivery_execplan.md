# Deliver AI Trainer plans through Intervals.icu to the athlete's device

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

AI Trainer can build, explain, reconcile, and safely adjust a training plan, but the athlete still follows IntervalCoach because those workouts arrive in Intervals.icu and then on Garmin. After this change, the athlete can open the web Planning export tab and send the next one or two weeks of the active AI Trainer plan to Intervals.icu with one action. Sending the same range again updates AI Trainer's own events instead of creating duplicates and never edits IntervalCoach or manually created workouts. When a recovery proposal is approved or rolled back, the affected workout dates are delivered again automatically so the plan shown in AI Trainer and the workout on the device stay aligned.

The delivered event is not merely a calendar note. AI Trainer serializes the existing catalog prescription into Intervals.icu native workout text. A successful provider response must contain parsed `workout_doc.steps`; this is the evidence that Intervals.icu recognized an executable workout that can enter its Garmin delivery path. A composite brick is sent as two ordered workout events, one for each leg. Older persisted checkpoints that predate the workout catalog use the existing `models.fit_export.build_steps_for_sport` fallback rather than being silently delivered without steps.

## Progress

- [x] (2026-07-14 09:17Z) Audited issue #168, the current create-only Intervals.icu adapter, active plan/session identity, plan-actual reconciliation, recovery proposal apply/rollback, web Export mode, official Intervals.icu OpenAPI, and the live account in read-only mode.
- [x] (2026-07-14 09:17Z) Published the pre-ExecPlan contract and mandatory BDD scenarios in issue #168 comment `4967348427`.
- [x] (2026-07-14 09:22Z) Created isolated worktree `/private/tmp/ai_trainer_issue168` on branch `codex/issue-168-intervals-delivery` from clean `main` at `3983cf5`.
- [x] (2026-07-14 13:02Z) Added failing provider-adapter, delivery-domain, API, proposal lifecycle, and reconciliation contracts before production code; the focused red run reported 11 expected failures at missing module/method/route/identity boundaries and retained 47 passing adjacent tests.
- [x] (2026-07-14 13:30Z) Implemented deterministic UUID-v5 slot identity, material external ids, native executable workout text with legacy fallback, composite-leg delivery, bounded bulk upsert/delete, and owned-only cleanup.
- [x] (2026-07-14 13:30Z) Exposed the FastAPI delivery action and connected recovery approve plus rollback with affected-date sync and fail-open provider evidence; the focused contour is green at `58 passed`.
- [x] (2026-07-14 13:48Z) Added the web Export delivery selector/button and explicit executable/calendar-only/deleted/failed result states; Next lint and production build pass.
- [x] (2026-07-14 13:50Z) Completed focused (`58 passed`), contributor-safe smoke (`602 passed, 1 skipped`), broad non-live (`645 passed, 6 skipped, 24 deselected`), Python compilation, Next lint/build, and static self-review. Isolated browser/provider acceptance remains.
- [x] (2026-07-14 13:58Z) Completed isolated browser acceptance against a local Intervals-compatible mock and temporary SQLite: two UI submissions returned `1 executable / 0 calendar-only / 0 failed` and converged on one event id with parsed steps; all temporary servers were stopped.
- [x] (2026-07-14 14:25Z) Repeated deletion-safety self-review after opening implementation PR #192. Added regression coverage for non-contiguous recovery dates and partial bulk responses, then made cleanup fail closed; the focused delivery/recovery/API/reconciliation contour is green at `60 passed`.
- [x] (2026-07-14 14:38Z) Merged current `main` after recovery-curves PR #187 landed and verified the combined tree: focused integration `102 passed`, smoke `649 passed, 1 skipped`, broad non-live `692 passed, 6 skipped, 24 deselected`, Next lint and production build clean.
- [x] (2026-07-14 14:55Z) Added a test-driven, fail-closed live acceptance runner. Five fake-provider scenarios prove the exact confirmation gate, acceptance-only UID, two-upsert identity, foreign preservation, cleanup on parser failure, residual refusal, and future-only date guard without any live request; the expanded smoke suite is `654 passed, 1 skipped`.
- [x] (2026-07-14 15:10Z) Addressed both independent-review findings plus the cheap follow-ups: empty recovery date sets are provider-free `skipped`, template/day alignment is verified before payload creation, manual windows use `ATHLETE_TIMEZONE`, and unused creator fields were removed. A legacy pre-#168 rollback integration test proves the false failure is gone; smoke is `658 passed, 1 skipped`, broad non-live is `701 passed, 6 skipped, 24 deselected`, and Next lint/build plus compileall are clean.
- [ ] Perform the separately authorized reversible live Intervals.icu acceptance: upsert twice, inspect parsed `workout_doc`, verify no foreign mutation, and remove only the temporary AI Trainer acceptance events.
- [ ] Finalize this living document after live evidence and obtain independent review of implementation PR #192 before merge. PR #191 contains only the already-merged ExecPlan because it was merged while implementation was still in progress.

## Surprises & Discoveries

- Observation: the existing Intervals.icu write path is create-only even though the official API has safe bulk upsert and bulk delete.
  Evidence: `services/intervals_icu.py::push_planned_events` calls `create_events`, which performs one plain `POST /events` per payload. The official OpenAPI exposes `POST /events/bulk` with `upsertOnUid` and `PUT /events/bulk-delete`.

- Observation: exact provider reconciliation is already designed but cannot activate for current exports.
  Evidence: `models/plan_actual_reconciliation.py` treats `external_id == "ai_trainer:<session_id>"` as confidence `1.0`, while `build_planned_event_payload` does not emit `external_id`.

- Observation: the current live plan is a legacy checkpoint created before catalog materialization.
  Evidence: its future plan rows have deterministic `ats_...` session ids and template keys, but `materialized_steps=[]` and no legs. Delivery must reuse the TCX/FIT fallback instead of assuming new checkpoints only.

- Observation: the live account proves both the ownership risk and the required brick granularity.
  Evidence: the bounded read-only query returned eleven IntervalCoach workouts with `oauth_client_id=173`, no AI Trainer external id, and two separate events on brick days. The old AI Trainer event from 2026-06-08 has neither a managed external id nor a deterministic slot identity and must be left untouched.

- Observation: a real IntervalCoach event contains parseable native workout text and a populated provider-side workout document.
  Evidence: event `119641533` contains lines such as `- Race Pace 1 9m 87-95% 90rpm`; the read-only response includes five `workout_doc.steps` and `moving_time=1860`.

- Observation: the contract-first red run reached every intended writeback boundary without any provider I/O.
  Evidence: the focused command reported `11 failed, 47 passed`. Failures were the missing deterministic delivery model/service, bulk adapter methods and retained provider fields, delivery API contract, recovery affected dates/side effect, and composite-leg exact identity. The contributor-safe autouse fixture removed the developer API key before every non-live test.

- Observation: composite identity fixtures must include the same ordered leg indexes as materialized catalog plans.
  Evidence: a first reconciliation test mutated an already-identified session into an index-less composite, so a second identity pass correctly produced a different material ID. Real catalog bricks already freeze `leg_index`; the corrected fixture builds the composite before identity and the exact leg external-id contract passes.

- Observation: the complete web/API/provider loop is idempotent under an Intervals-compatible runtime, not only under unit mocks.
  Evidence: an isolated Next page on `:3018` called an isolated FastAPI on `:8018`, which called a local provider mock on `:8099`. Two button clicks both showed one executable workout and zero errors; the bounded provider read contained exactly one event, id `9001`, with the same UUID-v5 slot, owned external id, native four-step description, and non-empty `workout_doc.steps`.

- Observation: a bounded provider window is wider than an explicit non-contiguous recovery date set.
  Evidence: the first implementation listed from the earliest to latest affected date and considered every owned event in that interval stale. A regression with selected dates 15 and 17 July proved it would delete the untouched 16 July workout. Cleanup now additionally requires the event's local date to be in the explicit selected set.

- Observation: cleanup after a partial or malformed bulk response can make a transient provider failure destructive.
  Evidence: a two-leg replacement returning confirmation for only one UID previously deleted the old single-slot event before reporting `partial`. Cleanup now runs only after every desired UID is confirmed, while a deliberate all-rest or removed-date sync can still delete stale owned slots.

- Observation: legacy approved recovery proposals do not contain `affected_dates`.
  Evidence: independent review reproduced `safe_deliver_active_plan(dates=[])` as a retryable failure even though no provider call was needed. Empty explicit date sets now return a zero-count, non-retryable `skipped` result before client resolution; an integration fixture removes `affected_dates` from an approved proposal and verifies rollback remains honest.

- Observation: positional day/template alignment is an internal builder invariant but an unsafe assumption at an external write boundary.
  Evidence: equal-length lists with shifted template dates previously produced a valid-looking payload for the wrong prescription. Delivery now requires `template.date == daily_plan.date` for every non-rest selected row and fails before provider access otherwise.

## Decision Log

- Decision: use two provider identities with different meanings.
  Rationale: a deterministic UUID v5 `uid` identifies the AI Trainer delivery slot for a date and optional brick leg, so changing TSS still updates the same event. `external_id="ai_trainer:<session_id>"` identifies the exact material prescription used by plan-actual reconciliation. One identifier cannot remain stable across an edit and also identify the edited material.
  Date/Author: 2026-07-14 / Codex

- Decision: delete only events whose `external_id` starts with `ai_trainer:` and whose date is inside the explicit delivery window.
  Rationale: date, name, type, creator athlete, or calendar are insufficient proof of ownership. This fail-closed rule protects IntervalCoach, manual workouts, races, and the old unmanaged AI Trainer event.
  Date/Author: 2026-07-14 / Codex

- Decision: perform one bounded list, one bulk upsert, and at most one bulk delete per delivery request.
  Rationale: this reduces rate-limit usage and lets the provider implement atomic upsert by deterministic `uid`. It also makes concurrency safe: simultaneous retries converge on the same slots rather than racing two create-only calls.
  Date/Author: 2026-07-14 / Codex

- Decision: keep local plan mutation authoritative when provider delivery fails.
  Rationale: recovery approval persists a new checkpoint before external I/O. Marking the proposal failed or rolling back that checkpoint because of a timeout would lie about local state and risk a second plan mutation on retry. The proposal remains terminal and returns a separate retryable delivery result.
  Date/Author: 2026-07-14 / Codex

- Decision: automatically deliver both recovery apply and rollback.
  Rationale: synchronizing only approval leaves the device on the reduced prescription after a successful local rollback. The same affected dates are available from the proposal result and can be delivered idempotently in either direction.
  Date/Author: 2026-07-14 / Codex

- Decision: treat an empty explicit recovery date set as a successful no-op and derive manual delivery windows in the athlete timezone.
  Rationale: a legacy proposal may have no affected-date evidence, which is not a provider failure. Manual seven/fourteen-day windows are local-calendar concepts and must not move at UTC midnight on a VPS.
  Date/Author: 2026-07-14 / Codex

- Decision: require provider-parsed steps for `executable` status.
  Rationale: HTTP success and a WORKOUT category prove only that an event exists. The user value is a workout that Intervals.icu recognizes and can forward to Garmin, so each delivered event must return non-empty `workout_doc.steps`; otherwise the response is `calendar_only` and remains visibly incomplete.
  Date/Author: 2026-07-14 / Codex

- Decision: keep the legacy Streamlit buttons functional but move all new semantics into shared Python.
  Rationale: `api/` plus `web/` is the product surface. Streamlit may continue calling compatibility helpers, but event identity, serialization, sync, and failure behavior must have one source in `services/` and `models/`.
  Date/Author: 2026-07-14 / Codex

## Outcomes & Retrospective

The implementation now delivers the active plan through a bounded, owned-only Intervals.icu write path. Manual web delivery supports seven or fourteen days; recovery approve and rollback synchronize only affected dates after the local append-only checkpoint succeeds. UUID-v5 slots make retries and material edits converge, while `external_id` preserves exact plan-actual identity. Composite bricks become ordered leg events, and legacy checkpoints receive the existing FIT-compatible step fallback instead of calendar-only notes.

Validation before integrating recovery curves was green at `60 passed` for the focused delivery contour, `604 passed, 1 skipped` for contributor-safe smoke, and `647 passed, 6 skipped, 24 deselected` for the broad non-live suite. After merging current `main`, the combined #176 + #168 tree passes `102` focused integration tests, `649 passed, 1 skipped` smoke, and `692 passed, 6 skipped, 24 deselected` broad non-live tests. Python compilation, Next lint, and Next production build pass. Browser acceptance proved two-click idempotency and executable result rendering against a local provider-compatible mock; it did not touch `ai_trainer.db` or the live Intervals calendar.

The remaining acceptance gap is deliberately external: a reversible write to the athlete's real Intervals.icu calendar must confirm that its parser produces non-empty `workout_doc.steps`, preserves all foreign events, and, separately, whether Garmin receives the workout. That live write requires an explicit human gate; until it is run, the PR must not claim verified Garmin delivery.

## Context and Orientation

The active product uses FastAPI routes under `api/` and Next.js pages under `web/`. The shared Intervals.icu adapter is `services/intervals_icu.py`. It authenticates a personal account with Basic auth, lists calendar and execution evidence, and can currently create events. `tests/smoke/test_intervals_icu_service.py` protects that boundary.

The active persisted plan is the latest planning checkpoint in SQLite. `api/planning_service.py::get_active_plan` restores it and applies `models.session_identity.ensure_session_identities`. A session id beginning with `ats_` is a fingerprint of the date, TSS, sport allocation, role, phase, duration, and structured prescription. If an edit changes that material, the new template receives a new session id and records the previous value as `replaces_session_id`. `api/planning_service.py::plan_days` exposes the session, catalog steps, and composite legs to the web Export page.

`models.plan_actual_reconciliation.build_reconciliation` joins completed local activities to Intervals.icu activities and paired workout events. It already recognizes an event whose `external_id` is `ai_trainer:<session_id>` as exact evidence. Delivery must emit that identifier unchanged.

A recovery proposal is stored in `coach_proposals`. `api/routers/decisions.py::approve_proposal` atomically moves a recovery proposal from `pending` to `applying`, calls `api.planning_service.apply_recovery_replan`, and then stores terminal status `approved`. Rollback similarly claims `approved` to `rolling_back`, restores the old checkpoint as a new append-only checkpoint, and stores `rolled_back`. External delivery is a side effect after the local checkpoint is known; it must never be allowed to corrupt those transitions.

The web Planning export tab is `web/app/planning/page.tsx::ExportMode`. It already displays the active plan and download links. It is the manual delivery surface. The Decisions and Today pages reuse the proposal response and do not need a second delivery button for this slice.

An Intervals.icu event has two useful caller-controlled identities. `uid` can be used by the provider's `upsertOnUid=true` mode. AI Trainer will compute a standard UUID v5 from a fixed namespace and slot key `YYYY-MM-DD:single` or `YYYY-MM-DD:leg:<n>`. `external_id` is the material key `ai_trainer:<session_id>` for a single session and `ai_trainer:<session_id>:leg:<n>` for a composite leg. The `ai_trainer:` prefix is also the only ownership marker that authorizes deletion.

An executable workout is a WORKOUT event whose native Intervals.icu description has been parsed into a non-empty `workout_doc.steps` array. Native text expresses one step per line, for example `- Warmup 10m 55-70%`. AI Trainer converts exact `duration_seconds` and materialized power, heart-rate, or pace targets when they exist. For legacy steps, it estimates duration using the same fallback as FIT export and maps stable zone tokens conservatively. Unsupported relative targets remain open/RPE instructions in the text and the delivery result must report whether the provider parsed them.

## Behavioral Specification

Given an active plan with workouts in the next fourteen calendar days, when the athlete confirms delivery from the web Export tab, then the API sends only future non-rest sessions in that bounded range, returns every provider event id and parse status, and the page states how many executable workouts were updated.

Given the same unchanged plan and date range, when delivery is requested twice or concurrently, then the provider contains one AI Trainer event per deterministic slot and both responses refer to the same event ids.

Given an AI Trainer session whose TSS or role changes but whose date and leg slot remain the same, when the range is delivered again, then the same provider event is updated, its `external_id` changes to the new session material id, and the old event is not left beside it.

Given a previously delivered AI Trainer date that is now rest or absent from the selected plan window, when that window is synchronized, then only the old managed AI Trainer event is deleted. An IntervalCoach workout, race, manually created workout, or legacy event without the ownership prefix remains byte-for-byte untouched.

Given a composite brick, when it is delivered, then Intervals.icu receives ordered bike and run events with separate deterministic leg slots and times, while both external ids retain the parent session id. Plan-actual reconciliation accepts paired activities whose event external ids equal either the parent id or one of its leg ids as exact evidence for the same planned session.

Given a provider timeout, HTTP 401, 403, 429, or malformed response, when a recovery proposal has already created its checkpoint, then the proposal remains `approved` and its result contains `delivery.status=failed`, `retryable=true`, and a sanitized error. A later manual delivery converges on the same slots without applying the plan again.

Given a recovery proposal that changes one date, when it is approved, then only the edited date is delivered from the newly active checkpoint. When the same proposal is rolled back, then the same date is delivered from the restored checkpoint.

Given `demo=true` or missing Intervals.icu configuration, when a delivery endpoint is called, then it performs no provider write and returns an explicit non-success response without exposing credentials.

Given a provider event response with no parsed steps, when delivery completes, then the event is reported as `calendar_only`, not `executable`. The feature cannot claim device-ready acceptance until a live event contains parsed steps and appears in Garmin.

## Plan of Work

Milestone 1 establishes the delivery contract and provider identity. First add failing tests to `tests/smoke/test_intervals_icu_service.py` for parameterized HTTP requests, bounded event listing with `uid` and `external_id`, bulk upsert, bulk delete, deterministic payload identity, and sanitized rate-limit errors. Add a new focused file `tests/smoke/test_intervals_plan_delivery.py` that specifies range selection, foreign-event preservation, removed-day cleanup, changed-session upsert, concurrency-safe retries, legacy fallback, composite slots, parsed-step status, and exact-match leg identity. Implement the pure payload and workout text rules in `models/intervals_workout_delivery.py`; keep HTTP in `services/intervals_icu.py`; compose plan plus provider state in `services/intervals_plan_delivery.py`.

Milestone 2 exposes manual delivery through FastAPI and Next.js. Extend `api/routers/planning.py` with an explicit request model and `POST /api/planning/delivery/intervals`. Add a thin `api/planning_service.py` function that restores the latest checkpoint and calls the shared delivery service; it must accept an injected `today` in tests and reject demo mode before provider access. Extend `GET /api/planning/plan` only with local configuration metadata so rendering Export mode does not spend a provider GET. Update `web/lib/types.ts` and `web/app/planning/page.tsx::ExportMode` with a seven/fourteen day selector, one delivery button, disabled/not-configured explanation, busy state, and a result card separating executable, calendar-only, deleted, and failed counts.

Milestone 3 connects the recovery lifecycle. Preserve raw `edited_dates` in `api.planning_service.apply_recovery_replan` result. In `api/routers/decisions.py`, finish the local proposal transition even if delivery fails. After apply, call the delivery service for exactly those dates and persist the sanitized delivery result inside the proposal result. On rollback, reuse the original affected dates after restoring the checkpoint and update the terminal result. Add tests proving provider failure never changes local terminal status, no delivery occurs on stale approval, and retry does not reapply planning.

Milestone 4 validates executable delivery. Build native Intervals.icu workout descriptions from exact catalog steps; use `build_steps_for_sport` only when the checkpoint lacks materialized steps. For a composite template, emit one provider event per leg with ordered local times. Extend reconciliation to accept `ai_trainer:<session_id>:leg:<n>` as exact evidence. In an isolated live acceptance, deliver a narrowly bounded temporary future range, repeat it, read the same event ids back, assert non-empty `workout_doc.steps`, verify all pre-existing foreign event ids are unchanged, and clean up only the temporary `ai_trainer:` external ids. Finally verify whether the executable workout appears in Garmin; if provider parsing succeeds but Garmin sync is not configured or delayed, record that external observation honestly rather than claiming it.

## Concrete Steps

Work from `/private/tmp/ai_trainer_issue168` on branch `codex/issue-168-intervals-delivery`.

Before production implementation, create the contract tests and run:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_intervals_icu_service.py tests/smoke/test_intervals_plan_delivery.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_planning.py -q

The first run must fail because the new delivery module, API route, and adapter methods do not exist. Record the concise failure in `Surprises & Discoveries`, then commit the tests separately.

After each milestone, rerun the same focused contour. After the web milestone, run from `web/`:

    npm run lint
    npm run build

At completion run:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m compileall api models services data
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/ -q

Start an isolated web acceptance on non-default ports so existing local services are not disturbed. Use a copied SQLite database and point the API process to that copy. Open the Export tab, select a bounded range, deliver once, deliver again, and verify the result remains one event per slot. Do not use demo mode for the live provider acceptance.

## Validation and Acceptance

The focused tests must prove all behavioral scenarios above, including HTTP parameter shape and foreign-event preservation. The full smoke and broad non-live suites must remain green. Python compilation, Next lint, and Next production build must succeed.

Manual browser acceptance is successful when `/planning?tab=export` shows configured Intervals.icu delivery, sends the chosen future range with one action, displays executable/calendar-only/deleted/failed counts, and a second click reports the same provider event identities rather than increasing their number.

Provider acceptance is successful when a bounded GET after delivery shows only `external_id` values beginning with `ai_trainer:` for AI Trainer-created events, the original IntervalCoach event ids still exist unchanged, and each supported delivered event returns non-empty `workout_doc.steps`. The acceptance script must capture the provider ids before and after and clean up only the temporary AI Trainer external ids.

After explicit athlete authorization, run the reversible provider probe from the repository root with a near future date:

    python scripts/accept_intervals_delivery_live.py \
      --date YYYY-MM-DD \
      --confirm-live-write CREATE-VERIFY-AND-DELETE-ONE-INTERVALS-EVENT

The runner performs no provider read until the confirmation and future-date guards pass. Its UUID-v5 key uses an acceptance-only namespace input rather than the product's date slot. It refuses a residual probe, upserts the same payload twice, requires the same provider id and parsed steps, compares all foreign rows before and after, and deletes in `finally` only rows matching both the exact acceptance UID and external id.

Recovery acceptance is successful when approving a test proposal creates one new checkpoint and delivers its edited date, rollback creates another append-only checkpoint and restores the provider event, and a simulated provider failure leaves the proposal terminal with a visible retryable delivery error.

Garmin acceptance is successful only when at least one newly delivered executable workout is visible in Garmin. If it is not visible despite parsed `workout_doc`, record the observed provider/Garmin state as an unresolved external integration gap; do not weaken the acceptance wording.

## Idempotence and Recovery

All delivery requests are safe to retry because the provider upserts deterministic slot UIDs. A failed response does not trigger a second local plan mutation. A recovery proposal remains terminal and the athlete retries delivery through the same web action.

Cleanup is fail closed. The implementation lists a bounded date range and deletes only event ids whose external id has the `ai_trainer:` prefix. It never deletes by name, date alone, type, calendar, or creator. The old June AI Trainer event has no managed identity and remains untouched.

If bulk upsert partially succeeds before a network failure, retrying the same payload converges on the same UIDs. If parsing produces `calendar_only`, the event remains visible for diagnosis and can be updated by a later serializer fix using the same slot. If the live acceptance itself fails, remove only event ids returned by that acceptance run or carrying its explicit AI Trainer external ids.

## Artifacts and Notes

The official API evidence used by this plan is:

    POST /api/v1/athlete/{id}/events/bulk?upsertOnUid=true
    PUT  /api/v1/athlete/{id}/events/bulk-delete

The live IntervalCoach example that proves executable native text has this shape:

    Main Set
    - Race Pace 1 9m 87-95% 90rpm
    - Recovery 5m 55% 80rpm

Its provider response contains `workout_doc.steps` with exact durations and percent-FTP targets. Do not copy its personalized prose or provider ids into product fixtures.

## Interfaces and Dependencies

Do not add a new dependency. Continue using the Python standard library HTTP adapter in `services/intervals_icu.py` and the existing Next/SWR stack.

In `services/intervals_icu.py`, extend `IntervalsICUClient` with bounded methods equivalent to:

    list_workout_events(oldest: date, newest: date) -> list[dict[str, Any]]
    upsert_events_by_uid(payloads: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]
    delete_events(payloads: Iterable[Mapping[str, Any]]) -> int

`list_workout_events` must retain `uid`, `external_id`, `workout_doc`, and the existing reconciliation fields. Bulk methods must use the official endpoints and query parameters and must return normalized provider evidence without credentials.

In `models/intervals_workout_delivery.py`, provide pure functions equivalent to:

    delivery_slot_uid(session_date: str, leg_index: int | None = None) -> str
    build_delivery_events(goal_plan: Mapping[str, Any], dates: Sequence[str]) -> list[dict[str, Any]]
    build_intervals_workout_description(steps: Sequence[Mapping[str, Any]], ...) -> str
    provider_event_is_owned(event: Mapping[str, Any]) -> bool
    provider_event_is_executable(event: Mapping[str, Any]) -> bool

The slot UID must be deterministic UUID v5. Every payload must include category, local date/time, name, type, load, moving time, uid, external id, and native description. Single sessions use the parent session id; composite legs append `:leg:<n>`.

V1 has no persisted per-session start-time preference. Delivery therefore uses 07:00 athlete-local for the first event and a fixed five-minute gap between composite brick legs. These are explicit export defaults, not inferred coaching recommendations; changing them requires a separate scheduling contract rather than silent serializer heuristics.

In `services/intervals_plan_delivery.py`, expose one orchestration result equivalent to:

    deliver_active_plan(
        db: Database,
        *,
        days: int | None = None,
        dates: Sequence[str] | None = None,
        today: date | None = None,
        source: str,
    ) -> dict[str, Any]

Exactly one of `days` or `dates` is accepted. The result includes status, source, checkpoint id, window/dates, created-or-updated provider ids, executable count, calendar-only count, deleted count, failed count, retryable flag, and sanitized error. It does not expose the API key or authorization header.

In `api/routers/planning.py`, add:

    POST /api/planning/delivery/intervals
    body: {"days": 7 | 14}
    response: IntervalsDeliveryResult

The route rejects `demo=true` before calling the provider. `GET /api/planning/plan` may add local `delivery` configuration metadata but must not make a remote request.

Recovery proposal responses retain their current `proposal` and `result` keys. For recovery apply and rollback, `result` gains `affected_dates` and `delivery`. Existing clients that ignore those fields remain compatible.

Revision note (2026-07-14, Codex): initial ExecPlan created after source, official API, and live read-only audit. It intentionally includes the executable-device milestone because a calendar-only HTTP success does not satisfy the user problem recorded in issue #168. Updated after contract-first RED, backend/API/recovery GREEN, full local validation, two-click browser acceptance, integration with #176, and the fail-closed live-runner contract; the remaining real-provider/Garmin observation stays explicit rather than being inferred from mocks.
