Add trigger-aware targeted recovery-episode refresh so late match/feedback evidence for sessions older than the 12-week sync horizon is not silently dropped (Issue #195)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained according to `.agent/PLANS.md`, which is checked into this repository at that path and defines the required format and living-document discipline for ExecPlans in AI Trainer. It also incorporates by reference `docs/reconciliation_service_execplan.md` (Issue #194, already completed on `main`), which moved `reconciliation_at` — the pure, read-only function that compares a saved training plan against recorded activities and returns a dictionary of matched/unmatched sessions (the "reconciliation payload") — out of `api/planning_service.py` into `services/reconciliation.py`. Everything below assumes that move already happened; `services/recovery_analytics.py` already imports `reconciliation_at` from `services.reconciliation`, not from `api`.

## Purpose / Big Picture

"Recovery episodes" are rows in the `recovery_episodes` SQLite table, one durable, append-only, immutable record per (planned training session, revision), built by `services/recovery_analytics.py::refresh_recovery_episodes`. Each episode pairs a planned session with what actually happened (an activity the athlete recorded, matched either automatically or by explicit user/coach confirmation) and with the athlete's readiness ("recovery") snapshots for the day of the session and the three days after, so the system can later ask "how did this athlete's readiness respond after this kind of session." This materialization only ever happens for sessions the local evidence proves were both planned and actually completed and matched — it never talks to a live provider.

Today, every time new evidence arrives (a Garmin sync completes, the athlete confirms which activity matches a planned session, the athlete submits or edits post-workout feedback), the system calls `refresh_recovery_episodes`, which re-derives episodes for a rolling window capped at 12 weeks ending "today". This cap exists so a routine post-sync refresh — which runs unattended after every sync — stays cheap: it never has to reconcile an athlete's entire multi-year training history. But this same cap has a side effect the cap's author did not intend: if an athlete confirms a match, corrects feedback, or removes ("tombstones") feedback for a session that happened *more than 12 weeks ago*, that correction is saved permanently to its own append-only table (`plan_actual_matches` or `session_feedback` — those tables have no cap), but `refresh_recovery_episodes`'s 12-week window silently never looks back far enough to notice the change, so the derived `recovery_episodes` row for that old session is never updated. The append-only source-of-truth history is intact, but the read-optimized "recovery episode" projection built from it can quietly go stale forever. This was flagged as issue #195, itself a follow-up from PR #187's review.

After this change, two things happen. First, nothing changes about the routine, unattended, "just finished a sync" refresh: it still uses the same rolling 12-week window ending today, so its cost and behavior for an athlete syncing every day are identical to before this change — this is what the issue calls "option 2, the ordinary post-sync refresh remains bounded." Second, whenever the athlete (or an admin, via the admin-resolve bridge) explicitly confirms/rejects a plan-vs-actual match, or submits/corrects/removes feedback for a specific planned session, that exact session's `session_id` (the content-derived stable identity assigned to every planned session by `models/session_identity.py::ensure_session_identities`) is now passed through to a new, narrowly-scoped "targeted" refresh path. That path resolves the session's own date from the currently active plan, and does one small, bounded reconciliation probe anchored on that specific date (not on "today", and not a 12-week window) — so it can materialize (or refresh) that one session's recovery episode even if the session happened a year ago, without reconciling the athlete's entire history to do it.

You can see this working two ways. First, `python -m pytest tests/smoke/test_recovery_episode_refresh_horizon.py -q` exercises the new behavior end-to-end against real temporary SQLite fixtures with frozen dates: it plants a matched, feedback-covered training session more than 12 weeks in the past, shows that an ordinary bounded-sync refresh does not touch it, then shows that calling `refresh_recovery_episodes(db, target_session_ids=[old_session_id])` (or, more realistically, calling `api.planning_service.record_plan_actual_match` or one of the `api.session_feedback` functions for that old session) does materialize exactly one new recovery-episode revision for it — and that repeating the same call with unchanged evidence creates zero new revisions (idempotence), while a later correction creates exactly one more. Second, you can watch this manually: start a Python REPL from the repository root with `PYTHONPATH=.` set (or just `python3` from the repo root, since it already resolves top-level packages), create a temporary `Database` instance, save a planning checkpoint whose one session is dated more than 84 days before some "as_of" date, save a matching activity and a `plan_actual_matches` row confirming it, save four `readiness_snapshots` rows (session day + 3 days after) so the recovery outcome has evidence to compute, then call `services.recovery_analytics.refresh_recovery_episodes(db, as_of=<that far-future as_of>)` (the ordinary bounded call) and observe `created == 0` and `reason` absent because the session is outside the 12-week window entirely — then call `services.recovery_analytics.refresh_recovery_episodes(db, as_of=<that far-future as_of>, target_session_ids=[<the session_id>])` and observe `created == 1` and `db.get_recovery_episodes(latest_only=True)` now contains a row for that session.

## Progress

- [x] (2026-07-18) Read `AGENTS.md`, `.agent/PLANS.md`, Issue #195, and `docs/reconciliation_service_execplan.md` (the completed #194 extraction this plan builds on).
- [x] (2026-07-18) Surveyed `services/recovery_analytics.py::refresh_recovery_episodes`/`refresh_recovery_episodes_best_effort`/`record_post_sync_recovery_state`, `services/reconciliation.py::reconciliation_at`, the two production call sites (`api/planning_service.py::record_plan_actual_match`, `api/session_feedback.py::_append_feedback` — which is the single shared append path for `submit_session_feedback`, `correct_session_feedback`, `tombstone_session_feedback`, and `resolve_prediction_via_feedback`/admin-resolve), and the relevant `data/database.py` read helpers (`get_readiness_snapshots`, `get_latest_session_feedback` (singular, by session_id, no date window), `get_latest_session_feedbacks` (plural, filtered by feedback *submission* date, not session date), `get_latest_plan_actual_matches` (filtered by the match's `session_date` column), `get_activities_between`, `get_coach_constraints`, `save_recovery_episode` (returns `{"episode": {...}, "created": bool}`, not a top-level `id`)).
- [x] (2026-07-18) Created this ExecPlan.
- [ ] Write the RED contract: a new `tests/smoke/test_recovery_episode_refresh_horizon.py` covering acceptance gates 1–7 and 9 from the issue's trigger comment, plus an update to the one existing test that monkeypatches `refresh_recovery_episodes_best_effort`'s call signature (`tests/smoke/test_api_planning.py::test_user_match_correction_appends_ledger_and_changes_reconciliation`) so it asserts the new `target_session_ids` argument (gate 8, match side). Commit RED separately before any production file changes.
- [ ] Implement GREEN in `services/recovery_analytics.py`: add `target_session_ids` to `refresh_recovery_episodes`/`refresh_recovery_episodes_best_effort`; extract the existing per-row materialization body into a shared helper; add the new targeted-scope function.
- [ ] Wire `api/planning_service.py::record_plan_actual_match` and `api/session_feedback.py::_append_feedback` to pass `target_session_ids=[session_id]`.
- [ ] Run the new focused tests, the existing recovery/feedback/planning/identity-handoff suites, the full smoke suite, and the broader non-live suite; record exact pass counts below.
- [ ] Push the branch (no new branch created — see Decision Log) and open a draft PR with `Closes #195`.

## Surprises & Discoveries

- Observation: `data/database.py::get_latest_session_feedbacks` (plural) filters by `substr(sf.submitted_at, 1, 10)`, i.e. the timestamp the feedback was *submitted*, not the planned session's own date. The existing bulk `refresh_recovery_episodes` loop calls it once with `start_date=earliest snapshot date, end_date=resolved_as_of` — a window that works for the bulk case because "submitted" and "session date" are usually close together for sessions inside the rolling window. For a *targeted* refresh of an old session, a late correction could be submitted today for a session that happened months ago, so any date-bounded call to the plural getter would need to span from the session's date to "today" — arbitrarily wide for old sessions, defeating the "small window" requirement. `data/database.py::get_latest_session_feedback` (singular, by `session_id`, no date filter at all) is the correct primitive for the targeted path: it is an indexed point lookup, not a range scan, and it is unaffected by how late the feedback arrived.
  Evidence: `data/database.py:1994-2035`.
- Observation: `data/database.py::save_recovery_episode` returns `{"episode": {...full row incl. "id"...}, "created": bool}`, not a flat dict with a top-level `"id"`. The existing bulk loop only reads `saved.get("created")` and never the id, so this was easy to miss when designing the targeted path's per-target `episode_id` observability field — it must read `saved["episode"]["id"]`, not `saved["id"]`.
  Evidence: `data/database.py:998-1069`.
- Observation: `data/database.py::get_latest_plan_actual_matches` filters by the match row's own `session_date` column (the *planned* session's date, fixed at save time), not by when the match was confirmed — unlike the feedback plural getter. So a single-day window (`start_date=end_date=session_date`) is sufficient and correct for the targeted path's match lookup, with no "late confirmation" problem to work around.
  Evidence: `data/database.py:1810-1830` (`WHERE session_date BETWEEN ? AND ?`).
- Observation: `tests/smoke/test_recovery_transfer_identity_handoff.py` documents that `session_templates` entries can have a nested `sessions: [...]` list for multi-session days (Issue #205/#206/#209 lineage), where each nested session has its own content-derived `session_id` independent of the day-level template's own top-level `session_id`. The *existing* bulk `refresh_recovery_episodes` already only indexes templates by the day-level top-level `item.get("session_id")` (`templates = {str(item.get("session_id")): dict(item) for item in plan.get("session_templates", []) ...}`), i.e. it does not resolve nested per-session identities either. This plan's targeted-refresh session-id-to-date resolution intentionally mirrors that exact same (already-existing, already-scoped-elsewhere) limitation rather than trying to fix nested-day identity resolution, which is out of scope for #195 and tracked by the #205/#206/#209 lineage instead.
  Evidence: `tests/smoke/test_recovery_transfer_identity_handoff.py:1-24`; `services/recovery_analytics.py:142-146` (pre-change).
- Observation: the admin-resolve bridge (`api/session_feedback.py::resolve_prediction_via_feedback`) creates its `plan_actual_matches` row directly via `_admin_match_evidence`/`db.save_plan_actual_match` — it does **not** call `refresh_recovery_episodes_best_effort` itself for the match half. The only refresh call in that whole flow comes from the trailing `_append_feedback(...)` call inside the same function. This means routing `target_session_ids` through `_append_feedback`'s existing single call site automatically satisfies gate 9 ("admin resolve does not double-create an episode revision") without any special-casing — there was never a second refresh call to begin with.
  Evidence: `api/session_feedback.py:518-663` (`_admin_match_evidence` builds and saves the match with no refresh call; `resolve_prediction_via_feedback` calls `_append_feedback` once at line 648).
- Observation: exactly one existing test in the repository monkeypatches `refresh_recovery_episodes_best_effort` by module attribute with a hard-coded keyword-only signature (`lambda _db, *, as_of=None: ...`): `tests/smoke/test_api_planning.py::test_user_match_correction_appends_ledger_and_changes_reconciliation`. Adding `target_session_ids` as a keyword argument to the real call site in `record_plan_actual_match` would make this test's monkeypatch raise `TypeError: unexpected keyword argument 'target_session_ids'` the moment `record_plan_actual_match` calls it — this test must be updated as a direct, minimal consequence of wiring the call site, mirroring the same "update the one white-box test that hard-codes a signature" pattern `docs/reconciliation_service_execplan.md` recorded for issue #194.
  Evidence: `tests/smoke/test_api_planning.py:609-646`.

## Decision Log

- Decision: work directly on the already-checked-out branch `claude/issue-195-20260718-1638` (which is even with `origin/main@abdfd18`) instead of creating a new `claude/issue-195-recovery-refresh` branch in an isolated worktree, as the trigger comment requested.
  Rationale: this task is running inside the `claude-code-action` GitHub Actions harness, whose own operating instructions explicitly state "You are already on the correct branch ... Never create new branches when triggered on issues or closed/merged PRs," and only allow pushing to that exact branch. Those harness-level constraints take precedence over the trigger comment's generic process instructions, since the harness is what actually authenticates and pushes on this job's behalf. The RED-then-GREEN separate-commit discipline the trigger comment asks for is preserved regardless of which branch/worktree hosts it.
  Date/Author: 2026-07-18, Claude.
- Decision: the additive parameter is named `target_session_ids` (plural, a sequence) on both `refresh_recovery_episodes` and `refresh_recovery_episodes_best_effort`, defaulting to `None`. Presence of a non-empty sequence selects "targeted" scope; absence (`None` or empty) preserves today's "bounded_sync" scope and behavior byte-for-byte.
  Rationale: this is exactly the interface the trigger comment asks for ("Prefer an additive API such as `target_session_ids`"), and plural-with-list matches the shape every call site naturally has (a single affected `session_id` wrapped in a one-element list) while also supporting the "multiple valid targets" and "duplicate target ids" acceptance gates without a second function signature.
  Date/Author: 2026-07-18, Claude.
- Decision: refactor the existing per-row episode-materialization body (the ~130-line loop interior in `refresh_recovery_episodes` that computes `stimulus_family`, `reasons`/exclusions, pre/d1/d2/d3 readiness anchors, and calls `db.save_recovery_episode`) into a private helper, `_materialize_matched_row`, shared verbatim by both the bounded-sync loop and the new targeted path.
  Rationale: the issue explicitly forbids "a second matcher" or copying reconciliation/materialization logic; extracting a shared helper (rather than writing a second, subtly-different materialization body for the targeted path) is the only way to guarantee the two scopes produce byte-identical episode content for the same evidence, and it keeps the fingerprint/idempotence contract in exactly one place.
  Date/Author: 2026-07-18, Claude.
- Decision: the targeted path's bounded reconciliation probe uses `weeks=1` and `as_of=<the resolved session_date>` (not the caller's `as_of`/"today"), so `services.reconciliation.reconciliation_at`'s own window (`[as_of - 6 days, as_of]`) always includes the target date at its right edge, regardless of how old the session is.
  Rationale: this is the smallest possible bounded window that is guaranteed, by construction, to contain the target session's date — satisfying the issue's "anchored on that session date," "small window," "never an all-history scan" requirements simultaneously. A larger `weeks` value would not improve correctness (the target date is already guaranteed present) and would only widen the reconciliation cost for no benefit.
  Date/Author: 2026-07-18, Claude.
- Decision: within the targeted path, per-target auxiliary reads use different windows chosen per the actual filter semantics of each read, not one shared window: activities use `[session_date, session_date + 3 days]` (matches what `select_daily_anchor` needs for pre/d1/d2/d3); matches use `[session_date, session_date]` (the match row's `session_date` column is the fixed planned date); feedback uses the singular `get_latest_session_feedback(session_id)` primitive with no date filter at all (feedback *submission* date is unrelated to session date and can be arbitrarily later for exactly the late-correction scenario this issue exists to fix).
  Rationale: see the "Surprises & Discoveries" entries on `get_latest_session_feedbacks` vs `get_latest_session_feedback` and on the match getter's date semantics above — using one shared window for all three reads would either miss late feedback (if narrow) or silently stop being "small" (if widened to cover "session date to today" for an old session).
  Date/Author: 2026-07-18, Claude.
- Decision: unknown/absent session identity and "target date after `as_of`" both fail closed per-target with a machine-readable `reason` code (`session_not_found_in_active_checkpoint`, `target_date_after_as_of`, `session_not_in_reconciliation_window`) inside a `processed` list entry with `status: "not_found"`; they never raise, and they never fall back to widening the probe or invoking the bounded-sync scope.
  Rationale: explicit issue requirement ("must not fall back to an unbounded refresh"); using a status/reason field (rather than raising) keeps `refresh_recovery_episodes_best_effort`'s existing best-effort/never-raise contract intact for callers, and keeps multi-target calls able to report a mix of successes and failures in one response instead of failing the whole batch on one bad id.
  Date/Author: 2026-07-18, Claude.
- Decision: duplicate target ids are deduplicated by first occurrence before any resolution/processing happens, and the single per-distinct-date reconciliation probe is cached and reused across every target that resolves to the same date — but per-target `processed` entries are still emitted in that same first-occurrence order (not grouped/reordered by date).
  Rationale: satisfies gate 5 ("stable result ordering" together with "one reconciliation/materialization per distinct target/date") without the caller having to reconstruct original request order from a date-grouped response.
  Date/Author: 2026-07-18, Claude.
- Decision: `record_post_sync_recovery_state` (the post-sync entry point) is left calling `refresh_recovery_episodes` with no `target_session_ids` at all — zero code change to that call site.
  Rationale: explicit issue/task requirement that ordinary post-sync refresh remains bounded and untouched.
  Date/Author: 2026-07-18, Claude.

## Outcomes & Retrospective

Pending GREEN implementation and validation; this section will be completed once the full validation command set has run.

## Context and Orientation

`services/recovery_analytics.py` is a "services" module: per `AGENTS.md`'s architecture rules (also enforced by the automated `tests/smoke/test_api_architecture.py::test_services_modules_do_not_depend_on_api` guard from #194), it may depend on `data/`, `models/`, and other `services/` modules, but never on `api/`. It already imports `reconciliation_at` from `services/reconciliation.py` (not `api/planning_service.py` — that dependency inversion was fixed by #194). This plan does not change that import.

The three functions this plan touches inside `services/recovery_analytics.py`:

`refresh_recovery_episodes(db, *, as_of=None, capture_mode="prospective")` — the one function that actually writes `recovery_episodes` rows. Computes a `weeks = min(12, ...)` lookback from the earliest available readiness snapshot up to `as_of` (defaulting to today), calls `reconciliation_at(db, weeks=weeks, as_of=as_of, include_provider=False)`, and for every reconciliation row that is `match_status == "matched"` with at least one `actual_activity_id`, builds a frozen evidence dict, fingerprints it (SHA-256 of canonical JSON), and calls `db.save_recovery_episode(...)`, which is a no-op (returns `created: False`) if that exact fingerprint was already saved, or appends a new revision otherwise.

`refresh_recovery_episodes_best_effort(db, *, as_of=None)` — a thin wrapper that calls the above inside a `try/except`, turning any exception into `{"created": 0, "error": str(exc)}` instead of raising, because callers use this from user-facing request handlers (a match confirmation, a feedback submission) where a derived-analytics failure must never block the primary write that already succeeded.

`record_post_sync_recovery_state(db, *, capture_run_id, observed_at_utc=None, capture_mode="prospective")` — called once per Garmin sync run; saves one readiness snapshot, then calls `refresh_recovery_episodes` (not the best-effort wrapper — it catches its own exception locally) with no target sessions. This is the "ordinary post-sync refresh" the issue says must stay bounded and untouched.

The two production call sites this plan wires:

`api/planning_service.py::record_plan_actual_match(db, *, base_checkpoint_id, session_id, activity_ids, actual_role, action)` (`api/planning_service.py:1000-1081`) — called when the athlete explicitly confirms or rejects (both branches share this one function; `action` is `"confirm"` or `"reject"`) which recorded activity matches a specific planned session. It validates the request, saves a new `plan_actual_matches` row via `db.save_plan_actual_match`, then (line 1078-1080, currently) calls `refresh_recovery_episodes_best_effort(db, as_of=date.today())` with no session targeting at all — today, if `session_id` refers to a session more than 12 weeks old, this call silently does nothing for it.

`api/session_feedback.py::_append_feedback(db, payload, *, evidence, now_utc, source, supersedes_feedback_id=None, status="active")` (`api/session_feedback.py:199-263`) — the single shared low-level "save one feedback revision" function. It is called by `submit_session_feedback` (first feedback for a session), `correct_session_feedback` (a revision superseding a prior one), `tombstone_session_feedback` (marks a revision `status="tombstone"`, effectively "removed"), and `resolve_prediction_via_feedback` (the admin-resolve bridge — see the Surprises entry above: it saves its own match row separately via `_admin_match_evidence` before calling this function, so this is still the *only* refresh call in that whole flow). It saves the feedback row via `db.save_session_feedback`, evaluates any pending quality-forecast predictions, then (line 260-262, currently) calls `refresh_recovery_episodes_best_effort(db, as_of=now_utc.date())`, again with no targeting — every one of the four callers above funnels through this single call site, so wiring it once wires all four.

Both call sites already know the exact `session_id` they just wrote evidence for (`session_id` is a parameter of `record_plan_actual_match`; inside `_append_feedback`, `session_id = str(row.get("session_id") or payload.get("session_id") or "").strip()` is computed near the top of the function, before the refresh call).

`data/database.py::Database` is a thin synchronous SQLite wrapper (each method opens its own `sqlite3.connect`, does its work, and closes the connection — there is no shared connection/session object to thread through). The read helpers this plan's targeted path uses, with their exact filter semantics (already covered above in Surprises & Discoveries, repeated here for completeness since this section must be self-contained): `get_latest_planning_checkpoint()` (no args, most recent checkpoint or `None`), `get_readiness_snapshots(*, capture_mode=None, local_date=None)` (no date-range filtering — every snapshot ever saved for that capture mode, which is intentional: `select_daily_anchor` needs the full history to find "the latest eligible snapshot on this specific local date" for whatever date it's asked about, old or new), `get_latest_session_feedback(session_id)` (singular, indexed point lookup, no date filter), `get_latest_plan_actual_matches(*, start_date, end_date)` (filtered by the match's own fixed `session_date` column), `get_activities_between(start_date, end_date)` (filtered by the activity's own `date` column), `get_coach_constraints(start_date=None, end_date=None, active_only=True, limit=100)` (used to detect "sick/travel/injury" exclusion reasons for a given date), and `save_recovery_episode(payload)` (returns `{"episode": {...row incl. "id"...}, "created": bool}`; idempotent by `fingerprint`).

## Plan of Work

1. In `services/recovery_analytics.py`, add `from typing import Any, Sequence` (currently only `Any` is imported from `typing`).

2. Extract the existing per-row body of the `for row in reconciliation.get("rows") or []:` loop inside `refresh_recovery_episodes` (everything from the `match_status`/`actual_activity_ids` check through the `saved = db.save_recovery_episode({...})` call, i.e. today's lines ~172-302) into a new private function:

       def _materialize_matched_row(
           db: Database,
           row: dict[str, Any],
           *,
           checkpoint: dict[str, Any] | None,
           templates: dict[str, dict[str, Any]],
           snapshots: list[dict[str, Any]],
           activities: list[dict[str, Any]],
           matches: dict[str, dict[str, Any]],
           feedbacks: dict[str, dict[str, Any]],
           exclusion_by_date: dict[str, list[str]],
           capture_mode: str,
           resolved_as_of: date,
       ) -> dict[str, Any] | None:

   It returns `None` immediately (no DB write) if `row.get("match_status") != "matched"` or there is no `row.get("actual_activity_ids")` — exactly today's skip condition — otherwise it does exactly what today's loop body does (unchanged logic, only renamed local variables where needed for parameter names) and returns the full dict `db.save_recovery_episode(...)` produced (`{"episode": {...}, "created": bool}`).

3. Rename the existing top-level `refresh_recovery_episodes` function to `_refresh_bounded_sync_episodes` (identical signature, `db, *, as_of=None, capture_mode="prospective"`), and change its loop to call the new helper:

       for row in reconciliation.get("rows") or []:
           session_date = date.fromisoformat(str(row.get("date"))[:10])
           if session_date < earliest or session_date > resolved_as_of:
               continue
           saved = _materialize_matched_row(
               db, row, checkpoint=checkpoint, templates=templates, snapshots=snapshots,
               activities=activities, matches=matches, feedbacks=feedbacks,
               exclusion_by_date=exclusion_by_date, capture_mode=capture_mode,
               resolved_as_of=resolved_as_of,
           )
           if saved is None:
               continue
           considered += 1
           created += int(bool(saved.get("created")))

   Add `"scope": "bounded_sync"` to all three of this function's `return` dicts (the `no_readiness_snapshots` early return, the `no_plan` early return, and the final return) — additive only, no existing key removed or renamed.

4. Add a new private function `_refresh_targeted_episodes(db, *, as_of, capture_mode, target_session_ids)` implementing exactly the algorithm described in Context and Orientation / Decision Log above: dedupe `target_session_ids` by first occurrence into `ordered_ids`; resolve the active checkpoint once and build the same `templates` dict the bounded path builds (`{str(item.get("session_id")): dict(item) for item in plan.get("session_templates", []) or [] if item.get("session_id")}`); fetch `snapshots = db.get_readiness_snapshots(capture_mode=capture_mode)` and the full (unfiltered by date, `active_only=False`) `coach_constraints`/`exclusion_by_date` map once, since both are needed regardless of how many targets there are; then, for each id in `ordered_ids`, in order: resolve its `session_date` from `templates` (fail closed with `reason="session_not_found_in_active_checkpoint"` if the id is missing or has no parseable `date`); check `session_date > resolved_as_of` (fail closed with `reason="target_date_after_as_of"`); look up (with a per-date cache keyed by `session_date.isoformat()`, so two targets sharing a date reuse one probe) `reconciliation_at(db, weeks=1, as_of=session_date, include_provider=False)`, a `[session_date, session_date] `-windowed `get_latest_plan_actual_matches` dict keyed by `target_key`, and a `[session_date, session_date + 3 days]`-windowed `get_activities_between` list; find the row in that reconciliation payload whose `session_id` matches (fail closed with `reason="session_not_in_reconciliation_window"` if absent or `has_plan` is false); look up `feedback = db.get_latest_session_feedback(session_id) or {}` (no cache needed — already a single indexed point lookup) and wrap it as the one-entry `feedbacks` map `_materialize_matched_row` expects; call `_materialize_matched_row(...)`; if it returns `None`, append `{"session_id": ..., "status": "not_matched"}`; otherwise append `{"session_id": ..., "status": "created" if saved["created"] else "unchanged", "episode_id": saved["episode"]["id"]}` and increment a running `created` counter. Return:

       {
           "scope": "targeted",
           "as_of": resolved_as_of.isoformat(),
           "capture_mode": capture_mode,
           "requested_session_ids": ordered_ids,
           "processed": processed,
           "not_found": [item["session_id"] for item in processed if item["status"] == "not_found"],
           "created": created,
           "episodes": len(db.get_recovery_episodes(latest_only=True, capture_mode=capture_mode)),
       }

5. Change the public `refresh_recovery_episodes` into a two-line dispatcher:

       def refresh_recovery_episodes(
           db: Database,
           *,
           as_of: date | None = None,
           capture_mode: str = "prospective",
           target_session_ids: Sequence[str] | None = None,
       ) -> dict[str, Any]:
           if target_session_ids:
               return _refresh_targeted_episodes(
                   db, as_of=as_of, capture_mode=capture_mode, target_session_ids=target_session_ids
               )
           return _refresh_bounded_sync_episodes(db, as_of=as_of, capture_mode=capture_mode)

   Add the same `target_session_ids: Sequence[str] | None = None` parameter to `refresh_recovery_episodes_best_effort`, passed straight through to `refresh_recovery_episodes` inside its existing `try/except`.

6. In `api/planning_service.py::record_plan_actual_match` (around line 1078-1080), change the call to `refresh_recovery_episodes_best_effort(db, as_of=date.today(), target_session_ids=[session_id])`.

7. In `api/session_feedback.py::_append_feedback` (around line 260-262), change the call to `refresh_recovery_episodes_best_effort(db, as_of=now_utc.date(), target_session_ids=[session_id])`.

8. Update `tests/smoke/test_api_planning.py::test_user_match_correction_appends_ledger_and_changes_reconciliation`'s monkeypatch (line ~617-621) from `lambda _db, *, as_of=None: refresh_calls.append(as_of) or {"created": 0}` to a signature that also accepts and records `target_session_ids`, and strengthen the existing `assert refresh_calls == [date.today()]` assertion to also check the recorded `target_session_ids` equals `[target["session_id"]]`.

## Concrete Steps

All commands run from the repository root, `/home/runner/work/ai_trainer/ai_trainer`, using the already-available `python3 -m pytest` (verified working; no separate virtualenv activation was needed in this environment).

RED (test-only) commit — before any production file changes:

    python3 -m pytest tests/smoke/test_recovery_episode_refresh_horizon.py -q

Expected RED output: the new test module fails to collect or its individual tests fail with `TypeError: refresh_recovery_episodes() got an unexpected keyword argument 'target_session_ids'` (the parameter does not exist yet).

    git add tests/smoke/test_recovery_episode_refresh_horizon.py docs/recovery_episode_refresh_execplan.md
    git commit -m "test: RED contract for targeted recovery-episode refresh (#195)"

GREEN commit — after applying the Plan of Work above:

    python3 -m pytest tests/smoke/test_recovery_episode_refresh_horizon.py -q
    python3 -m pytest tests/smoke/test_recovery_episode_materializer.py tests/smoke/test_recovery_analytics.py tests/smoke/test_post_workout_feedback.py tests/smoke/test_feedback_planning_handoff.py tests/smoke/test_recovery_response.py tests/smoke/test_recovery_transfer_identity_handoff.py tests/smoke/test_api_planning.py tests/smoke/test_recovery_replan_loop.py -q
    python3 -m pytest tests/smoke -q
    python3 -m pytest -m "not live and not debug" tests/ -q
    git diff --check

Expected GREEN output: all of the above pass; the full smoke suite is expected to match or exceed the pre-change baseline of `844 passed` recorded in this repository's environment during this task (see Progress).

    git add services/recovery_analytics.py api/planning_service.py api/session_feedback.py tests/smoke/test_api_planning.py docs/recovery_episode_refresh_execplan.md
    git commit -m "feat: targeted recovery-episode refresh for old-session match/feedback evidence (#195)"

## Validation and Acceptance

Behavior for the ordinary, unattended post-sync path is unchanged and observable the same way it always was: `record_post_sync_recovery_state(db, capture_run_id=..., observed_at_utc=...)` still triggers a `refresh_recovery_episodes` call with no `target_session_ids`, still bounded to `weeks = min(12, ...)`, still ending at "today." The new behavior is observable via `refresh_recovery_episodes(db, as_of=<date>, target_session_ids=[<session_id>])` (or transitively via `record_plan_actual_match`/`submit_session_feedback`/`correct_session_feedback`/`tombstone_session_feedback`/`resolve_prediction_via_feedback` for a session whose planned date is more than 12 weeks before `as_of`): it returns `scope: "targeted"`, `created: 1` the first time real matched evidence exists for that session, `created: 0` on an identical retry, and a `processed` entry with `status: "not_found"` and a machine-readable `reason` for an unknown/absent/future-dated session id — with no reconciliation call in that path ever using `weeks` greater than 1 or `as_of` other than the resolved target date.

The full required validation command set (Concrete Steps) must all pass, with the smoke suite pass count at or above the documented baseline (`844 passed`).

## Idempotence and Recovery

Every step is a plain file edit or an additive new file — nothing destructive, nothing that touches a live database or external service; all new/changed tests use `tmp_path`-backed temporary SQLite files. `_materialize_matched_row`/`db.save_recovery_episode` are already idempotent by fingerprint, so re-running any targeted or bounded refresh with unchanged evidence is always safe and a no-op. If a step is interrupted partway, `git status` shows exactly which files were touched; re-running the same edits is safe because they are simple, non-accumulating replacements. If the GREEN implementation breaks something unexpected, `git revert` of the GREEN commit alone restores the pre-change behavior while keeping the RED tests in history as documentation of the target contract.

## Artifacts and Notes

To be filled in with exact validation transcripts once GREEN lands.

## Interfaces and Dependencies

In `services/recovery_analytics.py`, this plan changes the public surface to:

    def refresh_recovery_episodes(
        db: Database,
        *,
        as_of: date | None = None,
        capture_mode: str = "prospective",
        target_session_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]: ...

    def refresh_recovery_episodes_best_effort(
        db: Database,
        *,
        as_of: date | None = None,
        target_session_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]: ...

Both are additive-only changes (new optional keyword parameter; existing positional/keyword call shape and existing return keys are preserved exactly). `record_post_sync_recovery_state` is unchanged. `api.planning_service.record_plan_actual_match` and `api.session_feedback._append_feedback` (and therefore `submit_session_feedback`, `correct_session_feedback`, `tombstone_session_feedback`, `resolve_prediction_via_feedback`) each gain exactly one keyword argument (`target_session_ids=[session_id]`) on their existing `refresh_recovery_episodes_best_effort` call. No new third-party dependencies. Depends only on already-existing `data.database.Database` methods and `services.reconciliation.reconciliation_at` (unchanged, from #194).
