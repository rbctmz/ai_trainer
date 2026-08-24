# Slice Spec And Review Template

This is the Class A slice spec for issue `#502` and is linked from
`docs/activity_tss_reconciliation_execplan.md`. It records the RED milestone
and the completed local M2 GREEN implementation; publication remains a separate
delivery gate.

- Issue / PR: [#502 — Make FTP provenance deterministic across date boundaries](https://github.com/rbctmz/ai_trainer/issues/502); PR: TBD
- Author / checker / merge owner: Luna / independent Codex checker / root agent
- Date: 2026-08-24
- Candidate head: branch `codex/issue-502-ftp-date-boundary`; base SHA `79ff81044e731003a6af587056ee213f24ea0a78`; commit SHA pending publication

## Change Class

- Class: **A**
- Rationale: historical FTP/TSS provenance affects persisted correctness; the work crosses the SQLite data layer, activity repair, and the shadow bike HR-pair service. The issue also has an identity/provenance automatic-escalation trigger and explicitly requires deterministic timezone evidence before implementation.
- Automatic escalation triggers checked: identity/provenance — yes; persistence semantics — yes; data migration — no new migration; live-provider write — no; security/secret — no; irreversible action — no; new external API contract — no.
- Review budget used: 1 / 2 rounds

## Scope

- Behavior that changes: deterministic smoke coverage plus the minimal compatibility-preserving production resolver. Tests hold absolute activity/profile instants constant while representing the activity as UTC and Europe/Moscow local time. Repair and bike HR pair now share the UTC timeline resolver.
- Files/modules in scope:
  - `tests/smoke/test_activity_tss_reconciliation.py` — date-boundary repair matrix;
  - `tests/smoke/test_bike_hr_quality_pairs.py` — date-boundary `ftp_verified` matrix;
  - `data/data_processor.py` — UTC parser and shared FTP resolver;
  - `data/athlete_profile_store.py` — additive `ftp_timeline()` projection;
  - `data/database.py` — repair integration and timeline facade;
  - `services/bike_hr_pairs.py` — pair integration;
  - `docs/activity_tss_reconciliation_execplan.md` — living-plan evidence and next milestone;
  - `docs/activity_tss_reconciliation_502_slice_spec.md` — this Class A slice spec.

## Non-goals

- Behavior deliberately unchanged: Power TSS formula; personal HR-TSS model from #444; provider ingestion rules; legacy `ftp_history()/ftp_at(date)` contract; all live athlete data; API/web contracts; historical backfill; automatic correction of the live database; broad timezone refactor.
- Deferred work and owner: independent review, commit/push, PR, and issue comment — root agent. Any broader timezone normalization outside FTP provenance remains out of scope.

## Definition of Done

- [x] Acceptance criteria are observable: fixed UTC/Moscow tests use explicit timestamps and assert `tss_ftp_used`, `ftp_on_date`, and `ftp_verified`.
- [x] Required tests/checks are named and pass: the new parametrized nodes, the three issue-reported regression nodes, both focused smoke modules, targeted Ruff, and `git diff --check`.
- [x] Merge and cleanup owner is assigned: root agent owns independent review, commit/push, PR, and post-merge cleanup.

## Public Contracts

- `ActivityProcessor._started_at_utc` / persisted `activities.started_at_utc`: **unchanged**; the tests consume the existing UTC provenance field.
- `AthleteProfileStore.ftp_history()` and `data.data_processor.ftp_at(date)`: **unchanged**; old date-only callers retain their contract.
- `AthleteProfileStore.ftp_timeline()` and `Database.get_athlete_ftp_timeline()`: **changed compatibly/additive**; return `(UTC-aware synced_at, ftp)` entries without schema/API changes.
- `data.data_processor.resolve_ftp_for_activity(history, timeline, activity_date, activity_started_at_utc=None)`: **new internal contract**; returns `(ftp, verified)` and uses date fallback with `verified=False` when absolute evidence is unavailable.
- `Database._repair_legacy_activity_tss()` and `services.bike_hr_pairs.record_bike_hr_pair()`: **changed internally, persisted output corrected**; both consume the shared resolver.
- SQLite schema, API, TypeScript, configuration, CLI, and user-visible contracts: **unchanged**; no extractor or migration is required.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: invalid timestamps produce an empty timeline and deterministic date fallback; missing activity `started_at_utc` never produces `ftp_verified=true`. Every test uses `tmp_path`; failures leave only pytest temporary files and never touch `ai_trainer.db`.
- Retry/idempotency key and duplicate behavior: no product writes are introduced. Each parameter uses a distinct temporary database and activity ID; rerunning the command creates the same isolated fixture and the same result.
- Rollback procedure and proof: revert the resolver/store/service changes and retain the RED tests to reproduce the original failure; no schema rollback or runtime backfill is needed. The exact focused suite and `git diff --check` provide the proof boundary.
- [x] Does this add **new persistent state**? No. `ftp_timeline()` is a read projection over existing `athlete_profile` rows; no schema or live row is added.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? Yes; pytest `tmp_path` owns all rows and is cleaned by the test runner.
- [x] Restart and partial-failure recovery are covered. Each test performs a fresh `Database` reopen where relevant and asserts the repair/pair projection; no live sync or cursor is advanced.

## State Boundaries and Identity

- Source of truth and owner: fixed `startTimeGMT` is the activity instant; explicit/SQLite `athlete_profile.synced_at` is the profile snapshot instant; `AthleteProfileStore.ftp_timeline()` and `resolve_ftp_for_activity(...)` own the shared projection behavior.
- Stable identity/provenance keys: activity IDs `bike-502-utc`, `bike-502-europe_moscow`, and `bike-502-pair-*`; profile rows are explicitly addressed by their fresh SQLite IDs only inside isolated fixtures.
- Cursor/checkpoint lifecycle: N/A — the tests do not use provider cursors, checkpoints, or backfills.
- Concurrency and stale-write behavior: N/A for this deterministic single-writer fixture; no shared database is opened.

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| A profile snapshot two minutes after the same absolute ride must not replace the historical FTP during repair, independent of local representation. | `test_repair_uses_profile_before_same_absolute_activity_across_timezones[utc]` and `[europe_moscow]` | Historical RED: UTC passed; Europe/Moscow returned `tss_ftp_used=172` instead of `159`. | M2 GREEN: both parameters return `tss_ftp_used=159`. |
| A profile snapshot after the activity must not make a bike HR pair verified. | `test_bike_hr_pair_does_not_verify_profile_after_absolute_activity[utc]` and `[europe_moscow]` | Historical RED: UTC passed; Europe/Moscow returned `ftp_verified=1` instead of `0`. | M2 GREEN: both parameters persist `ftp_verified=0`, with the earliest FTP retained as unverified evidence. |
| Existing #451 repair behavior remains covered. | `test_repair_keeps_ftp_of_activity_date_when_profile_changes`; `test_repair_restores_date_accurate_ftp_for_mismatched_rows` | At the current host clock both pass; issue #502 records their failures at 00:03 Europe/Moscow when relative fixtures cross the SQLite UTC/local date boundary. | Existing regressions pass at ordinary and fixed boundary clocks after GREEN. |
| Existing #444 S1 pair behavior remains covered. | `test_garmin_sync_records_bike_hr_pair` | At the current host clock it passes; issue #502 records `ftp_verified=1` instead of `0` when the relative fixture is run just after local midnight. | Existing pair regression plus the fixed matrix pass repeatedly across UTC/Moscow. |
| No unrelated smoke/lint regression is introduced by the resolver or fixtures. | `ai_trainer_env/bin/python -m pytest tests/smoke/test_activity_tss_reconciliation.py tests/smoke/test_bike_hr_quality_pairs.py -q`; targeted Ruff; `git diff --check` | Historical RED baseline: `29 passed, 2 failed`; Ruff and diff check passed. | M2 GREEN: focused modules `32 passed`; Ruff `All checks passed!`; diff check passes. |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: **ASR-REL-1** (historical activity facts must not be silently rewritten), **ASR-REL-3** (safe, repeatable persistence around sync/repair), and **ASR-MOD-3** (legacy schema/rows remain backward-compatible). The fixed matrix is a correctness gate for these attributes.
- ADRs reused or required: ADR-0002 (SQLite timestamps and additive compatibility) plus issue #451 FTP provenance. No new ADR or migration is required because the timestamp-aware projection reads existing columns and preserves legacy interfaces.
- Tactic and trade-off: deterministic isolated fixtures and explicit UTC instants maximize testability and falsifiability. Absolute evidence is preferred; legacy date-only rows keep their FTP fallback but remain explicitly unverified.
- New architecture boundary discovered during review: absolute event chronology (`started_at_utc` versus profile `synced_at`) crosses the data-store date projection and the bike HR service; both consumers must share one resolver rather than independently interpreting local dates.

## Delivery Slices

For every slice, keep one reviewable behavior boundary and a clean pushed checkpoint where the agent workflow requires it.

1. Slice: M1 RED — deterministic UTC/Europe-Moscow provenance matrix.
   - RED, or characterization baseline for a behavior-preserving refactor: added the two parametrized tests; fixed-input execution is `5 passed, 2 failed`, with only Europe/Moscow variants failing.
   - GREEN: — intentionally not implemented in this slice.
   - Refactor/contract refresh: ExecPlan updated; Class A spec added; no production contract changed.
   - Verification: targeted Ruff and `git diff --check` pass; focused modules report `29 passed, 2 failed`.

2. Slice: M2 GREEN — shared absolute timestamp-aware FTP resolver.
   - RED: M1 matrix above.
   - GREEN: completed with additive `ftp_timeline()` and one shared resolver used by repair and bike HR pair; legacy date APIs remain compatible and unverified fallback is explicit.
   - Refactor/contract refresh: ExecPlan and this spec describe the additive internal contract; schema/API/TypeScript contracts remain unchanged.
   - Verification: boundary matrix, original regressions, focused modules, full smoke, contributor-safe pytest, Ruff, and diff check pass.

3. Slice: M3 review/publish.
   - RED: N/A after M2 GREEN; retain the RED transcript in the evidence bundle.
   - GREEN: independent checker confirms no live DB/backfill and no formula/#444 activation; PR closes #502.
   - Refactor/contract refresh: `git diff --check`, CI, and required post-merge process metrics.
   - Verification: real pushed branch and PR URL, then issue comment with commit SHA and evidence.

## Evidence Bundle

- Head SHA: base `79ff81044e731003a6af587056ee213f24ea0a78`; candidate commit pending publication. Eight files are in scope: four production/data files, two smoke files, the ExecPlan, and this spec.
- Changed invariants: equivalent UTC/Moscow representations select the same historical FTP; a future-only profile cannot become verified; subsecond ordering is preserved; missing absolute activity time keeps date fallback but returns `verified=False`.
- Focused and broad tests: historical RED `5 passed, 2 failed`; GREEN boundary/fallback nodes passed; focused modules `33 passed`; full smoke `2011 passed, 1 skipped`; contributor-safe pytest `2057 passed, 3 skipped, 26 deselected`.
- CI checks/reruns/flakes: targeted Ruff and `git diff --check` pass; CI awaits the draft PR. The socket-dependent smoke skip and missing optional `garth` skips are classified environment/optional-dependency skips.
- Lifecycle/probe evidence: all tests use temporary SQLite paths; no `ai_trainer.db` opened or modified; second `Database` construction exercises repair in the repair case.
- Changed contracts: additive internal timeline/resolver only; no API/web/TypeScript/schema changes.
- Unresolved review-thread count: N/A — no PR opened by this slice.
- Residual risks and follow-ups: legacy rows without an absolute activity timestamp cannot prove chronology, so they intentionally remain unverified; no backfill is performed in #502.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | **Observed**: fixed `startTimeGMT=2026-08-23T23:59:00Z` and profile `synced_at=2026-08-24T00:01:00Z` failed only under the Europe/Moscow local representation. **Inferred**: date truncation selected a future profile. **Verified by**: historical RED `5 passed, 2 failed`, then GREEN matrix and full suites. | Closed: shared absolute resolver passes both representations. | Luna + root / resolved. |
| P2 | **Observed**: relative fixtures used multiple `datetime.now()` calls while SQLite `CURRENT_TIMESTAMP` is UTC. **Inferred**: setup was independently wall-clock sensitive. **Verified by**: fixed anchors plus direct exact-row reads pass without a 30-day aging dependency. | Closed: fixtures no longer depend on the host date. | Luna / resolved. |
| P2 | **Observed**: first GREEN parser truncated microseconds. **Inferred**: a later profile inside the same second could appear simultaneous with an earlier activity. **Verified by**: independent Luna probe and new `.900000Z` profile versus `.500000Z` activity regression. | Closed: parser retains subsecond precision and regression passes. | Independent Luna checker + root / resolved. |
| P2 | **Observed**: the Class A spec still described M2 as pending after implementation. **Inferred**: review evidence was stale. **Verified by**: synchronized delivery slices, evidence bundle, review findings, and verdict. | Closed: document matches the candidate. | Independent Luna checker + root / resolved. |

## Final Verdict

- Verdict: **READY** for draft PR publication.
- Blocking findings remaining: none.
- Review rounds used: 1 / 2.
- Accepted risk or follow-up issue: legacy rows without absolute activity time remain conservatively unverified; this is deliberate #502 behavior, not a backfill request.
- Merge owner final gate: root agent must commit/push, open the draft PR, and wait for CI/review before any merge.
- Post-merge sync/branch/worktree/progress cleanup: merge owner syncs local `main`, deletes the merged branch as appropriate, and records the final PR/check evidence.
